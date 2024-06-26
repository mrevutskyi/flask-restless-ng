# base.py - base classes for views of SQLAlchemy objects
#
# Copyright 2011 Lincoln de Sousa <lincoln@comum.org>.
# Copyright 2012, 2013, 2014, 2015, 2016 Jeffrey Finkelstein
#           <jeffrey.finkelstein@gmail.com> and contributors.
#
# This file is part of Flask-Restless.
#
# Flask-Restless is distributed under both the GNU Affero General Public
# License version 3 and under the 3-clause BSD license. For more
# information, see LICENSE.AGPL and LICENSE.BSD.
"""Base classes for fetching, creating, updating, and deleting
SQLAlchemy resources and relationships.

The main class in this module, :class:`APIBase`, is a
:class:`~flask.MethodView` subclass that is also an abstract base class
for JSON API requests on a SQLAlchemy backend.

"""
import math
import re
from collections import defaultdict
from functools import partial
from functools import wraps
from http import HTTPStatus
from itertools import chain
from typing import Optional
from typing import Set
from typing import Tuple
from urllib.parse import urlparse
from urllib.parse import urlunparse

from flask import Response
from flask import current_app
from flask import json
from flask import request
from flask.views import MethodView
from flask.views import View
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import load_only
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.dynamic import DynamicAttributeImpl
from sqlalchemy.orm.query import Query
from sqlalchemy.sql import false as FALSE
from sqlalchemy.sql.elements import BinaryExpression
from werkzeug.exceptions import HTTPException
from werkzeug.http import parse_options_header

from ..exceptions import BadRequest
from ..exceptions import Error
from ..exceptions import NotFound
from ..helpers import get_inclusions_for_instances
from ..helpers import get_model
from ..helpers import get_related_model
from ..helpers import is_like_list
from ..helpers import is_proxy
from ..helpers import query_by_primary_key
from ..helpers import session_query
from ..search import ComparisonToNull
from ..search import search
from ..serialization import DefaultSerializer
from ..serialization import DeserializationException
from ..serialization import SerializationException
from ..serialization import Serializer
from ..typehints import ResponseTuple
from .helpers import count
from .helpers import upper_keys as upper

#: The Content-Type we expect for most requests to APIs.
#:
#: The JSON API specification requires the content type to be
#: ``application/vnd.api+json``.
CONTENT_TYPE = 'application/vnd.api+json'

#: The highest version of the JSON API specification supported by
#: Flask-Restless.
JSONAPI_VERSION = '1.0'

#: Strings that indicate a database conflict when appearing in an error
#: message of an exception raised by SQLAlchemy.
#:
#: The particular error message depends on the particular environment
#: containing the SQLite backend, it seems.
CONFLICT_INDICATORS = ('conflicts with', 'UNIQUE constraint failed',
                       'is not unique')

#: The names of pagination links that appear in both ``Link`` headers
#: and JSON API links.
LINK_NAMES = ('first', 'last', 'prev', 'next')

#: The query parameter key that identifies filter objects in a
#: :https:method:`get` request.
FILTER_PARAM = 'filter[objects]'

#: The query parameter key that identifies sort fields in a :https:method:`get`
#: request.
SORT_PARAM = 'sort'

#: The query parameter key that identifies the page number in a
#: :https:method:`get` request.
PAGE_NUMBER_PARAM = 'page[number]'

#: The query parameter key that identifies the page size in a
#: :https:method:`get` request.
PAGE_SIZE_PARAM = 'page[size]'

#: A regular expression for Accept headers.
#:
#: For an explanation of "media-range", etc., see Sections 5.3.{1,2} of
#: RFC 7231.
ACCEPT_RE = re.compile(
    r'''(                       # media-range capturing-parenthesis
          [^\s;,]+              # type/subtype
          (?:[ \t]*;[ \t]*      # ";"
            (?:                 # parameter non-capturing-parenthesis
              [^\s;,q][^\s;,]*  # token that doesn't start with "q"
            |                   # or
              q[^\s;,=][^\s;,]* # token that is more than just "q"
            )
          )*                    # zero or more parameters
        )                       # end of media-range
        (?:[ \t]*;[ \t]*q=      # weight is a "q" parameter
          (\d*(?:\.\d+)?)       # qvalue capturing-parentheses
          [^,]*                 # "extension" accept params: who cares?
        )?                      # accept params are optional
    ''', re.VERBOSE)

#: Keys in a JSON API error object.
ERROR_FIELDS = ('id_', 'links', 'status', 'code_', 'title', 'detail', 'source',
                'meta')


def collection_parameters():
    """Gets filtering, sorting and other settings from the
    request that affect the collection of resources in a response.

    Returns a tuple of the form ``(filters, sort)``.
    These can be provided to the
    :func:`~flask_restless.search.search` function; for more
    information, see the documentation for that function.

    """
    try:
        # Determine filtering options.
        filters = json.loads(request.args.get(FILTER_PARAM, '[]'))

        # Determine sorting options.
        sort = request.args.get(SORT_PARAM)
        if sort:
            if sort == '0':
                # '0' disables default sorting
                sort = None
            else:
                sort = [('-', value[1:]) if value.startswith('-') else ('+', value)
                        for value in sort.split(',')]
        else:
            sort = []
    except (TypeError, KeyError, ValueError) as e:
        raise BadRequest(cause=e, details='Unable to decode filter objects as JSON list') from e

    return filters, sort


class PaginationError(Exception):
    """Raised when pagination fails, due to, for example, a bad
    pagination parameter supplied by the client.

    """
    pass


class ProcessingException(HTTPException):
    """Raised when a preprocessor or postprocessor encounters a problem.

    This exception should be raised by functions supplied in the
    ``preprocessors`` and ``postprocessors`` keyword arguments to
    :class:`APIManager.create_api`. When this exception is raised, all
    preprocessing or postprocessing halts, so any processors appearing
    later in the list will not be invoked.

    The keyword arguments ``id_``, ``href`` ``status``, ``code``,
    ``title``, ``detail``, ``links``, ``paths`` correspond to the
    elements of the JSON API error object; the values of these keyword
    arguments will appear in the error object returned to the client.

    Any additional positional or keyword arguments are supplied directly
    to the superclass, :exc:`werkzeug.exceptions.HTTPException`.

    """

    def __init__(self, id_=None, links=None, status=400, code=None, title=None,
                 detail=None, source=None, meta=None, *args, **kw):
        super(ProcessingException, self).__init__(*args, **kw)
        self.id_ = id_
        self.links = links
        self.status = status
        # This attribute would otherwise override the class-level
        # attribute `code` in the superclass, HTTPException.
        self.code_ = code
        self.code = status
        self.title = title
        self.detail = detail
        self.source = source
        self.meta = meta


class MultipleExceptions(Exception):
    """Raised when there are multple problems in the code.

    `exceptions` is a non-empty sequence of other exceptions that have
    been raised in the code.

    """

    def __init__(self, exceptions, *args):
        super(MultipleExceptions, self).__init__(*args)

        #: Sequence of other exceptions that have been raised in the code.
        self.exceptions = exceptions


