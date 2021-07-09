# serialization.py - JSON serialization for SQLAlchemy models
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
"""Classes for JSON serialization of SQLAlchemy models.

The abstract base classes :class:`Serializer` and :class:`Deserializer`
can be used to implement custom serialization from and deserialization
to SQLAlchemy objects. The :class:`DefaultSerializer` and
:class:`DefaultDeserializer` provide some basic serialization and
deserialization as expected by classes that follow the JSON API
protocol.

"""
import enum
from abc import ABC
from abc import abstractmethod
from collections import namedtuple
from copy import copy
from datetime import date
from datetime import datetime
from datetime import time
from datetime import timedelta
from typing import Any
from typing import Dict
from typing import FrozenSet
from typing import Optional
from urllib.parse import urljoin

from flask import request
from sqlalchemy import Column
from sqlalchemy import inspect
from sqlalchemy.orm.base import MANYTOONE

from .helpers import attribute_columns
from .helpers import foreign_keys
from .helpers import get_by
from .helpers import get_related_model
from .helpers import get_relations
from .helpers import has_field
from .helpers import is_like_list
from .helpers import primary_key_names
from .helpers import strings_to_datetimes

#: Names of columns which should definitely not be considered user columns to
#: be included in a dictionary representation of a model.
COLUMN_BLACKLIST = ('_sa_polymorphic_on', )

RelationshipInfo = namedtuple('RelationshipInfo', ['foreign_key', 'target_model'])


class SerializationException(Exception):
    """Raised when there is a problem serializing an instance of a
    SQLAlchemy model to a dictionary representation.

    `instance` is the (problematic) instance on which
    :meth:`Serializer.__call__` was invoked.

    `message` is an optional string describing the problem in more
    detail.

    `resource` is an optional partially-constructed serialized
    representation of ``instance``.

    Each of these keyword arguments is stored in a corresponding
    instance attribute so client code can access them.

    """

    def __init__(self, instance, message=None, resource=None, resource_type=None, resource_id=None, *args, **kw):
        super(SerializationException, self).__init__(*args, **kw)
        self.resource = resource
        self.message = message
        self.instance = instance
        self.resource_type = resource_type
        self.resource_id = resource_id


class DeserializationException(Exception):
    """Raised when there is a problem deserializing a Python dictionary to an
    instance of a SQLAlchemy model.

    Subclasses that wish to provide more detailed about the problem
    should set the ``detail`` attribute to be a string, either as a
    class-level attribute or as an instance attribute.

    """

    def __init__(self, *args, **kw):
        super(DeserializationException, self).__init__(*args, **kw)

        #: A string describing the problem in more detail.
        #:
        #: Subclasses must set this attribute to be a string describing
        #: the problem that cause this exception.
        self.detail = None

    def message(self):
        """Returns a more detailed description of the problem as a
        string.

        """
        base = 'Failed to deserialize object'
        if self.detail is not None:
            return '{0}: {1}'.format(base, self.detail)
        return base


class ClientGeneratedIDNotAllowed(DeserializationException):
    """Raised when attempting to deserialize a resource that provides
    an ID when an ID is not allowed.

    """

    def __init__(self, *args, **kw):
        super(ClientGeneratedIDNotAllowed, self).__init__(*args, **kw)

        self.detail = 'Server does not allow client-generated IDS'


class ConflictingType(DeserializationException):
    """Raised when attempting to deserialize a linkage object with an
    unexpected ``'type'`` key.

    `relation_name` is a string representing the name of the
    relationship for which a linkage object has a conflicting type.

    `expected_type` is a string representing the expected type of the
    related resource.

    `given_type` is is a string representing the given value of the
    ``'type'`` element in the resource.

    """

    def __init__(self, expected_type, given_type, relation_name=None, *args,
                 **kw):
        super(ConflictingType, self).__init__(*args, **kw)

        #: The name of the relationship with a conflicting type.
        self.relation_name = relation_name

        #: The expected type name for the related model.
        self.expected_type = expected_type

        #: The type name given by the client for the related model.
        self.given_type = given_type

        if relation_name is None:
            detail = 'expected type "{0}" but got type "{1}"'
            detail = detail.format(expected_type, given_type)
        else:
            detail = ('expected type "{0}" but got type "{1}" in linkage'
                      ' object for relationship "{2}"')
            detail = detail.format(expected_type, given_type, relation_name)
        self.detail = detail


