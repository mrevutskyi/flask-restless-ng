# relationships.py - views for requests on SQLAlchemy relationships
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
"""Views for fetching, creating, updating, and deleting relationships.

The main class in this module, :class:`RelationshipAPI`, is a
:class:`~flask.MethodView` subclass that handles requests for updating
relationships according to the JSON API specification.

"""
from flask import json
from flask import request
from markupsafe import escape
from werkzeug.exceptions import BadRequest

from ..helpers import get_by
from ..helpers import get_related_model
from ..helpers import is_like_list
from .base import APIBase
from .base import collection_parameters
from .base import error
from .base import error_response
from .base import errors_response


class RelationshipAPI(APIBase):
    """Provides fetching, updating, and deleting from relationship URLs.

    The endpoints provided by this class are of the form
    ``/people/1/relationships/articles``, and the requests and responses
    include **link objects**, as opposed to **resource objects**.

    `session` and `model` are as described in the constructor of the
    superclass. In addition to those described below, this constructor
    also accepts all the keyword arguments of the constructor of the
    superclass.

    `allow_delete_from_to_many_relationships` is as described in
    :meth:`APIManager.create_api`.

    """

    def __init__(self, session, model, api_manager,
                 allow_delete_from_to_many_relationships=False, *args, **kw):
        super(RelationshipAPI, self).__init__(session, model, api_manager, *args, **kw)
        self.allow_delete_from_to_many_relationships = \
            allow_delete_from_to_many_relationships

    def collection_processor_type(self, *args, **kw):
        return 'TO_MANY_RELATIONSHIP'

    def resource_processor_type(self, *args, **kw):
        return 'TO_ONE_RELATIONSHIP'

    def use_resource_identifiers(self):
        return True

    def get(self, resource_id, relation_name):
        """Fetches a to-one or to-many relationship from a resource.

        If the specified relationship is a to-one relationship, this method
        returns a link object. If it is a to-many relationship, it returns a
        collection of link objects.

        The request documents, response documents, and status codes are in the
        format specified by the JSON API specification.

        """
        for preprocessor in self.preprocessors['GET_RELATIONSHIP']:
            temp_result = preprocessor(resource_id=resource_id,
                                       relation_name=relation_name)
            # Let the return value of the preprocessor be the new value of
            # instid, thereby allowing the preprocessor to effectively specify
            # which instance of the model to process on.
            #
            # We assume that if the preprocessor returns None, it really just
            # didn't return anything, which means we shouldn't overwrite the
            # instid.
            if temp_result is not None:
                resource_id = temp_result
        # get the instance of the "main" model whose ID is `resource_id`
        primary_resource = get_by(self.session, self.model, resource_id,
                                  self.primary_key)
        if primary_resource is None:
            return error_response(404, detail=f'No resource with ID {escape(resource_id)}')
        if is_like_list(primary_resource, relation_name):
            filters, sort = collection_parameters()
            return self._get_collection_helper(resource=primary_resource,
                                               relation_name=relation_name,
                                               filters=filters, sort=sort)
        resource = getattr(primary_resource, relation_name)
        return self._get_resource_helper(resource,
                                         primary_resource=primary_resource,
                                         relation_name=relation_name)

    def post(self, resource_id, relation_name):
        """Adds resources to a to-many relationship.

        The request documents, response documents, and status codes are in the
        format specified by the JSON API specification.

        """
        # try to load the fields/values to update from the body of the request
        try:
            data = json.loads(request.get_data()) or {}
        except (BadRequest, TypeError, ValueError, OverflowError) as exception:
            # this also happens when request.data is empty
            detail = 'Unable to decode data'
            return error_response(400, cause=exception, detail=detail)
        for preprocessor in self.preprocessors['POST_RELATIONSHIP']:
            temp_result = preprocessor(resource_id=resource_id,
                                       relation_name=relation_name, data=data)
            # See the note under the preprocessor in the get() method.
            if temp_result is not None:
                resource_id, relation_name = temp_result
        instance = get_by(self.session, self.model, resource_id, self.primary_key)
        # If no instance of the model exists with the specified instance ID,
        # return a 404 response.
        if instance is None:
            return error_response(404, detail=f'No instance with ID {escape(resource_id)} in model {self.model}')
        # If no such relation exists, return a 404.
        if not hasattr(instance, relation_name):
            return error_response(404, detail=f'Model {self.model} has no relation named {escape(relation_name)}')
        related_model = get_related_model(self.model, relation_name)
        related_value = getattr(instance, relation_name)
        # Unwrap the data from the request.
        data = data.pop('data', {})
        for rel in data:
            if 'type' not in rel:
                return error_response(400, detail='Must specify correct data type')
            if 'id' not in rel:
                return error_response(400, detail='Must specify resource ID')
            type_ = rel['type']
            # The type name must match the collection name of model of the
            # relation.
            collection_name = self.api_manager.collection_name(related_model)
            if type_ != collection_name:
                return error_response(409, detail=f'Type must be {collection_name}, not {type_}')
            # Get the new objects to add to the relation.
            new_value = get_by(self.session, related_model, rel['id'], self.api_manager.primary_key_for(related_model))
            if new_value is None:
                return error_response(404, detail=f'No object of type {escape(type_)} found with ID {rel["id"]}')
            # Don't append a new value if it already exists in the to-many
            # relationship.
            if new_value not in related_value:
                try:
                    related_value.append(new_value)
                except self.validation_exceptions as exception:
                    return self._handle_validation_exception(exception)

        self.session.flush()

        # Perform any necessary postprocessing.
        for postprocessor in self.postprocessors['POST_RELATIONSHIP']:
            postprocessor()
        self.session.commit()
        return {}, 204, {}

    def patch(self, resource_id, relation_name):
        """Updates to a to-one or to-many relationship.

        If the relationship is a to-many relationship and this class was
        instantiated with the ``allow_to_many_replacement`` keyword argument
        set to ``False``, then this method returns a :http:status:`403`
        response.

        The request documents, response documents, and status codes are in the
        format specified by the JSON API specification.

        """
        # try to load the fields/values to update from the body of the request
        try:
            data = json.loads(request.get_data()) or {}
        except (BadRequest, TypeError, ValueError, OverflowError) as exception:
            # this also happens when request.data is empty
            detail = 'Unable to decode data'
            return error_response(400, cause=exception, detail=detail)
        for preprocessor in self.preprocessors['PATCH_RELATIONSHIP']:
            temp_result = preprocessor(instance_id=resource_id,
                                       relation_name=relation_name, data=data)
            # See the note under the preprocessor in the get() method.
            if temp_result is not None:
                resource_id, relation_name = temp_result
        instance = get_by(self.session, self.model, resource_id,
                          self.primary_key)
        # If no instance of the model exists with the specified instance ID,
        # return a 404 response.
        if instance is None:
            return error_response(404, detail=f'No instance with ID {escape(resource_id)} in model {self.model}')
        # If no such relation exists, return a 404.
        if not hasattr(instance, relation_name):
            return error_response(404, detail=f'Model {self.model} has no relation named {escape(relation_name)}')
        related_model = get_related_model(self.model, relation_name)
        # related_value = getattr(instance, relation_name)

        # Unwrap the data from the request.
        data = data.pop('data', {})
        # If the client sent a null value, we assume it wants to remove a
        # to-one relationship.
        if data is None:
            if is_like_list(instance, relation_name):
                detail = 'Cannot set null value on a to-many relationship'
                return error_response(400, detail=detail)
            setattr(instance, relation_name, None)
        else:
            # If this is a list, we assume the client is trying to set a
            # to-many relationship.
            if isinstance(data, list):
                # Replacement of a to-many relationship may have been disabled
                # on the server-side by the user.
                if not self.allow_to_many_replacement:
                    detail = 'Not allowed to replace a to-many relationship'
                    return error_response(403, detail=detail)
                replacement = []
                for rel in data:
                    if 'type' not in rel:
                        return error_response(400, detail='Must specify correct data type')
                    if 'id' not in rel:
                        return error_response(400, detail='Must specify resource ID or IDs')
                    type_ = rel['type']
                    # The type name must match the collection name of model of
                    # the relation.
                    collection_name = self.api_manager.collection_name(related_model)
                    if type_ != collection_name:
                        return error_response(409, detail=f'Type must be {collection_name}, not {type_}')
                    id_ = rel['id']
                    obj = get_by(self.session, related_model, id_, self.api_manager.primary_key_for(related_model))
                    replacement.append(obj)
            # Otherwise, we assume the client is trying to set a to-one
            # relationship.
            else:
                if 'type' not in data:
                    return error_response(400, detail='Must specify correct data type')
                if 'id' not in data:
                    return error_response(400, detail='Must specify resource ID or IDs')
                type_ = data['type']
                # The type name must match the collection name of model of the
                # relation.
                collection_name = self.api_manager.collection_name(related_model)
                if type_ != collection_name:
                    return error_response(409, detail=f'Type must be {collection_name}, not {type_}')
                id_ = data['id']
                replacement = get_by(self.session, related_model, id_, self.api_manager.primary_key_for(related_model))
            # If the to-one relationship resource or any of the to-many
            # relationship resources do not exist, return an error response.
            if replacement is None:
                detail = f'No object of type {escape(type_)} found with ID {escape(id_)}'
                return error_response(404, detail=detail)
            if isinstance(replacement, list) and any(value is None for value in replacement):
                not_found = (rel for rel, value in zip(data, replacement)
                             if value is None)
                detail = 'No object of type {0} found with ID {1}'
                errors = [error(detail=detail.format(escape(rel['type']), escape(rel['id'])))
                          for rel in not_found]
                return errors_response(404, errors)
            # Finally, set the relationship to have the new value.
            try:
                setattr(instance, relation_name, replacement)
            except self.validation_exceptions as exception:
                return self._handle_validation_exception(exception)
        self.session.flush()
        for postprocessor in self.postprocessors['PATCH_RELATIONSHIP']:
            postprocessor()
        self.session.commit()
        return {}, 204, {}

    def delete(self, resource_id, relation_name):
        """Deletes resources from a to-many relationship.

        If this class was instantiated with the
        ``allow_delete_from_to_many_relationships`` keyword argument set to
        ``False``, then this method returns a :http:status:`403` response.

        The request documents, response documents, and status codes are in the
        format specified by the JSON API specification.

        """
        if not self.allow_delete_from_to_many_relationships:
            detail = 'Not allowed to delete from a to-many relationship'
            return error_response(403, detail=detail)
        # try to load the fields/values to update from the body of the request
        try:
            data = json.loads(request.get_data()) or {}
        except (BadRequest, TypeError, ValueError, OverflowError) as exception:
            # this also happens when request.data is empty
            return error_response(400, cause=exception, detail='Unable to decode data')
        was_deleted = False
        for preprocessor in self.preprocessors['DELETE_RELATIONSHIP']:
            temp_result = preprocessor(instance_id=resource_id,
                                       relation_name=relation_name)
            # See the note under the preprocessor in the get() method.
            if temp_result is not None:
                resource_id = temp_result
        instance = get_by(self.session, self.model, resource_id,
                          self.primary_key)
        # If no such relation exists, return an error to the client.
        if not hasattr(instance, relation_name):
            return error_response(404, detail=f'No such link: {escape(relation_name)}')
        # We assume that the relation is a to-many relation.
        related_model = get_related_model(self.model, relation_name)
        related_type = self.api_manager.collection_name(related_model)
        relation = getattr(instance, relation_name)
        data = data.pop('data')
        not_found = []
        to_remove = []
        for rel in data:
            if 'type' not in rel:
                detail = 'Must specify correct data type'
                return error_response(400, detail=detail)
            if 'id' not in rel:
                detail = 'Must specify resource ID'
                return error_response(400, detail=detail)
            type_ = rel['type']
            id_ = rel['id']
            if type_ != related_type:
                detail = f'Conflicting type: expected {related_type} but got type {escape(type_)} for linkage object with ID {escape(id_)}'
                return error_response(409, detail=detail)
            resource = get_by(self.session, related_model, id_, self.api_manager.primary_key_for(related_model))
            if resource is None:
                not_found.append((type_, id_))
            else:
                to_remove.append(resource)
        if not_found:
            detail = 'No resource of type {0} and ID {1} found'
            errors = [error(detail=detail.format(escape(t), escape(i))) for t, i in not_found]
            return errors_response(404, errors)
        # Remove each of the resources from the relation (if they are not
        # already absent).
        for resource in to_remove:
            try:
                relation.remove(resource)
            except ValueError:
                # The JSON API specification requires that we silently
                # ignore requests to delete resources that are already
                # missing from a to-many relation.
                pass
        was_deleted = len(self.session.dirty) > 0
        self.session.commit()
        for postprocessor in self.postprocessors['DELETE_RELATIONSHIP']:
            postprocessor(was_deleted=was_deleted)
        if not was_deleted:
            detail = 'There was no instance to delete'
            return error_response(404, detail=detail)
        return {}, 204, {}