def un_camel_case(s):
    """Inserts spaces before the capital letters in a camel case string.

    """
    # This regular expression appears on StackOverflow
    # <https://stackoverflow.com/a/199120/108197>, and is distributed
    # under the Creative Commons Attribution-ShareAlike 3.0 Unported
    # license.
    return re.sub(r'(?<=\w)([A-Z])', r' \1', s)


def catch_processing_exceptions(func):
    """Decorator that catches :exc:`ProcessingException`s and subsequently
    returns a JSON-ified error response.

    """
    @wraps(func)
    def new_func(*args, **kw):
        """Executes ``func(*args, **kw)`` but catches
        :exc:`ProcessingException`s.

        """
        try:
            return func(*args, **kw)
        except ProcessingException as exception:
            kw = {key: getattr(exception, key) for key in ERROR_FIELDS}
            # Need to change the name of the `code` key as a workaround
            # for name collisions with Werkzeug exception classes.
            kw['code'] = kw.pop('code_')
            return error_response(cause=exception, **kw)
    return new_func


# This code is (lightly) adapted from the ``werkzeug`` library, in the
# ``werkzeug.http`` module. See <https://werkzeug.pocoo.org> for more
# information.
def parse_accept_header(value):
    """Parses an HTTP Accept-* header.

    This does not implement a complete valid algorithm but one that
    supports at least value and quality extraction.

    `value` is the :https:header:`Accept` header string (everything after
    the ``Accept:``) to be parsed.

    Returns an iterator over ``(value, extra)`` tuples. If there were no
    media type parameters, then ``extra`` is simply ``None``.

    """
    def match_to_pair(match):
        """Returns the pair ``(name, quality)`` from the given match
        object for the Accept header regular expression.

        ``name`` is the name of the content type that is accepted, and
        ``quality`` is the integer given by the header's media type
        parameter, or ``None`` if it has no such media type paramer.

        """
        name = match.group(1)
        extra = match.group(2)
        # This is the main difference between our implementation and
        # Werkzeug's implementation: all we want to know is whether
        # there is any media type parameters or not, so we mark the
        # quality is ``None`` instead of ``1`` here.
        quality = max(min(float(extra), 1), 0) if extra else None
        return name, quality
    return map(match_to_pair, ACCEPT_RE.finditer(value))


def requires_json_api_accept(func):
    """Decorator that requires :https:header:`Accept` headers with the
    JSON API media type to have no media type parameters.

    This does *not* require that all requests have an
    :https:header:`Accept` header, just that those requests with an
    :https:header:`Accept` header for the JSON API media type have no
    media type parameters. However, if there are only
    :https:header:`Accept` headers that specify non-JSON API media types,
    this will cause a :https:status`406` response.

    If a request does not have the correct ``Accept`` header, a
    :https:status:`406` response is returned. An incorrect header is
    described in the `Server Responsibilities`_ section of the JSON API
    specification:

        Servers MUST respond with a 406 Not Acceptable status code if a
        request's Accept header contains the JSON API media type and all
        instances of that media type are modified with media type
        parameters.

    View methods can be wrapped like this::

        @requires_json_api_accept
        def get(self, *args, **kw):
            return '...'

    .. _Server Responsibilities: https://jsonapi.org/format/#content-negotiation-servers

    """
    @wraps(func)
    def new_func(*args, **kw):
        """Executes ``func(*args, **kw)`` only after checking for the
        correct JSON API :https:header:`Accept` header.

        """
        header = request.headers.get('Accept')
        # If there is no Accept header, we don't need to do anything.
        if header is None:
            return func(*args, **kw)
        header_pairs = list(parse_accept_header(header))
        # If the Accept header is empty, then do nothing.
        #
        # An empty Accept header is technically allowed by RFC 2616,
        # Section 14.1 (for more information, see
        # https://stackoverflow.com/a/12131993/108197). Since an empty
        # Accept header doesn't violate JSON APIs rule against having
        # only JSON API mimetypes with media type parameters, we simply
        # proceed as normal with the request.
        if len(header_pairs) == 0:
            return func(*args, **kw)
        jsonapi_pairs = [(name, extra) for name, extra in header_pairs
                         if name.startswith(CONTENT_TYPE)]
        # If there are Accept headers but none of them specifies the
        # JSON API media type, respond with `406 Not Acceptable`.
        if len(jsonapi_pairs) == 0:
            detail = ('Accept header, if specified, must be the JSON API media'
                      ' type: application/vnd.api+json')
            return error_response(406, detail=detail)
        # If there are JSON API Accept headers, but they all have media
        # type parameters, respond with `406 Not Acceptable`.
        if all(extra is not None for name, extra in jsonapi_pairs):
            detail = ('Accept header contained JSON API content type, but each'
                      ' instance occurred with media type parameters; at least'
                      ' one instance must appear without parameters (the part'
                      ' after the semicolon)')
            return error_response(406, detail=detail)
        # At this point, everything is fine, so just execute the method as-is.
        return func(*args, **kw)
    return new_func


def requires_json_api_mimetype(func):
    """Decorator that requires requests *that include data* have the
    :https:header:`Content-Type` header required by the JSON API
    specification.

    If the request does not have the correct :https:header:`Content-Type`
    header, a :https:status:`415` response is returned.

    View methods can be wrapped like this::

        @requires_json_api_mimetype
        def get(self, *args, **kw):
            return '...'

    """
    @wraps(func)
    def new_func(*args, **kw):
        """Executes ``func(*args, **kw)`` only after checking for the
        correct JSON API :https:header:`Content-Type` header.

        """
        # GET and DELETE requests don't have request data in JSON API,
        # so we can ignore those and only continue if this is a PATCH or
        # POST request.
        #
        # Ideally we would be able to decorate each individual request
        # methods directly, but it is not possible with the current
        # design of Flask's method-based views.
        if request.method not in ('PATCH', 'POST'):
            return func(*args, **kw)
        header = request.headers.get('Content-Type')
        content_type, extra = parse_options_header(header)
        content_is_json = content_type.startswith(CONTENT_TYPE)
        # Request must have the Content-Type: application/vnd.api+json header,
        if not content_is_json:
            detail = f'Request must have "Content-Type: {CONTENT_TYPE}" header'
            return error_response(415, detail=detail)
        # JSON API requires that the content type header does not have
        # any media type parameters.
        if extra:
            detail = f'Content-Type header must not have any media type parameters but found {extra}'
            return error_response(415, detail=detail)
        return func(*args, **kw)
    return new_func


def mime_renderer(func):

    @wraps(func)
    def new_func(*args, **kw):
        data, status_code, headers = func(*args, **kw)
        return Response(response=json.dumps(data), status=status_code, mimetype=CONTENT_TYPE, headers=headers)
    return new_func


