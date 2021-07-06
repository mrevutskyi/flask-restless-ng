# manager.py - class that creates endpoints compliant JSON API
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
"""Provides the main class with which users of Flask-Restless interact.

The :class:`APIManager` class allow users to create ReSTful APIs for
their SQLAlchemy models.

"""
import warnings
from collections import defaultdict
from typing import Dict
from typing import Optional
from uuid import uuid1

from flask import Blueprint
from werkzeug.urls import url_quote_plus

from . import registry
from .helpers import get_model
from .helpers import primary_key_names
from .serialization import DefaultDeserializer
from .serialization import DefaultSerializer
from .serialization import Deserializer
from .serialization import Serializer
from .views import API
from .views import RelationshipAPI
from .views.base import FetchCollection
from .views.base import FetchResource
from .views.function import FunctionAPI

#: The names of HTTP methods that allow fetching information.
READONLY_METHODS = frozenset(('GET', ))

#: The names of HTTP methods that allow creating, updating, or deleting information.
WRITEONLY_METHODS = frozenset(('PATCH', 'POST', 'DELETE'))

#: The set of all recognized HTTP methods.
ALL_METHODS = READONLY_METHODS | WRITEONLY_METHODS


class IllegalArgumentError(Exception):
    """This exception is raised when a calling function has provided illegal
    arguments to a function or method.

    """
    pass


