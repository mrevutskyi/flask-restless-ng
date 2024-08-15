# search.py - searching on SQLAlchemy models
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
"""Provides search queries for SQLAlchemy models.

The :func:`search` function creates a SQLAlchemy query object for a
given set of filters, sorting rules, etc. The
:func:`search_relationship` function creates a query restricted to a
relationship on a particular instance of a SQLAlchemy model.

"""
import inspect

from sqlalchemy import and_
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy.orm import aliased
from sqlalchemy.orm.attributes import InstrumentedAttribute

from .exceptions import BadRequest
from .helpers import get_related_association_proxy_model
from .helpers import get_related_model
from .helpers import primary_key_names
from .helpers import session_query
from .helpers import string_to_datetime

try:
    # SQLAlchemy 1.3+
    from sqlalchemy.ext.associationproxy import ObjectAssociationProxyInstance as AssociationProxy
except ImportError:
    from sqlalchemy.ext.associationproxy import AssociationProxy  # type: ignore


class ComparisonToNull(Exception):
    """Raised when a client attempts to use a filter object that compares a
    resource's attribute to ``NULL`` using the ``==`` operator instead of using
    ``is_null``.

    """
    pass


class UnknownField(Exception):
    """Raised when the user attempts to reference a field that does not
    exist on a model in a search.

    """

    def __init__(self, field):

        #: The name of the unknown attribute.
        self.field = field


def _sub_operator(model, argument, fieldname):
    """Recursively calls :func:`create_operation` when argument is a dictionary
    of the form specified in :ref:`search`.

    This function is for use with the ``has`` and ``any`` search operations.

    """
    if isinstance(model, InstrumentedAttribute):
        submodel = model.property.mapper.class_
    elif isinstance(model, AssociationProxy):
        submodel = get_related_association_proxy_model(model)
    else:
        # TODO what to do here?
        pass
    fieldname = argument['name']
    operator = argument['op']
    argument = argument.get('val')
    return create_operation(submodel, fieldname, operator, argument)


#: The mapping from operator name (as accepted by the search method) to a
#: function which returns the SQLAlchemy expression corresponding to that
#: operator.
#:
#: Each of these functions accepts either one, two, or three arguments. The
#: first argument is the field object on which to apply the operator. The
#: second argument, where it exists, is either the second argument to the
#: operator or a dictionary as described below. The third argument, where it
#: exists, is the name of the field.
#:
#: For functions that accept three arguments, the second argument may be a
#: dictionary containing ``'name'``, ``'op'``, and ``'val'`` mappings so that
#: :func:`create_operation` may be applied recursively. For more information
#: and examples, see :ref:`search`.
#:
#: Some operations have multiple names. For example, the equality operation can
#: be described by the strings ``'=='``, ``'eq'``, ``'equals'``, etc.
OPERATORS = {
    # Operators which accept a single argument.
    'is_null': lambda f: f.is_(None),
    'is_not_null': lambda f: f.isnot(None),
    # 'desc': lambda f: f.desc,
    # 'asc': lambda f: f.asc,
    # Operators which accept two arguments.
    '==': lambda f, a: f == a,
    'eq': lambda f, a: f == a,
    'equals': lambda f, a: f == a,
    'equal_to': lambda f, a: f == a,
    '!=': lambda f, a: f != a,
    'ne': lambda f, a: f != a,
    'neq': lambda f, a: f != a,
    'not_equal_to': lambda f, a: f != a,
    'does_not_equal': lambda f, a: f != a,
    '>': lambda f, a: f > a,
    'gt': lambda f, a: f > a,
    '<': lambda f, a: f < a,
    'lt': lambda f, a: f < a,
    '>=': lambda f, a: f >= a,
    'ge': lambda f, a: f >= a,
    'gte': lambda f, a: f >= a,
    'geq': lambda f, a: f >= a,
    '<=': lambda f, a: f <= a,
    'le': lambda f, a: f <= a,
    'lte': lambda f, a: f <= a,
    'leq': lambda f, a: f <= a,
    '<<': lambda f, a: f.op('<<')(a),
    '<<=': lambda f, a: f.op('<<=')(a),
    '>>': lambda f, a: f.op('>>')(a),
    '>>=': lambda f, a: f.op('>>=')(a),
    '<>': lambda f, a: f.op('<>')(a),
    '&&': lambda f, a: f.op('&&')(a),
    'ilike': lambda f, a: f.ilike(a),
    'like': lambda f, a: f.like(a),
    'not_like': lambda f, a: ~f.like(a),
    'in': lambda f, a: f.in_(a),
    'not_in': lambda f, a: ~f.in_(a),
    'to_tsquery': lambda f, a: f.op('@@')(func.to_tsquery(a)),
    'plainto_tsquery': lambda f, a: f.op('@@')(func.plainto_tsquery(a)),
    '@>': lambda f, a, fn: f.op('@>')(a),
    '<@': lambda f, a, fn: f.op('<@')(a),
    '!@>': lambda f, a, fn: ~f.op('@>')(a),
    '!<@': lambda f, a, fn: ~f.op('<@')(a),
    # Operators which accept three arguments.
    'has': lambda f, a, fn: f.has(_sub_operator(f, a, fn)),
    'any': lambda f, a, fn: f.any(_sub_operator(f, a, fn)),
}