def catch_integrity_errors(session):
    """Returns a decorator that catches database integrity errors.

    `session` is the SQLAlchemy session in which all database transactions will
    be performed.

    View methods can be wrapped like this::

        @catch_integrity_errors(session)
        def get(self, *args, **kw):
            return '...'

    Specifically, functions wrapped with the returned decorator catch the
    exceptions specified in :data:`ROLLBACK_ERRORS`. After the exceptions are
    caught, the session is rolled back, the exception is logged on the current
    Flask application, and an error response is returned to the client.

    """
    def decorated(func):
        """Returns a decorated version of ``func``, as described in the
        wrapper defined within.

        """
        @wraps(func)
        def wrapped(*args, **kw):
            """Executes ``func(*args, **kw)`` but catches any exception
            that warrants a database rollback.

            """
            try:
                return func(*args, **kw)
            # This should include: DataError, IntegrityError,
            # ProgrammingError, FlushError, OperationalError,
            # InvalidRequestError, and any other SQLAlchemyError
            # subclass.
            except SQLAlchemyError as exception:
                session.rollback()
                # Special status code for conflicting instances: 409 Conflict
                status = 409 if is_conflict(exception) else 400
                detail = str(exception)
                title = un_camel_case(exception.__class__.__name__)
                return error_response(status, detail=detail, title=title)
        return wrapped
    return decorated


def is_conflict(exception):
    """Returns ``True`` if and only if the specified exception represents a
    conflict in the database.

    """
    exception_string = str(exception)
    return any(s in exception_string for s in CONFLICT_INDICATORS)


def parse_sparse_fields(type_=None):
    """Get the sparse fields as requested by the client.

    Returns a dictionary mapping resource type names to set of fields to
    include for that resource.

    For example, if the client requests::

        GET /articles?fields[articles]=title,body&fields[people]=name

    then::

        >>> parse_sparse_fields()
        {'articles': {'title', 'body'}, 'people': {'name'}}

    If the `type_` argument is given, only the set of fields for that resource
    type will be returned::

        >>> parse_sparse_fields('articles')
        {'title', 'body'}

    """
    # TODO use a regular expression to ensure field parameters are of the
    # correct format? (maybe ``fields\[[^\[\]\.]*\]``)
    fields = {key[7:-1]: set(value.split(','))
              for key, value in request.args.items()
              if key.startswith('fields[') and key.endswith(']')}
    return fields.get(type_) if type_ is not None else fields


def resources_from_path(instance, path):
    """Returns an iterable of all resources along the given relationship
    path for the specified instance of the model.

    For example, if our model includes three classes, ``Article``,
    ``Person``, and ``Comment``::

        >>> article = Article(id=1)
        >>> comment1 = Comment(id=1)
        >>> comment2 = Comment(id=2)
        >>> person1 = Person(id=1)
        >>> person2 = Person(id=2)
        >>> article.comments = [comment1, comment2]
        >>> comment1.author = person1
        >>> comment2.author = person2
        >>> instances = [article, comment1, comment2, person1, person2]
        >>> session.add_all(instances)
        >>>
        >>> l = list(api.resources_from_path(article, 'comments.author'))
        >>> len(l)
        4
        >>> [r.id for r in l if isinstance(r, Person)]
        [1, 2]
        >>> [r.id for r in l if isinstance(r, Comment)]
        [1, 2]

    """
    # First, split the path to determine the sequence of relationships
    # to follow.
    if '.' in path:
        path = path.split('.')
    else:
        path = [path]
    # Next, do a breadth-first traversal of the resources related to
    # `instance` via the given path.
    seen = set()
    nextlevel = {instance}
    first_time = True
    while nextlevel:
        thislevel = nextlevel
        nextlevel = set()
        # Follow the relation given in the path to get the "neighbor"
        # resources of any resource in the current level of the
        # breadth-first traversal.
        if path:
            relation = path.pop(0)
        else:
            relation = None
        for resource in thislevel:
            if resource is None:
                continue
            if resource in seen:
                continue
            # Since this method is going to be used to populate the
            # `included` section of a compound document, we don't want
            # to yield the instance from which related resources are
            # being included.
            if first_time:
                first_time = False
            else:
                yield resource
            seen.add(resource)
            # If there are still parts of the relationship path to
            # traverse, queue up the related resources at the next
            # level.
            if relation is not None:
                if is_like_list(resource, relation):
                    update = nextlevel.update
                else:
                    update = nextlevel.add
                update(getattr(resource, relation))


# TODO these need to become JSON Pointers
def extract_error_messages(exception):
    """Tries to extract a dictionary mapping field name to validation error
    messages from `exception`, which is a validation exception as provided in
    the ``validation_exceptions`` keyword argument to the constructor of the
    :class:`APIBase` class.

    Since the type of the exception is provided by the user in the constructor
    of that class, we cannot know for sure where the validation error messages
    live inside `exception`. Therefore this method simply attempts to access a
    few likely attributes and returns the first one it finds (or ``None`` if no
    error messages dictionary can be extracted).

    """
    # Check for our own built-in validation error.
    if isinstance(exception, DeserializationException):
        return exception.args[0]
    # 'errors' comes from sqlalchemy_elixir_validations
    if hasattr(exception, 'errors'):
        return exception.errors


def error(id_=None, links=None, status=None, code=None, title=None,
          detail=None, source=None, meta=None):
    """Returns a dictionary representation of an error as described in the
    JSON API specification.

    Note: the ``id_`` keyword argument corresponds to the ``id`` element
    of the JSON API error object.

    For more information, see the `Errors`_ section of the JSON API
    specification.

    .. Errors_: https://jsonapi.org/format/#errors

    """
    # HACK We use locals() so we don't have to list every keyword argument.
    if all(kwvalue is None for kwvalue in locals().values()):
        raise ValueError('At least one of the arguments must not be None.')

    # JSON API requires 'status' field to be a string
    if isinstance(status, HTTPStatus):
        status = str(status.value)
    elif isinstance(status, int):
        status = str(status)

    return {'id': id_, 'links': links, 'status': status, 'code': code,
            'title': title, 'detail': detail, 'source': source, 'meta': meta}


def error_response(status=400, cause=None, **kw):
    """Returns a correctly formatted error response with the specified
    parameters.

    This is a convenience function for::

        errors_response(status, [error(**kw)])

    For more information, see :func:`errors_response`.

    """
    if cause is not None:
        current_app.logger.exception(str(cause))
    return errors_response(status, [error(status=status, **kw)])


def errors_response(status, errors) -> Tuple[dict, int, dict]:
    """Return an error response with multiple errors.

    `status` is an integer representing an HTTP status code corresponding to an
    error response.

    `errors` is a list of error dictionaries, each of which must satisfy the
    requirements of the JSON API specification.

    This function returns a two-tuple whose left element is a dictionary
    representing a JSON API response document and whose right element is
    simply `status`.

    In addition to a list of the error objects under the ``'errors'``
    key, a jsonapi object, the returned dictionary object also includes
    under the ``'meta'`` element a key with a special name, stored in
    the key :data:`_STATUS`, which is used to workaround an
    incompatibility between Flask and mimerender that doesn't allow
    setting headers on a global response object.

    The keys within each error object are described in the `Errors`_
    section of the JSON API specification.

    .. _Errors: https://jsonapi.org/format/#errors

    """
    document = {'errors': errors, 'jsonapi': {'version': JSONAPI_VERSION}}
    return document, status, {}