class UnknownField(DeserializationException):
    """Raised when attempting to deserialize an object that references a
    field that does not exist on the model.

    `field` is the name of the unknown field as a string.

    """

    #: Whether the unknown field is given as a field or a relationship.
    #:
    #: This attribute can only take one of the two values ``'field'`` or
    #: ``'relationship'``.
    field_type: Optional[str] = None

    def __init__(self, field, *args, **kw):
        super(UnknownField, self).__init__(*args, **kw)

        #: The name of the unknown field, as a string.
        self.field = field

        self.detail = 'model has no {0} "{1}"'.format(self.field_type, field)


class UnknownRelationship(UnknownField):
    """Raised when attempting to deserialize a linkage object that
    references a relationship that does not exist on the model.

    """
    field_type = 'relationship'


class UnknownAttribute(UnknownField):
    """Raised when attempting to deserialize an object that specifies a
    field that does not exist on the model.

    """
    field_type = 'attribute'


class MissingInformation(DeserializationException):
    """Raised when a linkage object does not specify an element required by
    the JSON API specification.

    `relation_name` is the name of the relationship in which the linkage
    object is missing information.

    """

    #: The name of the key in the dictionary that is missing.
    #:
    #: Subclasses must set this class attribute.
    element: Optional[str] = None

    def __init__(self, relation_name=None, *args, **kw):
        super(MissingInformation, self).__init__(*args, **kw)

        #: The relationship in which a linkage object is missing information.
        self.relation_name = relation_name

        if relation_name is None:
            detail = 'missing "{0}" element'
            detail = detail.format(self.element)
        else:
            detail = ('missing "{0}" element in linkage object for'
                      ' relationship "{1}"')
            detail = detail.format(self.element, relation_name)
        self.detail = detail


class MissingData(MissingInformation):
    """Raised when a resource does not specify a ``'data'`` element
    where required by the JSON API specification.

    """
    element = 'data'


class MissingID(MissingInformation):
    """Raised when a resource does not specify an ``'id'`` element where
    required by the JSON API specification.

    """
    element = 'id'


class MissingType(MissingInformation):
    """Raised when a resource does not specify a ``'type'`` element
    where required by the JSON API specification.

    """
    element = 'type'


def get_column_name(column):
    """Retrieve a column name from a column attribute of SQLAlchemy model
    class, or a string.

    Raises `TypeError` when argument does not fall into either of those
    options.

    """
    # TODO use inspection API here
    if hasattr(column, '__clause_element__'):
        clause_element = column.__clause_element__()
        if not isinstance(clause_element, Column):
            msg = 'Expected a column attribute of a SQLAlchemy ORM class'
            raise TypeError(msg)
        return clause_element.key
    return column


class Serializer(ABC):
    """An object that, when called, returns a dictionary representation of a
    given instance of a SQLAlchemy model.

    """

    @property
    @abstractmethod
    def attributes_columns(self) -> FrozenSet[str]:
        """Provides a set of column names that should represent model's attributes"""

    @property
    @abstractmethod
    def relationship_columns(self) -> FrozenSet[str]:
        """Provides a set of column names that should represent model's relationships"""

    @abstractmethod
    def serialize(self, instance, only=None):
        """Returns a dictionary representation of the specified instance of a
        SQLAlchemy model.

        If `only` is a list, only the fields and relationships whose names
        appear as strings in `only` should appear in the returned
        dictionary. The only exception is that the keys ``'id'`` and ``'type'``
        will always appear, regardless of whether they appear in `only`.
        """


class Deserializer(ABC):
    """An object that, when called, returns an instance of the SQLAlchemy model
    specified at instantiation time.

    `session` is the SQLAlchemy session in which to look for any related
    resources.

    `model` is the class of which instances will be created by the
    :meth:`__call__` method.

    **This is a base class with no implementation.**

    """

    def __init__(self, session, model, api_manager):
        self.session = session
        self.model = model
        self.api_manager = api_manager

    @abstractmethod
    def deserialize(self, document):
        """Creates and returns a new instance of the SQLAlchemy model specified
        in the constructor whose attributes are given by the specified
        dictionary.

        `document` must be a dictionary representation of a JSON API
        document containing a single resource as primary data, as
        specified in the JSON API specification. For more information,
        see the `Resource Objects`_ section of the JSON API
        specification.

        .. _Resource Objects: http://jsonapi.org/format/#document-structure-resource-objects

        """