class Filter(object):
    """Represents a filter to apply to a SQLAlchemy query object.

    A filter can be, for example, a comparison operator applied to a field of a
    model and a value or a comparison applied to two fields of the same
    model. For more information on possible filters, see :ref:`search`.

    `fieldname` is the name of the field of a model which will be on the
    left side of the operator.

    `operator` is the string representation of an operator to apply. The
    full list of recognized operators can be found at :ref:`search`.

    If `argument` is specified, it is the value to place on the right side
    of the operator. If `otherfield` is specified, that field on the model
    will be placed on the right side of the operator.

    .. admonition:: About `argument` and `otherfield`

       Some operators don't need either argument and some need exactly one.
       However, this constructor will not raise any errors or otherwise
       inform you of which situation you are in; it is basically just a
       named tuple. Calling code must handle errors caused by missing
       required arguments.

    """

    def __init__(self, fieldname, operator, argument=None, otherfield=None):
        self.fieldname = fieldname
        self.operator = operator
        self.argument = argument
        self.otherfield = otherfield

    # # This is useful for debugging purposes.
    # def __repr__(self):
    #     """Returns a string representation of this object."""
    #     return '<Filter {0} {1} {2}>'.format(self.fieldname, self.operator,
    #                                          self.argument
    #                                          or self.otherfield)

    @staticmethod
    def from_dictionary(model, dictionary):
        """Returns a new :class:`Filter` object with arguments parsed from
        `dictionary`.

        `dictionary` is a dictionary of the form::

            {'name': 'age', 'op': 'lt', 'val': 20}

        or::

            {'name': 'age', 'op': 'lt', 'other': 'height'}

        where ``dictionary['name']`` is the name of the field of the model on
        which to apply the operator, ``dictionary['op']`` is the name of the
        operator to apply, ``dictionary['val']`` is the value on the right to
        which the operator will be applied, and ``dictionary['other']`` is the
        name of the other field of the model to which the operator will be
        applied.

        'dictionary' may also be an arbitrary Boolean formula consisting of
        dictionaries such as these. For example::

            {'or':
                 [{'and':
                       [dict(name='name', op='like', val='%y%'),
                        dict(name='age', op='ge', val=10)]},
                  dict(name='name', op='eq', val='John')
                  ]
             }

        This method raises :exc:`UnknownField` if ``dictionary['name']``
        does not refer to an attribute of `model`.

        """
        # If there are no ANDs or ORs, we are in the base case of the
        # recursion.
        if 'or' not in dictionary and 'and' not in dictionary:
            fieldname = dictionary.get('name')
            if not hasattr(model, fieldname):
                raise UnknownField(fieldname)
            operator = dictionary.get('op')
            otherfield = dictionary.get('field')
            argument = dictionary.get('val')
            # Need to deal with the special case of converting dates.
            argument = string_to_datetime(model, fieldname, argument)
            return Filter(fieldname, operator, argument, otherfield)
        # For the sake of brevity, rename this method.
        from_dict = Filter.from_dictionary
        # If there is an OR or an AND in the dictionary, recurse on the
        # provided list of filters.
        if 'or' in dictionary:
            subfilters = dictionary.get('or')
            return DisjunctionFilter(*[from_dict(model, filter_)
                                       for filter_ in subfilters])
        else:
            subfilters = dictionary.get('and')
            return ConjunctionFilter(*[from_dict(model, filter_)
                                       for filter_ in subfilters])


class JunctionFilter(Filter):
    """A conjunction or disjunction of other filters.

    `subfilters` is a tuple of :class:`Filter` objects.

    """

    def __init__(self, *subfilters):
        self.subfilters = subfilters

    def __iter__(self):
        return iter(self.subfilters)


class ConjunctionFilter(JunctionFilter):
    """A conjunction of other filters."""

    # # This is useful for debugging purposes.
    # def __repr__(self):
    #     return 'and_{0}'.format(tuple(repr(f) for f in self))


class DisjunctionFilter(JunctionFilter):
    """A disjunction of other filters."""

    # # This is useful for debugging purposes.
    # def __repr__(self):
    #     return 'or_{0}'.format(tuple(repr(f) for f in self))