def error_from_serialization_exception(exception, included=False):
    """Returns an error dictionary, as returned by :func:`error`,
    representing the given instance of :exc:`SerializationException`.

    If `included` is ``True``, this indicates that the exceptions were
    raised by attempts to serialize resources included in a compound
    document; this modifies the error message for the exceptions a bit
    to indicate that the resources were included resource, not primary
    data.
    """
    # As long as `exception` is a `SerializationException` that has been
    # initialized with an actual instance of a SQLAlchemy model, these
    # helper function calls should not cause a problem.
    if exception.message is not None:
        detail = exception.message
    else:
        resource = 'included resource' if included else 'resource'
        detail = 'Failed to serialize {0} of type {1} and ID {2}'
        detail = detail.format(resource, exception.resource_type, exception.resource_id)
    return error(status=500, detail=detail)


def errors_from_serialization_exceptions(exceptions, included=False):
    """Returns an errors response object, as returned by
    :func:`errors_response`, representing the given list of
    :exc:`SerializationException` objects.

    If `included` is ``True``, this indicates that the exceptions were
    raised by attempts to serialize resources included in a compound
    document; this modifies the error message for the exceptions a bit.

    """
    _to_error = partial(error_from_serialization_exception, included=included)
    errors = list(map(_to_error, exceptions))
    return errors_response(500, errors)


class Paginated:
    """Represents a paginated list of resources.

    This class is intended to be instantiated *after* the correct page
    of a collection has been computed. It is mainly used to handle link
    URLs for JSON API documents and HTTP headers.

    `items` is a list of dictionaries, each of which is a JSON API
    resource, either a resource object or a link object.

    `page_size` and `page_number` are the size and number of the current
    page (that is, the page containing `items`). If `page_size` is zero,
    then `items` must be *all* the items in the collection requested by
    the client. In this particular case, this object does not really
    represent a paginated response. Thus, there will be no pagination or
    header links; see :attr:`header_links` and
    :attr:`pagination_links`. Otherwise, `page_size` must be at least as
    large as the length of `items`.

    `num_results` is the total number of resources or link objects on
    all pages, not just the page represented by `items`.

    `first`, `last`, `prev`, and `next_` are integers representing the
    number of the first, last, previous, and next pages,
    respectively. These can also be ``None``, in the case that there is
    no such page.

    `filters`, and `sort` are the filtering and sorting query parameters
    from the request that yielded the given items.

    After instantiating this object, one can access a list of link
    header strings and a dictionary of pagination link strings as
    suggested by the JSON API specification, as well as the number of
    results and the items provided in the constructor. For example::

        >>> people = ['person1', 'person2', 'person3']
        >>> paginated = Paginated(people, num_results=10, page_number=2,
        ...                       page_size=3, first=1, last=4, prev=1, next=3)
        >>> paginated.items
        ['person1', 'person2', 'person3']
        >>> paginated.num_results
        10
        >>> for rel, url in paginated.pagination_links.items():
        ...     print(rel, url)
        ...
        first https://example.com/api/person?page[size]=3&page[number]=1
        last https://example.com/api/person?page[size]=3&page[number]=4
        prev https://example.com/api/person?page[size]=3&page[number]=1
        next https://example.com/api/person?page[size]=3&page[number]=3
        >>> for link in paginated.header_links:
        ...     print(link)
        ...
        <https://example.com/api/person?page[size]=3&page[number]=1>; rel="first"
        <https://example.com/api/person?page[size]=3&page[number]=4>; rel="last"
        <https://example.com/api/person?page[size]=3&page[number]=1>; rel="prev"
        <https://example.com/api/person?page[size]=3&page[number]=3>; rel="next"

    """

    @staticmethod
    def _filters_to_string(filters):
        """Returns a string representation of the specified dictionary
        of filter objects.

        This is essentially the inverse operation of the parsing that is
        done when reading the filter objects from the query parameters
        of the request string in a :https:method:`get` request.

        """
        return json.dumps(filters)

    @staticmethod
    def _sort_to_string(sort):
        """Returns a string representation of the specified sort fields.

        This is essentially the inverse operation of the parsing that is
        done when reading the sort fields from the query parameters of
        the request string in a :https:method:`get` request.

        """
        return ','.join(''.join((dir_, field)) for dir_, field in sort)

    @staticmethod
    def _url_without_pagination_params():
        """Returns the request URL including all query parameters except
        the page size and page number query parameters.

        The URL is returned as a string.

        """
        # Parse pieces of the URL requested by the client.
        path = request.path
        headers = request.headers
        # If X-Forwarded- headers are present use their values to build the URL
        # because request could be proxied by a load balancer
        host = headers.get('X-Forwarded-Host', request.host)
        proto = headers.get('X-Forwarded-Proto', request.scheme)
        query_params = request.args
        # Set the new query_parameters to be everything except the
        # pagination query parameters.
        new_query = {k: v for k, v in query_params.items() if k not in (PAGE_NUMBER_PARAM, PAGE_SIZE_PARAM)}
        new_query_string = '&'.join(map('='.join, new_query.items()))
        # Join the base URL with the query parameter string.
        return f'{proto}://{host}{path}?{new_query_string}'

    @staticmethod
    def _to_url(base_url, query_params):
        """Returns the specified base URL augmented with the given query
        parameters.

        `base_url` is a string representing a URL.

        `query_params` is a dictionary whose keys and values are strings,
        representing the query parameters to append to the given URL.

        If the base URL already has query parameters, the ones given in
        `query_params` are appended.

        """
        query_string = '&'.join(map('='.join, query_params.items()))
        scheme, netloc, path, params, query, fragment = urlparse(base_url)
        if query:
            query_string = '&'.join((query, query_string))
        parsed = (scheme, netloc, path, params, query_string, fragment)
        return urlunparse(parsed)

    def __init__(self, items, first=None, last=None, prev=None, next_=None,
                 page_size=None, num_results=None, filters=None, sort=None,
                 raw_items=None):
        self._items = items
        self._raw_items = raw_items
        self._num_results = num_results
        # Pagination links and the link header are computed by the code below.
        self._pagination_links = {}
        self._header_links = []
        # If page size is zero, there is really no pagination, so we
        # don't need to compute pagination links or header links.
        if page_size == 0:
            return
        # Create the pagination link URLs.
        #
        # Need to account for filters, and sort in addition
        # to pagination links, so we collect those query parameters
        # here, if they exist.
        query_params = {}
        if filters:
            query_params[FILTER_PARAM] = Paginated._filters_to_string(filters)
        if sort:
            query_params[SORT_PARAM] = Paginated._sort_to_string(sort)
        # The page size is independent of the link type (first, last,
        # next, or prev).
        query_params[PAGE_SIZE_PARAM] = str(page_size)
        # Maintain a list of URLs that should appear in a Link
        # header. If a link does not exist (for example, if there is no
        # previous page), then that link URL will not appear in this
        # list.
        link_numbers = [first, last, prev, next_]
        # Determine the URL as it would appear without the
        # client-requested pagination query parameters.
        #
        # (`base_url` is not a great name here, since
        # `flask.Request.base_url` is the URL *without* the query
        # parameters.)
        base_url = Paginated._url_without_pagination_params()
        for rel, num in zip(LINK_NAMES, link_numbers):
            # If the link doesn't exist (for example, if there is no
            # previous page), then add ``None`` to the pagination links
            # but don't add a link URL to the headers.
            if num is None:
                self._pagination_links[rel] = None
            else:
                # Each time through this `for` loop we update the page
                # number in the `query_param` dictionary, so the the
                # `_to_url` method will give us the correct URL for that
                # page.
                query_params[PAGE_NUMBER_PARAM] = str(num)
                url = Paginated._to_url(base_url, query_params)
                link_string = f'<{url}>; rel="{rel}"'
                self._header_links.append(link_string)
                self._pagination_links[rel] = url
        # TODO Here we should really make the attributes immutable:
        #
        #     self._header_links = ImmutableList(self._header_links)
        #     ...
        #

    @property
    def header_links(self):
        """List of link header strings for the paginated response.

        The headers can be provided to the HTTP response by using a
        dictionary like this::

            >>> paginated = Paginated(...)
            >>> headers = {'Link': ','.join(paginated.header_links)}

        There may be a way of creating multiple link headers like
        this, in certain situations::

            >>> headers = [('Link', link) for link in header_links]

        """
        return self._header_links

    @property
    def pagination_links(self):
        """Dictionary of pagination links for JSON API documents.

        This dictionary has the relationship of the page to this page as
        the key (``'first'``, ``'last'``, ``'prev'``, and ``'next'``)
        and the URL as the value.

        """
        return self._pagination_links

    @property
    def items(self):
        """The items in the current page that this object represents."""
        return self._items

    @property
    def raw_items(self):
        return self._raw_items

    @property
    def num_results(self):
        """The total number of elements in the search result, one page
        of which this object represents.

        """
        return self._num_results