class DefaultSerializer(Serializer):
    """Default Serializer implementation."""

    def __init__(self, model, type_name, api_manager, primary_key=None, only=None, exclude=None, additional_attributes=None, **kwargs):
        super().__init__(**kwargs)
        if only is not None and exclude is not None:
            raise ValueError('Cannot specify both `only` and `exclude` keyword arguments simultaneously')

        if additional_attributes is not None and exclude is not None and any(attr in exclude for attr in additional_attributes):
            raise ValueError('Cannot exclude attributes listed in the `additional_attributes` keyword argument')

        self._api_manager = api_manager
        self._model = model
        self._type = type_name
        pk_names = primary_key_names(model)
        if primary_key:
            if primary_key not in pk_names:
                raise ValueError(f'Column `{primary_key}` is not a primary key')
        else:
            raise ValueError('`primary_key` is required')

        self._primary_key = primary_key
        self._relations = set(get_relations(model))
        self._only = None

        columns = set(attribute_columns(model))
        # JSON API 1.0: Fields for a resource object MUST share a common namespace with each other and with type and id. In other words,
        # a resource can not have an attribute and relationship with the same name, nor can it have an attribute or relationship named type or id.
        # https://jsonapi.org/format/#document-resource-object-fields
        columns -= {'type', 'id'}

        # Also include any attributes specified by the user.
        if additional_attributes is not None:
            columns |= set(additional_attributes)

        # Only include fields allowed by the user during the instantiation of this object.
        if only is not None:
            # Always include at least the type and ID, regardless of what the user specified.
            only = {get_column_name(column) for column in only}
            columns &= only
            self._relations &= only
            self._only = only

        # Exclude columns specified by the user during the instantiation of this object.
        if exclude is not None:
            excluded_column_names = {get_column_name(column) for column in exclude}
            columns -= excluded_column_names
            self._relations -= excluded_column_names

        # JSON API 1.0: Although has-one foreign keys (e.g. author_id) are often stored internally alongside other information to be represented in a resource
        # object, these keys SHOULD NOT appear as attributes
        # https://jsonapi.org/format/#document-resource-object-attributes
        columns -= set(foreign_keys(model))

        # Exclude column names that are blacklisted.
        columns = {column for column in columns if not column.startswith('__') and column not in COLUMN_BLACKLIST}

        self._relations = frozenset(self._relations)
        self._columns = frozenset(columns)

        # Finding ManyToOne relationships that can be rendered using FK
        inspected_model = inspect(model)
        self._many_to_one_relationships = {}

        for relationship in inspected_model.relationships:
            if relationship.key in self._relations and relationship.direction == MANYTOONE:
                foreign_key = relationship.local_remote_pairs[0][0].key
                target_model = relationship.mapper.class_
                self._many_to_one_relationships[relationship.key] = RelationshipInfo(foreign_key=foreign_key, target_model=target_model)

    @property
    def many_to_one_relationships(self):
        return set(self._many_to_one_relationships.keys())

    @property
    def relationship_columns(self):
        return self._relations

    @property
    def attributes_columns(self):
        return self._columns

    def serialize_attributes(self, instance, only=None) -> Dict[str, Any]:
        columns = self.attributes_columns
        if only is not None:
            columns &= only

        # Create a dictionary mapping attribute name to attribute value for
        # this particular instance.
        attributes = {column: getattr(instance, column) for column in columns}

        for key, value in attributes.items():
            # Serialize any date- or time-like objects that appear in the attributes.
            if isinstance(value, (date, datetime, time)):
                attributes[key] = value.isoformat()
            elif isinstance(value, timedelta):
                attributes[key] = value.total_seconds()
            # Enums are not serializable by default, use 'name' property
            elif isinstance(value, enum.Enum):
                attributes[key] = value.name

        return attributes

    def serialize(self, instance, only=None):
        attributes = self.serialize_attributes(instance, only)

        for key, value in attributes.items():
            # Call any functions that appear in the result.
            if callable(value):
                attributes[key] = value()

        # Get the ID and type of the resource.
        id_ = str(getattr(instance, self._primary_key))
        type_ = self._type
        # Create the result dictionary and add the attributes.
        result = dict(id=id_, type=type_)
        if attributes:
            result['attributes'] = attributes

        relations = copy(self._relations)
        # Only consider those relations listed in `only`.
        if only is not None:
            relations &= only

        if relations:
            result['relationships'] = {rel: self.create_relationship(instance, rel) for rel in relations}

        # TODO: Refactor
        if (self._api_manager.include_links and (self._only is None or 'self' in self._only)
                and (only is None or 'self' in only)):
            instance_id = getattr(instance, self._api_manager.primary_key_for(self._model))
            path = self._api_manager.url_for(self._model, resource_id=instance_id, _method='GET')
            url = urljoin(request.url_root, path)
            result['links'] = dict(self=url)

        return result

    def create_relationship(self, instance, relation):
        """Creates a relationship from the given relation name.

        Returns a dictionary representing a relationship as described in
        the `Relationships`_ section of the JSON API specification.

        `instance` is the instance of the model for which we are considering
        a related value.

        `relation` is the name of the relation of `instance` given as a
        string.

        This function may raise :exc:`ValueError` if an API has not been
        created for the primary model, `model`, or the model of the
        relation.

        .. _Relationships: http://jsonapi.org/format/#document-resource-object-relationships

        """
        result = {}
        if self._api_manager.include_links:
            # Create the self and related links.
            pk_value = getattr(instance, self._api_manager.primary_key_for(self._model))
            self_link = self._api_manager.url_for(self._model, resource_id=pk_value, relation_name=relation, relationship=True)
            related_link = self._api_manager.url_for(self._model, resource_id=pk_value, relation_name=relation)
            result['links'] = {'self': self_link}
            # If the user has not created a GET endpoint for the related
            # resource, then there is no "related" link to provide, so we check
            # whether the URL exists before setting the related link.
            try:
                get_related_model(self._model, relation)
            except ValueError:
                pass
            else:
                result['links']['related'] = related_link

        relationship_info = self._many_to_one_relationships.get(relation)
        if relationship_info:
            fk_value = getattr(instance, relationship_info.foreign_key)
            if fk_value is None:
                result['data'] = None
            else:
                result['data'] = {
                    'id': str(fk_value),
                    'type': self._api_manager.collection_name(relationship_info.target_model)
                }
            return result

        # Get the related value so we can see if it is a to-many
        # relationship or a to-one relationship.
        related_value = getattr(instance, relation)
        # There are three possibilities for the relation: it could be a
        # to-many relationship, a null to-one relationship, or a non-null
        # to-one relationship. We decide whether the relation is to-many by
        # determining whether it is list-like.
        if is_like_list(instance, relation):
            # We could pre-compute the "type" name for the related instances
            # here and provide it in the `_type` keyword argument to the
            # serialization function, but the to-many relationship could be
            # heterogeneous.
            result['data'] = [self._api_manager.serialize_relationship(instance)
                              for instance in related_value]
        elif related_value is not None:
            result['data'] = self._api_manager.serialize_relationship(related_value)
        else:
            result['data'] = None
        return result