def create_operation(model, fieldname, operator, argument):
    """Translates an operation described as a string to a valid SQLAlchemy
    query parameter using a field of the specified model.

    More specifically, this translates the string representation of an
    operation, for example ``'gt'``, to an expression corresponding to a
    SQLAlchemy expression, ``field > argument``. The recognized operators
    are given by the keys of :data:`OPERATORS`. For more information on
    recognized search operators, see :ref:`search`.

    `model` is an instance of a SQLAlchemy declarative model being
    searched.

    `fieldname` is the name of the field of `model` to which the operation
    will be applied as part of the search.

    `operation` is a string representating the operation which will be
     executed between the field and the argument received. For example,
     ``'gt'``, ``'lt'``, ``'like'``, ``'in'`` etc.

    `argument` is the argument to which to apply the `operator`.

    This function raises the following errors:
    * :exc:`KeyError` if the `operator` is unknown (that is, not in
      :data:`OPERATORS`)
    * :exc:`TypeError` if an incorrect number of arguments are provided for
      the operation (for example, if `operation` is `'=='` but no
      `argument` is provided)
    * :exc:`AttributeError` if no column with name `fieldname` or
      `relation` exists on `model`

    """
    # raises KeyError if operator not in OPERATORS
    opfunc = OPERATORS[operator]
    numargs = len(inspect.getfullargspec(opfunc).args)
    # raises AttributeError if `fieldname` does not exist
    field = getattr(model, fieldname)
    # each of these will raise a TypeError if the wrong number of argments
    # is supplied to `opfunc`.
    if numargs == 1:
        return opfunc(field)
    if argument is None:
        msg = ('To compare a value to NULL, use the is_null/is_not_null '
               'operators.')
        raise ComparisonToNull(msg)
    if numargs == 2:
        return opfunc(field, argument)
    return opfunc(field, argument, fieldname)


def create_filter(model, filt):
    """Returns the operation on `model` specified by the provided filter.

    `filt` is an instance of the :class:`Filter` class.

    Raises one of :exc:`AttributeError`, :exc:`KeyError`, or
    :exc:`TypeError` if there is a problem creating the query. See the
    documentation for :func:`create_operation` for more information.

    """
    # If the filter is not a conjunction or a disjunction, simply proceed
    # as normal.
    if not isinstance(filt, JunctionFilter):
        fname = filt.fieldname
        val = filt.argument
        # get the other field to which to compare, if it exists
        if filt.otherfield:
            val = getattr(model, filt.otherfield)
        # for the sake of brevity...
        return create_operation(model, fname, filt.operator, val)
    # Otherwise, if this filter is a conjunction or a disjunction, make
    # sure to apply the appropriate filter operation.
    if isinstance(filt, ConjunctionFilter):
        return and_(create_filter(model, f) for f in filt)
    return or_(create_filter(model, f) for f in filt)


def search(session, model, filters=None, sort=None, _initial_query=None):
    """Returns a SQLAlchemy query instance with the specified parameters.

    Each instance in the returned query meet the requirements specified by
    ``filters`` and ``sort``.

    This function returns a single instance of the model matching the search
    parameters if ``search_params['single']`` is ``True``, or a list of all
    such instances otherwise. If ``search_params['single']`` is ``True``, then
    this method will raise :exc:`sqlalchemy.orm.exc.NoResultFound` if no
    results are found and :exc:`sqlalchemy.orm.exc.MultipleResultsFound` if
    multiple results are found.

    `model` is the SQLAlchemy model on which to create a query.

    `sort` is a list of two-tuples of the form ``(direction, fieldname)``,
    where ``direction`` is either ``'+'`` or ``'-'`` and ``fieldname`` is a
    string representing an attribute of the model or a dot-separated
    relationship path (for example, ``'owner.name'``).

    If `_initial_query` is provided, the filters, sorting, and grouping
    will be appended to this query. Otherwise, an empty query will be
    created for the specified model.

    When building the query, filters are applied first, then sorting.

    Raises :exc:`UnknownField` if one of the named fields given in one
    of the `filters` does not exist on the `model`.

    Raises one of :exc:`AttributeError`, :exc:`KeyError`, or :exc:`TypeError`
    if there is a problem creating the query. See the documentation for
    :func:`create_operation` for more information.

    """
    if _initial_query is not None:
        query = _initial_query
    else:
        query = session_query(session, model)

    try:
        # Filter the query.
        filters = [Filter.from_dictionary(model, f) for f in filters]

        # This function call may raise an exception.
        filters = [create_filter(model, f) for f in filters]
    except UnknownField as e:
        raise BadRequest(cause=e, details=f'Invalid filter object: No such field "{e.field}"') from e
    except Exception as e:
        raise BadRequest(cause=e, details='Unable to construct query') from e

    query = query.filter(*filters)

    def get_field(obj, name):
        try:
            return getattr(obj, name)
        except AttributeError:
            raise BadRequest(details=f'Invalid sorting: No such field {name}')

    # Order the query. If no order field is specified, order by primary
    # key.
    # if not _ignore_sort:
    if sort:
        for (symbol, field_name) in sort:
            direction_name = 'asc' if symbol == '+' else 'desc'
            related_model = model
            while '.' in field_name:
                field_name, _, field_name_in_relation = field_name.partition('.')
                related_model = aliased(get_related_model(related_model, field_name))
                field_name = field_name_in_relation
                query = query.join(related_model)

            field = get_field(related_model, field_name)
            direction = getattr(field, direction_name)
            query = query.order_by(direction())
    elif sort is not None:
        pks = primary_key_names(model)
        pk_order = (getattr(model, field).asc() for field in pks)
        query = query.order_by(*pk_order)

    return query