class ModelView(MethodView):
    """Base class for :class:`flask.MethodView` classes which represent a view
    of a SQLAlchemy model.

    `session` is the SQLAlchemy session in which all database transactions will
    be performed.

    `model` is the SQLALchemy declarative model class of the database model for
    which this instance of the class is an API.

    The model class for this view can be accessed from the :attr:`model`
    attribute, and the session in which all database transactions will be
    performed when dealing with this model can be accessed from the
    :attr:`session` attribute.

    """

    #: List of decorators applied to every method of this class.
    #:
    #: If a subclass must add more decorators, prepend them to this list::
    #:
    #:     class MyView(ModelView):
    #:         decorators = [my_decorator] + ModelView.decorators
    #:
    #: This way, the :data:`mimerender` function appears last. It must appear
    #: last so that it can render the returned dictionary.
    decorators = [requires_json_api_accept, requires_json_api_mimetype, mime_renderer]

    def __init__(self, session, model, *args, **kw):
        super(ModelView, self).__init__(*args, **kw)
        self.session = session
        self.model = model


class FetchView(View):
    decorators = [catch_processing_exceptions, requires_json_api_accept, requires_json_api_mimetype, mime_renderer]

    def __init__(self, session, model, api_manager, page_size=10, max_page_size=100, preprocessors=None, postprocessors=None, includes=None):
        self.session = session
        self.model = model
        self.api_manager = api_manager
        self.page_size = page_size
        self.max_page_size = max_page_size
        self.preprocessors = preprocessors or []
        self.postprocessors = postprocessors or []
        # TODO: parse request arguments here
        self.sparse_fields = parse_sparse_fields()
        if includes:
            self.default_includes = frozenset(includes)
        else:
            self.default_includes = {}

    def dispatch_request(self, *args, **kwargs):
        include = request.args.get('include')
        if include is None:
            include = self.default_includes
        else:
            include = set(include.split(','))

        try:
            return self.get_data(*args, include=include, **kwargs)
        except BadRequest as e:
            return error_response(e.http_code, detail=e.details)
        except Error as e:
            return error_response(e.http_code, cause=e.cause, detail=e.details)
        except MultipleExceptions as e:
            return errors_from_serialization_exceptions(e.exceptions)

    def get_data(self, *args, include: Optional[Set[str]] = None, **kwargs) -> ResponseTuple:
        raise NotImplementedError

    def _serialize_instances(self, instances):
        # should live in API MANAGER?
        serialized_instances = []
        failed = []
        for instance in instances:
            if instance is None:
                continue
            model = get_model(instance)
            serializer = self.api_manager.serializer_for(model)
            # This may raise ValueError
            _type = self.api_manager.collection_name(model)
            # TODO The `only` keyword argument will be ignored when
            # serializing relationships, so we don't really need to
            # recompute this every time.
            only = self.sparse_fields.get(_type)
            try:
                serialized = serializer.serialize(instance, only=only)
                serialized_instances.append(serialized)
            except SerializationException as exception:
                failed.append(exception)
        if failed:
            raise MultipleExceptions(failed)
        return serialized_instances

    def _selectinload_included_relationships(
            self,
            query: Query,
            include: Set[str],
            serializer: Serializer,
            filters=None
    ) -> Query:

        def is_safe_to_selectload(attribute):
            # SQLAlchemy does not build correct `selectinload` queries for models that have special select join
            try:
                inspected_relationship = inspect(attribute)
                if inspected_relationship.property.secondary:
                    return False
                if not isinstance(inspected_relationship.property.primaryjoin, BinaryExpression):
                    return False
            except Exception:
                # we do not have enough information, assume it's not safe
                return False

            return True

        join_paths = {path.split('.')[0] for path in include}

        for path in join_paths:
            attribute = getattr(self.model, path)
            if not is_safe_to_selectload(attribute):
                continue
            if not is_proxy(attribute) and not isinstance(attribute.impl, DynamicAttributeImpl):
                query = query.options(selectinload(attribute))

        relationship_columns = serializer.relationship_columns

        # `many_to_one_relationships` is not a part of the base Serializer class, so to keep backward compatibility
        # check if we use DefaultSerializer
        if isinstance(serializer, DefaultSerializer):
            relationship_columns -= serializer.many_to_one_relationships

        for path in relationship_columns:
            attribute = getattr(self.model, path)
            if not is_safe_to_selectload(attribute):
                continue
            if path not in join_paths and not is_proxy(attribute) and not isinstance(attribute.impl, DynamicAttributeImpl):
                options = selectinload(attribute)

                # if request contains filters we need to load all columns
                if not filters:
                    try:
                        related_model = get_related_model(self.model, path)
                        pk = self.api_manager.primary_key_for(related_model)
                        options = options.options(load_only(getattr(related_model, pk)))
                    except KeyError:
                        # theoretically all models should be known to the API, and we should raise a Server Error if they are not,
                        # but to keep backward compatibility we let it pass
                        pass
                query = query.options(options)

        return query