class DefaultDeserializer(Deserializer):
    """A default implementation of a deserializer for SQLAlchemy models.

    When called, this object returns an instance of a SQLAlchemy model
    with fields and relations specified by the provided dictionary.

    """

    def __init__(self, *args, allow_client_generated_ids=False, **kw):
        super(DefaultDeserializer, self).__init__(*args, **kw)

        #: Whether to allow client generated IDs.
        self.allow_client_generated_ids = allow_client_generated_ids

    def deserialize(self, document):
        """Creates and returns an instance of the SQLAlchemy model
        specified in the constructor.

        Everything in the `document` other than the `data` element is
        ignored.

        For more information, see the documentation for the
        :meth:`Deserializer.__call__` method.

        """
        if 'data' not in document:
            raise MissingData
        data = document['data']
        if 'type' not in data:
            raise MissingType
        if 'id' in data and not self.allow_client_generated_ids:
            raise ClientGeneratedIDNotAllowed
        type_ = data.pop('type')
        expected_type = self.api_manager.collection_name(self.model)
        if type_ != expected_type:
            raise ConflictingType(expected_type, type_)
        # Check for any request parameter naming a column which does not exist
        # on the current model.
        for field in data:
            if field == 'relationships':
                for relation in data['relationships']:
                    if not has_field(self.model, relation):
                        raise UnknownRelationship(relation)
            elif field == 'attributes':
                for attribute in data['attributes']:
                    if not has_field(self.model, attribute):
                        raise UnknownAttribute(attribute)
        # Determine which related instances need to be added.
        links = {}
        if 'relationships' in data:
            links = data.pop('relationships', {})
            for link_name, link_object in links.items():
                if 'data' not in link_object:
                    raise MissingData(link_name)
                linkage = link_object['data']
                related_model = get_related_model(self.model, link_name)
                expected_type = self.api_manager.collection_name(related_model)
                # Create the deserializer for this relationship object.
                deserializer = DefaultRelationshipDeserializer(self.session, related_model, self.api_manager, relation_name=link_name)
                links[link_name] = deserializer.deserialize(linkage)
        # TODO Need to check here if any related instances are None,
        # like we do in the patch() method. We could possibly refactor
        # the code above and the code there into a helper function...
        pass
        # Move the attributes up to the top level.
        data.update(data.pop('attributes', {}))
        # Special case: if there are any dates, convert the string form of the
        # date into an instance of the Python ``datetime`` object.
        data = strings_to_datetimes(self.model, data)
        # Create the new instance by keyword attributes.
        instance = self.model(**data)
        # Set each relation specified in the links.
        for relation_name, related_value in links.items():
            setattr(instance, relation_name, related_value)
        return instance


