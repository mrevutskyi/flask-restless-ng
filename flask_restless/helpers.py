# helpers.py - helper functions for Flask-Restless
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
"""Helper functions for Flask-Restless."""
import datetime
import inspect
from functools import lru_cache
from itertools import chain
from typing import Any
from typing import Dict
from typing import Generator
from typing import Iterable
from typing import List
from typing import Set

from dateutil.parser import parse as parse_datetime
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import Interval
from sqlalchemy import Time
from sqlalchemy.exc import NoInspectionAvailable
from sqlalchemy.ext.hybrid import HYBRID_PROPERTY
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.inspection import inspect as sqlalchemy_inspect
from sqlalchemy.orm import ColumnProperty
from sqlalchemy.orm import RelationshipProperty as RelProperty
from sqlalchemy.orm import class_mapper
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.orm.attributes import QueryableAttribute
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import ColumnElement

try:
    # SQLAlchemy 1.3+
    from sqlalchemy.ext.associationproxy import ObjectAssociationProxyInstance as AssociationProxyType
except ImportError:
    from sqlalchemy.ext.associationproxy import AssociationProxy as AssociationProxyType  # type: ignore

#: Names of attributes which should definitely not be considered relations when
#: dynamically computing a list of relations of a SQLAlchemy model.
RELATION_BLACKLIST = ('query', 'query_class', '_sa_class_manager',
                      '_decl_class_registry')

#: Types which should be considered columns of a model when iterating over all
#: attributes of a model class.
COLUMN_TYPES = (InstrumentedAttribute, hybrid_property)

#: Strings which, when received by the server as the value of a date or time
#: field, indicate that the server should use the current time when setting the
#: value of the field.
CURRENT_TIME_MARKERS = ('CURRENT_TIMESTAMP', 'CURRENT_DATE', 'LOCALTIMESTAMP')


def session_query(session, model):
    """Returns a SQLAlchemy query object for the specified `model`.

    If `model` has a ``query`` attribute already, ``model.query`` will be
    returned. If the ``query`` attribute is callable ``model.query()`` will be
    returned instead.

    If `model` has no such attribute, a query based on `session` will be
    created and returned.

    """
    if hasattr(model, 'query'):
        if callable(model.query):
            query = model.query()
        else:
            query = model.query
        if hasattr(query, 'filter'):
            return query
    return session.query(model)


def get_relations(model):
    """Returns a list of relation names of `model` (as a list of strings)."""
    return [k for k in dir(model)
            if not (k.startswith('_') or k in RELATION_BLACKLIST)
            and get_related_model(model, k)]


@lru_cache()
def get_related_model(model, relationname):
    """Gets the class of the model to which `model` is related by the attribute
    whose name is `relationname`.

    For example, if we have the model classes ::

        class Person(Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            articles = relationship('Article')

        class Article(Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship('Person')

    then

        >>> get_related_model(Person, 'articles')
        <class 'Article'>
        >>> get_related_model(Article, 'author')
        <class 'Person'>

    """
    if hasattr(model, relationname):
        # inspector = sqlalchemy_inspect(model)
        # attributes = inspector.attrs
        # if relationname in attributes:
        #     state = attributes[relationname]
        attr = getattr(model, relationname)
        if hasattr(attr, 'property') \
                and isinstance(attr.property, RelProperty):
            return attr.property.mapper.class_
        if isinstance(attr, AssociationProxyType):
            return get_related_association_proxy_model(attr)
    return None


def get_related_association_proxy_model(attr):
    """Returns the model class specified by the given SQLAlchemy relation
    attribute, or ``None`` if no such class can be inferred.

    `attr` must be a relation attribute corresponding to an association proxy.

    """
    prop = attr.remote_attr.property
    for attribute in ('mapper', 'parent'):
        if hasattr(prop, attribute):
            return getattr(prop, attribute).class_


def foreign_key_columns(model):
    """Returns a list of the :class:`sqlalchemy.Column` objects that contain
    foreign keys for relationships in the specified model class.

    """
    try:
        inspector = sqlalchemy_inspect(model)
    except NoInspectionAvailable:
        # Well, the inspection of a model class returns a mapper anyway, so
        # let's just assume the inspection would have returned the mapper.
        inspector = class_mapper(model)
    all_columns = inspector.columns
    return [c for c in all_columns if c.foreign_keys]


def foreign_keys(model):
    """Returns a list of the names of columns that contain foreign keys for
    relationships in the specified model class.

    """
    return [column.name for column in foreign_key_columns(model)]


def has_field(model, fieldname):
    """Returns ``True`` if the `model` has the specified field or if it has a
    settable hybrid property for this field name.

    """
    descriptors = sqlalchemy_inspect(model).all_orm_descriptors._data
    if fieldname in descriptors and hasattr(descriptors[fieldname], 'fset'):
        return descriptors[fieldname].fset is not None
    return hasattr(model, fieldname)


def get_field_type(model, fieldname):
    """Helper which returns the SQLAlchemy type of the field."""
    field = getattr(model, fieldname)
    if isinstance(field, ColumnElement):
        return field.type
    if isinstance(field, AssociationProxyType):
        field = field.remote_attr
    if hasattr(field, 'property'):
        prop = field.property
        if isinstance(prop, RelProperty):
            return None
        return prop.columns[0].type
    return None


def attribute_columns(model) -> List[str]:
    """Returns a list of model's column names that should be considered as attributes."""
    inspected_model = sqlalchemy_inspect(model)
    column_attrs = inspected_model.column_attrs.keys()
    descriptors = inspected_model.all_orm_descriptors.items()
    hybrid_columns = [k for k, d in descriptors if d.extension_type == HYBRID_PROPERTY]

    return column_attrs + hybrid_columns