class FetchCollection(FetchView):
    """Processes requests to fetch a resource collection."""

    def get_data(self, *args, include=None, **kwargs):
        filters, sort = collection_parameters()
        for preprocessor in self.preprocessors:
            preprocessor(filters=filters, sort=sort)
        page_size = int(request.args.get(PAGE_SIZE_PARAM, self.page_size))
        if page_size > self.max_page_size:
            raise BadRequest(details=f"Page size must not exceed the server's maximum: {self.max_page_size}")
        if page_size < 0:
            raise BadRequest(details='Page size can not be negative')
        page_number = int(request.args.get(PAGE_NUMBER_PARAM, 1))
        if page_number < 0:
            raise BadRequest(details='Page number can not be negative')
        if page_size == 0 and page_number > 1:
            raise BadRequest(details='Page number can not be used with with page size 0')

        serializer = self.api_manager.serializer_for(self.model)
        query = search(self.session, self.model, filters=filters, sort=sort)
        query = self._selectinload_included_relationships(query, include, serializer, filters=filters)

        if page_size == 0:
            instances = query.all()
            num_results = len(instances)
            prev = None
            next_ = None
            first = None
            last = None
        else:
            num_results = count(self.session, query)
            first = 1
            if num_results == 0:
                last = 1
            else:
                last = int(math.ceil(num_results / page_size))
            prev = page_number - 1 if page_number > 1 else None
            next_ = page_number + 1 if page_number < last else None
            offset = (page_number - 1) * page_size
            # TODO Use Query.slice() instead, since it's easier to use.
            instances = query.limit(page_size).offset(offset).all()
        data = self._serialize_instances(instances)
        paginated_data = Paginated(data, page_size=page_size, num_results=num_results, next_=next_, prev=prev, first=first, last=last)
        links = {'self': self.api_manager.url_for(self.model)}
        links.update(paginated_data.pagination_links)
        link_header = ','.join(paginated_data.header_links)
        headers = dict(Link=link_header)
        result = {
            'jsonapi': {'version': JSONAPI_VERSION},
            'data': paginated_data.items,
            'links': links,
            'meta': {'total': paginated_data.num_results}
        }

        if include:
            include_set = get_inclusions_for_instances(include, instances)
            include_list = self._serialize_instances(include_set)
            result['included'] = include_list

        for postprocessor in self.postprocessors:
            postprocessor(result=result, filters=filters, sort=sort)
        return result, 200, headers


class FetchResource(FetchView):

    def get_data(self, *args, include=None, resource_id=None, **kwargs) -> ResponseTuple:
        for preprocessor in self.preprocessors:
            temp_result = preprocessor(resource_id=resource_id)
            # Let the return value of the preprocessor be the new value of
            # instid, thereby allowing the preprocessor to effectively specify
            # which instance of the model to process on.
            #
            # We assume that if the preprocessor returns None, it really just
            # didn't return anything, which means we shouldn't overwrite the
            # instid.
            if temp_result is not None:
                resource_id = temp_result

        primary_key = self.api_manager.primary_key_for(self.model)
        query = query_by_primary_key(self.session, self.model, resource_id, primary_key)
        serializer = self.api_manager.serializer_for(self.model)
        query = self._selectinload_included_relationships(query, include, serializer)
        instance = query.first()
        if not instance:
            raise NotFound(details=f'No resource with ID {resource_id}')

        data = self._serialize_instances([instance])
        result = {
            'jsonapi': {'version': JSONAPI_VERSION},
            'data': data[0]
        }

        if include:
            include_set = get_inclusions_for_instances(include, [instance])
            include_set.discard(instance)  # do not duplicate resource itself inside include
            include_list = self._serialize_instances(include_set)
            result['included'] = include_list

        for postprocessor in self.postprocessors:
            postprocessor(result=result)

        return result, 200, {}