class APIManager:
    """Provides a method for creating a public ReSTful JSON API with respect
    to a given :class:`~flask.Flask` application object.

    The :class:`~flask.Flask` object can either be specified in the
    constructor, or after instantiation time by calling the
    :meth:`init_app` method.

    `app` is the :class:`~flask.Flask` object containing the user's
    Flask application.

    `session` is the :class:`~sqlalchemy.orm.session.Session` object in
    which changes to the database will be made.

    For example, to use this class with models defined in pure SQLAlchemy::

        from flask import Flask
        from flask.ext.restless import APIManager
        from sqlalchemy import create_engine
        from sqlalchemy.orm.session import sessionmaker

        engine = create_engine('sqlite:////tmp/mydb.sqlite')
        Session = sessionmaker(bind=engine)
        my_session = Session()
        app = Flask(__name__)
        api_manager = APIManager(app, session=my_session)

    `url_prefix` is the URL prefix at which each API created by this
    instance will be accessible. For example, if this is set to
    ``'foo'``, then this method creates endpoints of the form
    ``/foo/<collection_name>`` when :meth:`create_api` is called. If the
    `url_prefix` is set in the :meth:`create_api`, the URL prefix set in
    the constructor will be ignored for that endpoint.

    `postprocessors` and `preprocessors` must be dictionaries as
    described in the section :ref:`processors`. These preprocessors and
    postprocessors will be applied to all requests to and responses from
    APIs created using this APIManager object. The preprocessors and
    postprocessors given in these keyword arguments will be prepended to
    the list of processors given for each individual model when using
    the :meth:`create_api_blueprint` method (more specifically, the
    functions listed here will be executed before any functions
    specified in the :meth:`create_api_blueprint` method). For more
    information on using preprocessors and postprocessors, see
    :ref:`processors`.

    `include_links` controls whether to include link objects in resource objects
    https://jsonapi.org/format/#document-links

    """

    def __init__(self, app=None, session=None, preprocessors=None, postprocessors=None, url_prefix='/api', include_links: bool = False):
        if session is None:
            raise ValueError('`session` can not be empty')

        self.app = app

        #: A mapping whose keys are models for which this object has
        #: created an API via the :meth:`create_api_blueprint` method
        #: and whose values are the corresponding collection names for
        #: those models.
        self.created_apis_for: dict = {}

        #: List of blueprints created by :meth:`create_api` to be registered
        #: to the app when calling :meth:`init_app`.
        self.blueprints: list = []

        self.pre = preprocessors or {}
        self.post = postprocessors or {}
        self.session = session

        #: The default URL prefix for APIs created by this manager.
        #:
        #: This can be overridden by the `url_prefix` keyword argument in the
        #: :meth:`create_api` method.
        self.url_prefix = url_prefix

        self.include_links = include_links

    def url_for(self, model, **kw) -> str:
        """Returns the URL for the specified model, similar to
        :func:`flask.url_for`.

        `model` is a SQLAlchemy model class. This must be a model on
        which :meth:`create_api_blueprint` has been invoked previously,
        otherwise a :exc:`KeyError` is raised.

        This method only returns URLs for endpoints created by this
        :class:`APIManager`.

        """
        try:
            url_prefix = self.url_prefix_for(model) or ''
        except KeyError:
            raise ValueError('Model is not registered')
        url_for_collection = f'{url_prefix}/{self.collection_name(model)}'

        resource_id = kw.get('resource_id')

        if not resource_id:
            return url_for_collection

        relation_name = kw.get('relation_name')
        if not relation_name:
            return f'{url_for_collection}/{resource_id}'

        related_resource_id = kw.get('related_resource_id')
        if related_resource_id:
            return f'{url_for_collection}/{resource_id}/{relation_name}/{related_resource_id}'

        relationship = kw.get('relationship')
        if relationship:
            return f'{url_for_collection}/{resource_id}/relationships/{relation_name}'
        return f'{url_for_collection}/{resource_id}/{relation_name}'

    def collection_name(self, model):
        """Returns the collection name for the specified model, as specified by
        the ``collection_name`` keyword argument to
        :meth:`create_api_blueprint`.

        `model` is a SQLAlchemy model class. This must be a model on
        which :meth:`create_api_blueprint` has been invoked previously,
        otherwise a :exc:`KeyError` is raised.

        This method only returns URLs for endpoints created by this
        :class:`APIManager`.

        """
        try:
            return self.created_apis_for[model].collection_name
        except KeyError:
            raise ValueError(f'Model is not registered with the API: {model}')

    def serializer_for(self, model) -> Serializer:
        """Returns the serializer for the specified model, as specified
        by the `serializer` keyword argument to
        :meth:`create_api_blueprint`.

        `model` is a SQLAlchemy model class. This must be a model on
        which :meth:`create_api_blueprint` has been invoked previously,
        otherwise a :exc:`KeyError` is raised.

        This method only returns URLs for endpoints created by this
        :class:`APIManager`.

        """
        return self.created_apis_for[model].serializer

    def primary_key_for(self, instance_or_model):
        """Returns the primary key for the specified model, as specified
        by the `primary_key` keyword argument to
        :meth:`create_api_blueprint`.

        `model` is a SQLAlchemy model class. This must be a model on
        which :meth:`create_api_blueprint` has been invoked previously,
        otherwise a :exc:`KeyError` is raised.

        """
        # TODO: refactor to use model only
        if isinstance(instance_or_model, type):
            model = instance_or_model
        else:
            model = instance_or_model.__class__

        return self.created_apis_for[model].primary_key

    def url_prefix_for(self, model):
        """Returns url_prefix for the specified model, as specified
        by the `url_prefix` keyword argument to
        :meth:`create_api_blueprint`."""
        return self.created_apis_for[model].url_prefix

    def init_app(self, app):

        """Registers any created APIs on the given Flask application.

        This function should only be called if no Flask application was
        provided in the `app` keyword argument to the constructor of
        this class.

        When this function is invoked, any blueprint created by a
        previous invocation of :meth:`create_api` will be registered on
        `app` by calling the :meth:`~flask.Flask.register_blueprint`
        method.

        To use this method with pure SQLAlchemy, for example::

            from flask import Flask
            from flask_restless import APIManager
            from sqlalchemy import create_engine
            from sqlalchemy.orm.session import sessionmaker

            engine = create_engine('sqlite:////tmp/mydb.sqlite')
            Session = sessionmaker(bind=engine)
            mysession = Session()

            # Here create model classes, for example User, Comment, etc.
            ...

            # Create the API manager and create the APIs.
            api_manager = APIManager(session=mysession)
            api_manager.create_api(User)
            api_manager.create_api(Comment)

            # Later, call `init_app` to register the blueprints for the
            # APIs created earlier.
            app = Flask(__name__)
            api_manager.init_app(app)

        and with models defined with Flask-SQLAlchemy::

            from flask import Flask
            from flask_restless import APIManager
            from flask_sqlalchemy import SQLAlchemy

            db = SQLALchemy(app)

            # Here create model classes, for example User, Comment, etc.
            ...

            # Create the API manager and create the APIs.
            api_manager = APIManager(session=db.session)
            api_manager.create_api(User)
            api_manager.create_api(Comment)

            # Later, call `init_app` to register the blueprints for the
            # APIs created earlier.
            app = Flask(__name__)
            api_manager.init_app(app)

        """
        # Register any queued blueprints on the given application.
        for blueprint in self.blueprints:
            app.register_blueprint(blueprint)

    def create_api_blueprint(
            self,
            name: str,
            model,
            methods=READONLY_METHODS,
            url_prefix: Optional[str] = None,
            collection_name: Optional[str] = None,
            only=None,
            exclude=None,
            additional_attributes=None,
            validation_exceptions=None,
            page_size: int = 10,
            max_page_size: int = 100,
            preprocessors=None,
            postprocessors=None,
            primary_key: Optional[str] = None,
            serializer: Serializer = None,
            deserializer: Deserializer = None,
            includes=None,
            allow_to_many_replacement: bool = False,
            allow_delete_from_to_many_relationships: bool = False,
            allow_client_generated_ids: bool = False,
            allow_functions: bool = False
    ):
        """Creates and returns a ReSTful API interface as a blueprint, but does
        not register it on any :class:`flask.Flask` application.

        The endpoints for the API for ``model`` will be available at
        ``<url_prefix>/<collection_name>``. If `collection_name` is
        ``None``, the lowercase name of the provided model class will be
        used instead, as accessed by ``model.__table__.name``. (If any
        black magic was performed on ``model.__table__``, this will be
        reflected in the endpoint URL.) For more information, see
        :ref:`collectionname`.

        This function must be called at most once for each model for which you
        wish to create a ReSTful API. Its behavior (for now) is undefined if
        called more than once.

        This function returns the :class:`flask.Blueprint` object that handles
        the endpoints for the model. The returned :class:`~flask.Blueprint` has
        *not* been registered with the :class:`~flask.Flask` application
        object specified in the constructor of this class, so you will need
        to register it yourself to make it available on the application. If you
        don't need access to the :class:`~flask.Blueprint` object, use
        :meth:`create_api_blueprint` instead, which handles registration
        automatically.

        `name` is the name of the blueprint that will be created.

        `model` is the SQLAlchemy model class for which a ReSTful interface
        will be created.

        `app` is the :class:`Flask` object on which we expect the blueprint
        created in this method to be eventually registered. If not specified,
        the Flask application specified in the constructor of this class is
        used.

        `methods` is a list of strings specifying the HTTP methods that
        will be made available on the ReSTful API for the specified
        model.

        * If ``'GET'`` is in the list, :http:method:`get` requests will
          be allowed at endpoints for collections of resources,
          resources, to-many and to-one relations of resources, and
          particular members of a to-many relation. Furthermore,
          relationship information will be accessible. For more
          information, see :ref:`fetching`.
        * If ``'POST'`` is in the list, :http:method:`post` requests
          will be allowed at endpoints for collections of resources. For
          more information, see :ref:`creating`.
        * If ``'DELETE'`` is in the list, :http:method:`delete` requests
          will be allowed at endpoints for individual resources. For
          more information, see :ref:`deleting`.
        * If ``'PATCH'`` is in the list, :http:method:`patch` requests
          will be allowed at endpoints for individual
          resources. Replacing a to-many relationship when issuing a
          request to update a resource can be enabled by setting
          ``allow_to_many_replacement`` to ``True``.

          Furthermore, to-one relationships can be updated at
          the relationship endpoints under an individual resource via
          :http:method:`patch` requests. This also allows you to add to
          a to-many relationship via the :http:method:`post` method,
          delete from a to-many relationship via the
          :http:method:`delete` method (if
          ``allow_delete_from_to_many_relationships`` is set to
          ``True``), and replace a to-many relationship via the
          :http:method:`patch` method (if ``allow_to_many_replacement``
          is set to ``True``). For more information, see :ref:`updating`
          and :ref:`updatingrelationships`.

        The default set of methods provides a read-only interface (that is,
        only :http:method:`get` requests are allowed).

        `url_prefix` is the URL prefix at which this API will be
        accessible. For example, if this is set to ``'/foo'``, then this
        method creates endpoints of the form
        ``/foo/<collection_name>``. If not set, the default URL prefix
        specified in the constructor of this class will be used. If that
        was not set either, the default ``'/api'`` will be used.

        `collection_name` is the name of the collection specified by the
        given model class to be used in the URL for the ReSTful API
        created. If this is not specified, the lowercase name of the
        model will be used. For example, if this is set to ``'foo'``,
        then this method creates endpoints of the form ``/api/foo``,
        ``/api/foo/<id>``, etc.

        If `only` is not ``None``, it must be a list of columns and/or
        relationships of the specified `model`, given either as strings or as
        the attributes themselves. If it is a list, only these fields will
        appear in the resource object representation of an instance of `model`.
        In other words, `only` is a whitelist of fields. The ``id`` and
        ``type`` elements of the resource object will always be present
        regardless of the value of this argument. If `only` contains a string
        that does not name a column in `model`, it will be ignored.

        If `additional_attributes` is a list of strings, these
        attributes of the model will appear in the JSON representation
        of an instance of the model. This is useful if your model has an
        attribute that is not a SQLAlchemy column but you want it to be
        exposed. If any of the attributes does not exist on the model, a
        :exc:`AttributeError` is raised.

        If `exclude` is not ``None``, it must be a list of columns and/or
        relationships of the specified `model`, given either as strings or as
        the attributes themselves. If it is a list, all fields **except** these
        will appear in the resource object representation of an instance of
        `model`. In other words, `exclude` is a blacklist of fields. The ``id``
        and ``type`` elements of the resource object will always be present
        regardless of the value of this argument. If `exclude` contains a
        string that does not name a column in `model`, it will be ignored.

        If either `only` or `exclude` is not ``None``, exactly one of them must
        be specified; if both are not ``None``, then this function will raise a
        :exc:`IllegalArgumentError`.

        See :ref:`sparse` for more information on specifying which fields will
        be included in the resource object representation.

        `validation_exceptions` is the tuple of possible exceptions raised by
        validation of your database models. If this is specified, validation
        errors will be captured and forwarded to the client in the format
        described by the JSON API specification. For more information on how to
        use validation, see :ref:`validation`.

        `page_size` must be a positive integer that represents the default page
        size for responses that consist of a collection of resources. Requests
        made by clients may override this default by specifying ``page_size``
        as a query parameter. `max_page_size` must be a positive integer that
        represents the maximum page size that a client can request. Even if a
        client specifies that greater than `max_page_size` should be returned,
        at most `max_page_size` results will be returned. For more information,
        see :ref:`pagination`.

        `serializer` and `deserializer` are custom serialization
        classes. See :ref:`serialization`.

        `preprocessors` is a dictionary mapping strings to lists of
        functions. Each key represents a type of endpoint (for example,
        ``'GET_RESOURCE'`` or ``'GET_COLLECTION'``). Each value is a list of
        functions, each of which will be called before any other code is
        executed when this API receives the corresponding HTTP request. The
        functions will be called in the order given here. The `postprocessors`
        keyword argument is essentially the same, except the given functions
        are called after all other code. For more information on preprocessors
        and postprocessors, see :ref:`processors`.

        `primary_key` is a string specifying the name of the column of `model`
        to use as the primary key for the purposes of creating URLs. If the
        `model` has exactly one primary key, there is no need to provide a
        value for this. If `model` has two or more primary keys, you must
        specify which one to use. For more information, see :ref:`primarykey`.

        `includes` must be a list of strings specifying which related resources
        will be included in a compound document by default when fetching a
        resource object representation of an instance of `model`. Each element
        of `includes` is the name of a field of `model` (that is, either an
        attribute or a relationship). For more information, see
        :ref:`includes`.

        If `allow_to_many_replacement` is ``True`` and this API allows
        :http:method:`patch` requests, the server will allow two types
        of requests.  First, it allows the client to replace the entire
        collection of resources in a to-many relationship when updating
        an individual instance of the model. Second, it allows the
        client to replace the entire to-many relationship when making a
        :http:method:`patch` request to a to-many relationship endpoint.
        This is ``False`` by default. For more information, see
        :ref:`updating` and :ref:`updatingrelationships`.

        If `allow_delete_from_to_many_relationships` is ``True`` and
        this API allows :http:method:`patch` requests, the server will
        allow the client to delete resources from any to-many
        relationship of the model. This is ``False`` by default. For
        more information, see :ref:`updatingrelationships`.

        If `allow_client_generated_ids` is ``True`` and this API allows
        :http:method:`post` requests, the server will allow the client to
        specify the ID for the resource to create. JSON API recommends that
        this be a UUID. This is ``False`` by default. For more information, see
        :ref:`creating`.

        If `allow_functions` is ``True``, then :http:method:`get`
        requests to ``/api/eval/<collection_name>`` will return the
        result of evaluating SQL functions specified in the body of the
        request. For information on the request format, see
        :ref:`functionevaluation`. This is ``False`` by default.

        .. warning::

           This is deprecated and going to be removed in the next major version

        .. warning::

           If ``allow_functions`` is ``True``, you must not create an
           API for a model whose name is ``'eval'``.
        """
        # Perform some sanity checks on the provided keyword arguments.
        if only is not None and exclude is not None:
            msg = 'Cannot simultaneously specify both `only` and `exclude`'
            raise IllegalArgumentError(msg)
        if not hasattr(model, 'id') and len(primary_key_names(model)) == 0:
            msg = 'Provided model must have an `id` attribute or a primary key'
            raise IllegalArgumentError(msg)
        if collection_name == '':
            msg = 'Collection name must be nonempty'
            raise IllegalArgumentError(msg)
        if collection_name is None:
            collection_name = model.__table__.name

        # convert all method names to upper case
        methods = frozenset((m.upper() for m in methods))
        # the name of the API, for use in creating the view and the blueprint
        api_name = f'{collection_name}_api'
        # Prepend the universal preprocessors and postprocessors specified in
        # the constructor of this class.
        preprocessors_: Dict[str, list] = defaultdict(list)
        postprocessors_: Dict[str, list] = defaultdict(list)
        preprocessors_.update(preprocessors or {})
        postprocessors_.update(postprocessors or {})

        for key, value in self.pre.items():
            preprocessors_[key] = value + preprocessors_[key]

        for key, value in self.post.items():
            postprocessors_[key] = value + postprocessors_[key]

        # Validate that all the additional attributes exist on the model.
        if additional_attributes is not None:
            for attr in additional_attributes:
                if not hasattr(model, attr):
                    raise AttributeError(f'no attribute "{attr}" on model {model}')

        # find the primary_key of the model or try and use 'id'
        if primary_key is None:
            pk_names = primary_key_names(model)
            if len(pk_names) > 0:
                primary_key = pk_names[0]
            else:
                primary_key = 'id'

        # Create a default serializer and deserializer if none have been
        # provided.
        if serializer is None:
            serializer = DefaultSerializer(model, collection_name, self, primary_key=primary_key,
                                           only=only, exclude=exclude, additional_attributes=additional_attributes)

        session = self.session
        if deserializer is None:
            deserializer = DefaultDeserializer(self.session, model, self, allow_client_generated_ids=allow_client_generated_ids)
        # Create the view function for the API for this model.
        api_view = API.as_view(api_name, session, model, self,
                               # Keyword arguments for APIBase.__init__()
                               preprocessors=preprocessors_,
                               postprocessors=postprocessors_,
                               primary_key=primary_key,
                               validation_exceptions=validation_exceptions,
                               allow_to_many_replacement=allow_to_many_replacement,
                               # Keyword arguments for API.__init__()
                               page_size=page_size,
                               max_page_size=max_page_size,
                               serializer=serializer,
                               deserializer=deserializer,
                               includes=includes)

        # add the URL rules to the blueprint: the first is for methods on the
        # collection only, the second is for methods which may or may not
        # specify an instance, the third is for methods which must specify an
        # instance

        if url_prefix is None:
            prefix = self.url_prefix
        else:
            prefix = url_prefix

        blueprint = Blueprint(name, __name__, url_prefix=prefix)
        add_rule = blueprint.add_url_rule

        # The URLs that will be routed below.
        collection_url = f'/{collection_name}'
        resource_url = f'{collection_url}/<resource_id>'
        related_resource_url = f'{resource_url}/<relation_name>'
        to_many_resource_url = f'{related_resource_url}/<related_resource_id>'
        relationship_url = f'{resource_url}/relationships/<relation_name>'

        # Create relationship URL endpoints.
        #
        # Due to a limitation in Flask's routing (which is actually
        # Werkzeug's routing), this needs to be declared *before* the
        # rest of the API views. Otherwise, requests like
        # :http:get:`/api/articles/1/relationships/author` interpret the
        # word `relationships` as the name of a relation of an article
        # object.
        relationship_api_name = f'{api_name}_relationships'

        relationship_api_view = RelationshipAPI.as_view(
            relationship_api_name, session, model, self,
            # Keyword arguments for APIBase.__init__()
            preprocessors=preprocessors_,
            postprocessors=postprocessors_,
            primary_key=primary_key,
            validation_exceptions=validation_exceptions,
            allow_to_many_replacement=allow_to_many_replacement,
            # Keyword arguments RelationshipAPI.__init__()
            allow_delete_from_to_many_relationships=allow_delete_from_to_many_relationships
        )
        # When PATCH is allowed, certain non-PATCH requests are allowed
        # on relationship URLs.
        relationship_methods = READONLY_METHODS & methods
        if 'PATCH' in methods:
            relationship_methods |= WRITEONLY_METHODS
        add_rule(relationship_url, methods=relationship_methods,
                 view_func=relationship_api_view)

        get_collection_function = FetchCollection.as_view(
            name=f'{collection_name}_get_collection',
            session=session,
            model=model,
            api_manager=self,
            preprocessors=preprocessors_['GET_COLLECTION'],
            postprocessors=postprocessors_['GET_COLLECTION'],
            max_page_size=max_page_size,
            page_size=page_size,
            includes=includes
        )
        if 'GET' in methods:
            add_rule(collection_url, view_func=get_collection_function, methods=['GET'])

        get_resource_function = FetchResource.as_view(
            name=f'{collection_name}_get_resource',
            session=session,
            model=model,
            api_manager=self,
            preprocessors=preprocessors_['GET_RESOURCE'],
            postprocessors=postprocessors_['GET_RESOURCE'],
            includes=includes
        )

        # The URL for accessing the entire collection. (POST is special because
        # the :meth:`API.post` method doesn't have any arguments.)
        #
        # For example, /api/people.
        collection_methods = frozenset(('POST', )) & methods
        add_rule(collection_url, view_func=api_view,
                 methods=collection_methods)

        # The URL for accessing a single resource. (DELETE and PATCH are
        # special because the :meth:`API.delete` and :meth:`API.patch` methods
        # don't have the `relationname` and `relationinstid` arguments.)
        #
        # For example, /api/people/1.
        resource_methods = frozenset(('DELETE', 'PATCH')) & methods
        add_rule(resource_url, view_func=api_view, methods=resource_methods)
        resource_methods = READONLY_METHODS & methods
        add_rule(resource_url, view_func=get_resource_function, methods=resource_methods)

        # The URL for accessing a related resource, which may be a to-many or a
        # to-one relationship.
        #
        # For example, /api/people/1/articles.
        related_resource_methods = READONLY_METHODS & methods
        related_resource_defaults = dict(related_resource_id=None)
        add_rule(related_resource_url, view_func=api_view,
                 methods=related_resource_methods,
                 defaults=related_resource_defaults)

        # The URL for accessing a to-many related resource.
        #
        # For example, /api/people/1/articles/1.
        to_many_resource_methods = READONLY_METHODS & methods
        add_rule(to_many_resource_url, view_func=api_view,
                 methods=to_many_resource_methods)

        # if function evaluation is allowed, add an endpoint at /api/eval/...
        # which responds only to GET requests and responds with the result of
        # evaluating functions on all instances of the specified model
        if allow_functions:
            warnings.warn('`allow_functions` is deprecated and will be removed in the next major release', DeprecationWarning)
            eval_api_view = FunctionAPI.as_view(f'{api_name}_eval', session, model)
            blueprint.add_url_rule(f'/eval{collection_url}', methods=['GET'], view_func=eval_api_view)

        # Finally, record that this APIManager instance has created an API for
        # the specified model.
        api_info = registry.APIInfo(collection_name, blueprint.name, serializer, primary_key, prefix)
        self.created_apis_for[model] = api_info
        registry.add(model, api_info)
        return blueprint

    def serialize_relationship(self, instance):
        model = get_model(instance)
        return {
            'id': str(getattr(instance, self.primary_key_for(model))),
            'type': self.collection_name(model)
        }

    def primary_key_value(self, instance, as_string=False):
        """Returns the value of the primary key field of the specified `instance`
        of a SQLAlchemy model.

        This is a convenience function for::

            getattr(instance, primary_key_name(instance))

        If `as_string` is ``True``, try to coerce the return value to a string.

        """

        result = getattr(instance, self.primary_key_for(instance))
        if not as_string:
            return result
        try:
            return str(result)
        except UnicodeEncodeError:
            return url_quote_plus(result.encode('utf-8'))

    def create_api(self, *args, **kw):
        """Creates and possibly registers a ReSTful API blueprint for
        the given SQLAlchemy model.

        If a Flask application was provided in the constructor of this
        class, the created blueprint is immediately registered on that
        application. Otherwise, the blueprint is stored for later
        registration when the :meth:`init_app` method is invoked. In
        that case, the blueprint will be registered each time the
        :meth:`init_app` method is invoked.

        The keyword arguments for this method are exactly the same as
        those for :meth:`create_api_blueprint`, and are passed directly
        to that method. However, unlike that method, this method accepts
        only a single positional argument, `model`, the SQLAlchemy model
        for which to create the API. A UUID will be automatically
        generated for the blueprint name.

        For example, if you only wish to create APIs on a single Flask
        application::

            app = Flask(__name__)
            session = ...  # create the SQLAlchemy session
            manager = APIManager(app=app, session=session)
            manager.create_api(User)

        If you want to create APIs before having access to a Flask
        application, you can call this method before calling
        :meth:`init_app`::

            session = ...  # create the SQLAlchemy session
            manager = APIManager(session=session)
            manager.create_api(User)

            # later...
            app = Flask(__name__)
            manager.init_app(app)

        If you want to create an API and register it on multiple Flask
        applications, you can call this method once and :meth:`init_app`
        multiple times with different `app` arguments::

            session = ...  # create the SQLAlchemy session
            manager = APIManager(session=session)
            manager.create_api(User)

            # later...
            app1 = Flask('application1')
            app2 = Flask('application2')
            manager.init_app(app1)
            manager.init_app(app2)

        """
        blueprint_name = str(uuid1())
        blueprint = self.create_api_blueprint(blueprint_name, *args, **kw)
        # Store the created blueprint
        self.blueprints.append(blueprint)
        # If a Flask application was provided in the constructor of this
        # API manager, then immediately register the blueprint on that
        # application.
        if self.app is not None:
            self.app.register_blueprint(blueprint)