@lru_cache()
def primary_key_names(model):
    """Returns all the primary keys for a model."""
    return [key for key, field in inspect.getmembers(model)
            if isinstance(field, QueryableAttribute)
            and hasattr(field, 'property')
            and isinstance(field.property, ColumnProperty)
            and field.property.columns[0].primary_key]


def is_proxy(value: Any) -> bool:
    return isinstance(value, AssociationProxyType)


def is_like_list(instance, relation):
    """Returns ``True`` if and only if the relation of `instance` whose name is
    `relation` is list-like.

    A relation may be like a list if, for example, it is a non-lazy one-to-many
    relation, or it is a dynamically loaded one-to-many.

    """
    if relation in instance._sa_class_manager:
        return instance._sa_class_manager[relation].property.uselist
    elif hasattr(instance, relation):
        attr = getattr(instance._sa_instance_state.class_, relation)
        if hasattr(attr, 'property'):
            return attr.property.uselist
    related_value = getattr(type(instance), relation, None)
    if is_proxy(related_value):
        local_prop = related_value.local_attr.prop
        if isinstance(local_prop, RelProperty):
            return local_prop.uselist
    return False


def query_by_primary_key(session, model, pk_value, primary_key=None):
    """Returns a SQLAlchemy query object containing the result of querying
    `model` for instances whose primary key has the value `pk_value`.

    If `primary_key` is specified, the column specified by that string is used
    as the primary key column. Otherwise, the column named ``id`` is used.

    Presumably, the returned query should have at most one element.

    """
    pk_name = primary_key
    query = session_query(session, model)
    return query.filter(getattr(model, pk_name) == pk_value)


def get_inclusions_for_instances(include: Set[str], instances) -> Set:
    inclusion_tree: Dict[str, dict] = dict()
    for path in include:
        tree = path.split('.')
        current_tree = inclusion_tree
        for level in tree:
            current_tree[level] = current_tree.get(level, {})
            current_tree = current_tree[level]

    return set(chain.from_iterable(get_inclusions(inclusion_tree, instances)))


def get_inclusions(inclusion_tree: Dict[str, dict], instances: Iterable) -> Generator:
    stack = []
    while True:
        for key, sub_tree in inclusion_tree.items():
            new_instances = set()
            for instance in instances:
                included_instance = getattr(instance, key)
                if not included_instance:
                    continue
                if is_like_list(instance, key):
                    new_instances.update(set(included_instance))
                else:
                    new_instances.add(included_instance)
            if sub_tree and new_instances:
                stack.append((sub_tree, new_instances))
            yield new_instances
        if not stack:
            break
        inclusion_tree, instances = stack.pop()


def get_by(session, model, pk_value, primary_key):
    """Returns the first instance of `model` whose primary key has the value
    `pk_value`, or ``None`` if no such instance exists.

    If `primary_key` is specified, the column specified by that string is used
    as the primary key column. Otherwise, the column named ``id`` is used.

    """
    result = query_by_primary_key(session, model, pk_value, primary_key)
    return result.first()


def string_to_datetime(model, fieldname, value):
    """Casts `value` to a :class:`datetime.datetime` or
    :class:`datetime.timedelta` object if the given field of the given
    model is a date-like or interval column.

    If the field name corresponds to a field in the model which is a
    :class:`sqlalchemy.types.Date`, :class:`sqlalchemy.types.DateTime`,
    or :class:`sqlalchemy.Interval`, then the returned value will be the
    :class:`datetime.datetime` or :class:`datetime.timedelta` Python
    object corresponding to `value`. Otherwise, the `value` is returned
    unchanged.

    """
    if value is None:
        return value
    # If this is a date, time or datetime field, parse it and convert it to
    # the appropriate type.
    field_type = get_field_type(model, fieldname)
    if isinstance(field_type, (Date, Time, DateTime)):
        # If the string is empty, no datetime can be inferred from it.
        if value.strip() == '':
            return None
        # If the string is a string indicating that the value of should be the
        # current datetime on the server, get the current datetime that way.
        if value in CURRENT_TIME_MARKERS:
            return getattr(func, value.lower())()
        value_as_datetime = parse_datetime(value)
        # If the attribute on the model needs to be a Date or Time object as
        # opposed to a DateTime object, just get the date component of the
        # datetime.
        if isinstance(field_type, Date):
            return value_as_datetime.date()
        if isinstance(field_type, Time):
            return value_as_datetime.timetz()
        return value_as_datetime
    # If this is an Interval field, convert the integer value to a timedelta.
    if isinstance(field_type, Interval) and isinstance(value, int):
        return datetime.timedelta(seconds=value)
    # In any other case, simply copy the value unchanged.
    return value


def strings_to_datetimes(model, dictionary):
    """Returns a new dictionary with all the mappings of `dictionary` but
    with date strings and intervals mapped to :class:`datetime.datetime` or
    :class:`datetime.timedelta` objects.

    The keys of `dictionary` are names of fields in the model specified in the
    constructor of this class. The values are values to set on these fields. If
    a field name corresponds to a field in the model which is a
    :class:`sqlalchemy.types.Date`, :class:`sqlalchemy.types.DateTime`, or
    :class:`sqlalchemy.Interval`, then the returned dictionary will have the
    corresponding :class:`datetime.datetime` or :class:`datetime.timedelta`
    Python object as the value of that mapping in place of the string.

    This function outputs a new dictionary; it does not modify the argument.

    """
    return {k: string_to_datetime(model, k, v) for k, v in dictionary.items() if k not in ('type', 'links')}


def get_model(instance):
    """Returns the model class of which the specified object is an instance."""
    return type(instance)