class APIBase(ModelView):
    """Base class for view classes that provide fetch, create, update, and
    delete functionality for resources and relationships on resources.

    `session` and `model` are as described in the constructor of the
    superclass.

    `preprocessors` and `postprocessors` are as described in :ref:`processors`.

    `primary_key` is as described in :ref:`primarykey`.

    `validation_exceptions` are as described in :ref:`validation`.

    `allow_to_many_replacement` is as described in :ref:`allowreplacement`.

    """

    #: List of decorators applied to every method of this class.
    decorators = [catch_processing_exceptions] + ModelView.decorators

    def __init__(self, session, model, api_manager, preprocessors=None, postprocessors=None,
                 primary_key=None, serializer=None, deserializer=None,
                 validation_exceptions=None, includes=None, page_size=10,
                 max_page_size=100, allow_to_many_replacement=False, *args,
                 **kw):
        super(APIBase, self).__init__(session, model, *args, **kw)

        #: The name of the collection specified by the given model class
        #: to be used in the URL for the ReSTful API created.
        self.collection_name = api_manager.collection_name(self.model)
        self.api_manager = api_manager

        #: The default set of related resources to include in compound
        #: documents, given as a set of relationship paths.
        self.default_includes = includes
        if self.default_includes is not None:
            self.default_includes = frozenset(self.default_includes)

        #: Whether to allow complete replacement of a to-many relationship when
        #: updating a resource.
        self.allow_to_many_replacement = allow_to_many_replacement

        #: The default page size for responses that consist of a
        #: collection of resources.
        #:
        #: Requests made by clients may override this default by
        #: specifying ``page_size`` as a query parameter.
        self.page_size = page_size

        #: The maximum page size that a client can request.
        #:
        #: Even if a client specifies that greater than `max_page_size`
        #: should be returned, at most `max_page_size` results will be
        #: returned.
        self.max_page_size = max_page_size

        #: A custom serialization function for primary resources; see
        #: :ref:`serialization` for more information.
        #:
        #: This should not be ``None``, unless a subclass is not going to use
        #: serialization.
        self.serializer = serializer

        #: A custom deserialization function for primary resources; see
        #: :ref:`serialization` for more information.
        #:
        #: This should not be ``None``, unless a subclass is not going to use
        #: deserialization.
        self.deserializer = deserializer

        #: The tuple of exceptions that are expected to be raised during
        #: validation when creating or updating a model.
        self.validation_exceptions = tuple(validation_exceptions or ())

        #: The name of the attribute containing the primary key to use as the
        #: ID of the resource.
        self.primary_key = primary_key

        #: The mapping from method name to a list of functions to apply after
        #: the main functionality of that method has been executed.
        self.postprocessors = defaultdict(list, upper(postprocessors or {}))

        #: The mapping from method name to a list of functions to apply before
        #: the main functionality of that method has been executed.
        self.preprocessors = defaultdict(list, upper(preprocessors or {}))

        #: The mapping from resource type name to requested sparse
        #: fields for resources of that type.
        self.sparse_fields = parse_sparse_fields()

        # HACK: We would like to use the :attr:`API.decorators` class attribute
        # in order to decorate each view method with a decorator that catches
        # database integrity errors. However, in order to rollback the session,
        # we need to have a session object available to roll back. Therefore we
        # need to manually decorate each of the view functions here.
        def decorate(name, func):
            return setattr(self, name, func(getattr(self, name)))

        for method in ['get', 'post', 'patch', 'delete']:
            # Check if the subclass has the method before trying to decorate it.
            if hasattr(self, method):
                decorate(method, catch_integrity_errors(self.session))

    def dispatch_request(self, *args, **kwargs):
        try:
            return super().dispatch_request(*args, **kwargs)
        except Error as e:
            return error_response(e.http_code, cause=e.cause, detail=e.details)

    def collection_processor_type(self, *args, **kw):
        """The suffix for the pre- and postprocessor identifiers for
        requests on collections of resources.

        This is an abstract method; subclasses must override this
        method.

        """
        raise NotImplementedError

    def resource_processor_type(self, *args, **kw):
        """The suffix for the pre- and postprocessor identifiers for
        requests on resource objects.

        This is an abstract method; subclasses must override this
        method.

        """
        raise NotImplementedError

    def use_resource_identifiers(self):
        """Whether primary data in responses use resource identifiers or
        full resource objects.

        Subclasses that handle resource linkage should override this
        method so that it returns ``True``.

        """
        return False

    def _handle_validation_exception(self, exception):
        """Rolls back the session, extracts validation error messages, and
        returns an error response with :https:statuscode:`400` containing the
        extracted validation error messages.

        Again, *this method calls
        :meth:`sqlalchemy.orm.session.Session.rollback`*.

        """
        self.session.rollback()
        errors = extract_error_messages(exception)
        if not errors:
            return error_response(400, cause=exception, title='Validation error')
        if isinstance(errors, dict):
            errors = [error(title='Validation error', status=400,
                            detail='{0}: {1}'.format(field, detail))
                      for field, detail in errors.items()]
        current_app.logger.exception(str(exception))
        return errors_response(400, errors)

    def _serialize_many(self, instances, relationship=False):
        """Serializes a list of SQLAlchemy objects.

        `instances` is a list of SQLAlchemy objects of any model class.

        This function returns a list of dictionary objects, each of
        which is the serialized version of the corresponding SQLAlchemy
        model instance from `instances`.

        If `relationship` is ``True``, resource identifier objects will
        be returned instead of resource objects.

        This function raises :exc:`MultipleExceptions` if there is a
        problem serializing one or more of the objects in `instances`.

        """
        result = []
        failed = []
        for instance in instances:
            if instance is None:
                continue
            model = get_model(instance)
            if relationship:
                result.append(self.api_manager.serialize_relationship(instance))
            else:
                # Determine the serializer for this instance. If there
                # is no serializer, use the default serializer for the
                # current resource, even though the current model may
                # different from the model of the current instance.
                serializer = self.api_manager.serializer_for(model)
                # This may raise ValueError
                _type = self.api_manager.collection_name(model)
                # TODO The `only` keyword argument will be ignored when
                # serializing relationships, so we don't really need to
                # recompute this every time.
                only = self.sparse_fields.get(_type)
                try:
                    serialized = serializer.serialize(instance, only=only)
                    result.append(serialized)
                except SerializationException as exception:
                    failed.append(exception)
        if failed:
            raise MultipleExceptions(failed)
        return result

    def get_all_inclusions(self, instance_or_instances):
        """Returns a list of all the requested included resources
        associated with the given instance or instances of a SQLAlchemy
        model.

        ``instance_or_instances`` is either a SQLAlchemy
        :class:`~sqlalchemy.orm.query.Query` object representing
        multiple instances of a SQLAlchemy model, or it is simply one
        instance of a model. These instances represent the resources
        that will be returned as primary data in the JSON API
        response. The resources to include will be computed based on
        these data and the client's ``include`` query parameter.

        This function raises :exc:`MultipleExceptions` if any included
        resource causes a serialization exception. If this exception is
        raised, the :attr:`MultipleExceptions.exceptions` attribute
        contains a list of the :exc:`SerializationException` objects
        that caused it.

        """
        # If `instance_or_instances` is actually just a single instance
        # of a SQLAlchemy model, get the resources to include for that
        # one instance. Otherwise, collect the resources to include for
        # each instance in `instances`.
        if isinstance(instance_or_instances, (Query, list)):
            to_include = set(chain.from_iterable(self.resources_to_include(resource) for resource in instance_or_instances))
        else:
            to_include = self.resources_to_include(instance_or_instances)
        # This may raise MultipleExceptions if there are problems
        # serializing the included resources.
        return self._serialize_many(to_include)

    def _paginated(self, items, filters=None, sort=None):
        """Returns a :class:`Paginated` object representing the
        correctly paginated list of resources to return to the client,
        based on the current request.

        `items` is a SQLAlchemy query, or a Flask-SQLAlchemy query,
        containing all requested elements of a collection regardless of
        the page number or size in the client's request.

        `filters`, and `sort` must have already been
        extracted from the client's request (as by
        :meth:`_collection_parameters`) and applied to the query.

        If `relationship` is ``True``, the resources in the query object
        will be serialized as linkage objects instead of resources
        objects.

        This method serializes the (correct page of) resources. As such,
        it raises an instance of :exc:`MultipleExceptions` if there is a
        problem serializing resources.

        """
        # Determine the client's page size request. Raise an exception
        # if the page size is out of bounds, either too small or too
        # large.
        page_size = int(request.args.get(PAGE_SIZE_PARAM, self.page_size))
        if page_size < 0:
            raise PaginationError('Page size must be a positive integer')
        if page_size > self.max_page_size:
            msg = "Page size must not exceed the server's maximum: {0}"
            msg = msg.format(self.max_page_size)
            raise PaginationError(msg)
        is_relationship = self.use_resource_identifiers()
        # If the page size is 0, just return everything.
        if page_size == 0:
            raw_items = items.all()
            result = self._serialize_many(raw_items, relationship=is_relationship)
            # Use `len()` here instead of doing `count(self.session,
            # items)` because the former should be faster.
            num_results = len(result)
            return Paginated(result, page_size=page_size, num_results=num_results, raw_items=raw_items)
        # Determine the client's page number request. Raise an exception
        # if the page number is out of bounds.
        page_number = int(request.args.get(PAGE_NUMBER_PARAM, 1))
        if page_number < 0:
            raise PaginationError('Page number must be a positive integer')
        # At this point, we know the page size is positive, so we
        # paginate the response.
        #
        # If the query is really a Flask-SQLAlchemy query, we can use
        # its built-in pagination. Otherwise, we need to manually
        # compute the page numbers, the number of results, etc.
        if hasattr(items, 'paginate'):
            pagination = items.paginate(page=page_number, per_page=page_size, error_out=False)
            num_results = pagination.total
            first = 1
            last = pagination.pages
            prev = pagination.prev_num
            next_ = pagination.next_num
            items = pagination.items
        else:
            num_results = count(self.session, items)
            first = 1
            # Handle a special case for an empty collection of items.
            #
            # There will be no division-by-zero error here because we
            # have already checked that page size is not equal to zero
            # above.
            if num_results == 0:
                last = 1
            else:
                last = int(math.ceil(num_results / page_size))
            prev = page_number - 1 if page_number > 1 else None
            next_ = page_number + 1 if page_number < last else None
            offset = (page_number - 1) * page_size
            # TODO Use Query.slice() instead, since it's easier to use.
            items = items.limit(page_size).offset(offset)
        # Serialize the found items. This may raise an exception if
        # there is a problem serializing any of the objects.
        raw_items = items
        result = self._serialize_many(items, relationship=is_relationship)
        # Wrap the list of results in a Paginated object, which
        # represents the result set and stores some extra information
        # about how it was determined.
        return Paginated(result, num_results=num_results, first=first,
                         last=last, next_=next_, prev=prev,
                         page_size=page_size, filters=filters, sort=sort,
                         raw_items=raw_items)

    def _get_resource_helper(self, resource, primary_resource=None,
                             relation_name=None, related_resource=False):
        is_relationship = self.use_resource_identifiers()
        # The resource to serialize may be `None`, if we are fetching a
        # to-one relation that has no value. In this case, the "data"
        # for the JSON API response is just `None`.
        if resource is None:
            data = None
        else:
            # HACK The _serialize_many() method expects a list as input and
            # returns a list as output, but we only need to serialize a
            # single resource here. Thus we provide a list of length one
            # as input and assume a list of length one as output.
            try:
                data = self._serialize_many([resource],
                                            relationship=is_relationship)
            except MultipleExceptions as e:
                return errors_from_serialization_exceptions(e.exceptions)
            data = data[0]
        # Prepare the dictionary that will contain the JSON API response.
        result = {'jsonapi': {'version': JSONAPI_VERSION}, 'meta': {},
                  'links': {}, 'data': data}
        # Determine the top-level links.
        is_relation = primary_resource is not None
        is_related_resource = is_relation and related_resource
        if is_related_resource:
            resource_id = self.api_manager.primary_key_value(primary_resource)
            related_resource_id = self.api_manager.primary_key_value(resource)
            # `self.model` should match `get_model(primary_resource)`
            self_link = self.api_manager.url_for(self.model, resource_id=resource_id, relation_name=relation_name, related_resource_id=related_resource_id)
            result['links']['self'] = self_link
        else:
            resource_id = self.api_manager.primary_key_value(primary_resource)
            # `self.model` should match `get_model(primary_resource)`
            if is_relationship:
                self_link = self.api_manager.url_for(self.model, resource_id=resource_id, relation_name=relation_name, relationship=True)
                related_link = self.api_manager.url_for(self.model, resource_id=resource_id, relation_name=relation_name)
                result['links']['self'] = self_link
                result['links']['related'] = related_link
            else:
                self_link = self.api_manager.url_for(self.model, resource_id=resource_id, relation_name=relation_name)
                result['links']['self'] = self_link

        # Include any requested resources in a compound document.
        try:
            included = self.get_all_inclusions(resource)
        except MultipleExceptions as e:
            # By the way we defined `get_all_inclusions()`, we are
            # guaranteed that each of the underlying exceptions is a
            # `SerializationException`. Thus we can use
            # `errors_from_serialization_exception()`.
            return errors_from_serialization_exceptions(e.exceptions, included=True)
        if included:
            result['included'] = included
        # HACK Need to do this here to avoid a too-long line.
        kw = {'is_relation': is_relation,
              'is_related_resource': is_related_resource}
        # This method could have been called on a request to fetch a
        # single resource, a to-one relation, or a member of a to-many
        # relation.
        processor_type = 'GET_{0}'.format(self.resource_processor_type(**kw))
        for postprocessor in self.postprocessors[processor_type]:
            postprocessor(result=result)
        return result, 200, {}

    def _get_collection_helper(self, resource, relation_name, filters=None, sort=None) -> Tuple[dict, int, dict]:
        # Compute the result of the search on the model.
        is_relation = resource is not None
        model = get_model(resource)
        related_model = get_related_model(model, relation_name)
        query = session_query(self.session, related_model)

        # Filter by only those related values that are related to `instance`.
        relationship = getattr(resource, relation_name)
        primary_keys = {self.api_manager.primary_key_value(inst) for inst in relationship}
        # If the relationship is empty, we can avoid a potentially expensive
        # filtering operation by simply returning an intentionally empty
        # query.
        if not primary_keys:
            query = query.filter(FALSE())
        else:
            query = query.filter(self.api_manager.primary_key_value(related_model).in_(primary_keys))

        search_ = partial(search, self.session, related_model, _initial_query=query)
        try:
            search_items = search_(filters=filters, sort=sort)
        except ComparisonToNull as exception:
            detail = str(exception)
            return error_response(400, cause=exception, detail=detail)

        # Prepare the dictionary that will contain the JSON API response.
        result = {
            'jsonapi': {'version': JSONAPI_VERSION},
        }
        meta = {}
        links = {'self': self.api_manager.url_for(self.model)}

        # Add the primary data (and any necessary links) to the JSON API
        # response object.
        #
        # If the result of the search is a SQLAlchemy query object, we need to
        # return a collection.
        try:
            paginated = self._paginated(search_items, filters=filters, sort=sort)
        except MultipleExceptions as e:
            return errors_from_serialization_exceptions(e.exceptions)
        except PaginationError as exception:
            detail = exception.args[0]
            return error_response(400, cause=exception, detail=detail)
        # Wrap the resulting object or list of objects under a `data` key.
        result['data'] = paginated.items
        # Provide top-level links.
        links.update(paginated.pagination_links)
        result['links'] = links
        link_header = ','.join(paginated.header_links)
        headers = dict(Link=link_header)
        # Add the metadata to the JSON API response object.
        meta['total'] = paginated.num_results
        result['meta'] = meta

        # Determine the resources to include (in a compound document).
        if self.use_resource_identifiers():
            instances = resource
        else:
            instances = paginated.raw_items
        # Include any requested resources in a compound document.
        try:
            included = self.get_all_inclusions(instances)
        except MultipleExceptions as e:
            # By the way we defined `get_all_inclusions()`, we are
            # guaranteed that each of the underlying exceptions is a
            # `SerializationException`. Thus we can use
            # `errors_from_serialization_exception()`.
            return errors_from_serialization_exceptions(e.exceptions,
                                                        included=True)
        if included:
            result['included'] = included

        # This method could have been called on either a request to
        # fetch a collection of resources or a to-many relation.
        processor_type = self.collection_processor_type(is_relation=is_relation)
        for postprocessor in self.postprocessors[f'GET_{processor_type}']:
            postprocessor(result=result, filters=filters, sort=sort)
        return result, 200, headers

    def resources_to_include(self, instance):
        """Returns a set of resources to include in a compound document
        response based on the ``include`` query parameter and the default
        includes specified in the constructor of this class.

        The ``include`` query parameter is as described in the `Inclusion of
        Related Resources`_ section of the JSON API specification. It specifies
        which resources, other than the primary resource or resources, will be
        included in a compound document response.

        .. _Inclusion of Related Resources: https://jsonapi.org/format/#fetching-includes

        """
        # Add any links requested to be included by URL parameters.
        #
        # We expect `toinclude` to be a comma-separated list of relationship
        # paths.
        toinclude = request.args.get('include')
        if toinclude is None and self.default_includes is None:
            return {}
        elif toinclude is None and self.default_includes is not None:
            toinclude = self.default_includes
        else:
            toinclude = set(toinclude.split(','))
        return set(chain.from_iterable(resources_from_path(instance, path) for path in toinclude))