class DefaultRelationshipDeserializer(Deserializer):
    """A default implementation of a deserializer for resource
    identifier objects for use in relationships in JSON API documents.

    Each instance of this class should correspond to a particular
    relationship of a model.

    This deserializer differs from the default deserializer for
    resources since it expects that the input dictionary `data` to
    :meth:`__call__` contains only ``'id'`` and ``'type'`` keys.

    `session` is the SQLAlchemy session in which to look for any related
    resources.

    `model` is the SQLAlchemy model class of the relationship, *not the
    primary resource*. With the related model class, this deserializer
    will be able to use the ID provided to the :meth:`__call__` method
    to determine the instance of the `related_model` class which is
    being deserialized.

    `relation_name` is the name of the relationship being deserialized,
    given as a string. This is used mainly for more helpful error
    messages.

    """

    def __init__(self, *args, relation_name=None):
        super(DefaultRelationshipDeserializer, self).__init__(*args)

        #: The collection name given to the related model.
        self.type_name = self.api_manager.collection_name(self.model)

        #: The name of the relationship being deserialized, as a string.
        self.relation_name = relation_name

    def deserialize(self, data):
        """Gets the resource associated with the given resource
        identifier object.

        `data` must be a dictionary containing exactly two elements,
        ``'type'`` and ``'id'``, or a list of dictionaries of that
        form. In the former case, the `data` represents a to-one
        relation and in the latter a to-many relation.

        Returns the instance or instances of the SQLAlchemy model
        specified in the constructor whose ID or IDs match the given
        `data`.

        May raise :exc:`MissingID`, :exc:`MissingType`, or
        :exc:`ConflictingType`.

        """
        # If this is a to-one relationship, get the sole instance of the model.
        if not isinstance(data, list):
            if 'id' not in data:
                raise MissingID(self.relation_name)
            if 'type' not in data:
                raise MissingType(self.relation_name)
            type_ = data['type']
            if type_ != self.type_name:
                raise ConflictingType(self.relation_name, self.type_name,
                                      type_)
            id_ = data['id']
            primary_key = self.api_manager.primary_key_for(self.model)
            return get_by(self.session, self.model, id_, primary_key=primary_key)
        # Otherwise, if this is a to-many relationship, recurse on each
        # and return a list of instances.
        return list(map(self.deserialize, data))
