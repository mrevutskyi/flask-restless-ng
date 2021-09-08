# test_creating_resources.py - tests creating resources according to JSON API
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
"""Unit tests for requests that create resources.

The tests in this module correspond to the `Creating Resources`_ section
of the JSON API specification.

.. _Creating Resources: https://jsonapi.org/format/#crud-creating

"""
import pytest

from flask_restless import APIManager

from ..conftest import BaseTestClass
from .models import Article
from .models import Base
from .models import Comment
from .models import Person


class TestCreatingResources(BaseTestClass):
    """Tests corresponding to the `Creating Resources`_ section of the JSON API
    specification.

    .. _Creating Resources: https://jsonapi.org/format/#crud-creating

    """

    @pytest.fixture(autouse=True)
    def setup(self):
        manager = APIManager(self.app, session=self.session)
        manager.create_api(Article, methods=['POST'], allow_client_generated_ids=True)
        manager.create_api(Person, methods=['POST'])
        manager.create_api(Comment)
        Base.metadata.create_all(bind=self.engine)
        yield
        Base.metadata.drop_all(bind=self.engine)

    def test_sparse_fieldsets_post(self):
        """Tests for restricting which fields are returned in a
        :http:method:`post` request.

        This unit test lives in this class instead of the
        :class:`TestFetchingData` class because in that class, APIs do
        not allow :http:method:`post` requests.

        For more information, see the `Sparse Fieldsets`_ section
        of the JSON API specification.

        .. _Sparse Fieldsets: https://jsonapi.org/format/#fetching-sparse-fieldsets
        """
        data = {
            'data': {
                'type': 'person',
                'attributes': {
                    'name': 'foo',
                    'age': 99
                }
            }
        }
        query_string = {'fields[person]': 'name'}
        document = self.post_and_validate('/api/person', json=data, query_string=query_string)
        person = document['data']
        # ID and type must always be included.
        assert ['attributes', 'id', 'type'] == sorted(person)
        assert ['name'] == sorted(person['attributes'])

    def test_conversion(self):
        """Tests that values are being returned in the correct type.
        E.g. if an integer has been passed as a string, we still have integer in the response

        """
        data = {
            'data': {
                'type': 'person',
                'attributes': {
                    'age': '99'
                }
            }
        }
        document = self.post_and_validate('/api/person', json=data)
        person = document['data']
        assert person['attributes']['age'] == 99

    def test_include_post(self):
        """Tests for including related resources on a
        :http:method:`post` request.

        This unit test lives in this class instead of the
        :class:`TestFetchingData` class because in that class, APIs do
        not allow :http:method:`post` requests.

        For more information, see the `Inclusion of Related Resources`_
        section of the JSON API specification.

        .. _Inclusion of Related Resources: https://jsonapi.org/format/#fetching-includes

        """
        self.session.add(Comment(id=1))
        self.session.commit()
        data = {
            'data': {
                'type': 'person',
                'relationships': {
                    'comments': {
                        'data': [{'type': 'comment', 'id': 1}]
                    }
                }
            }
        }
        query_string = dict(include='comments')
        document = self.post_and_validate('/api/person', json=data, query_string=query_string)
        included = document['included']
        assert len(included) == 1
        comment = included[0]
        assert comment['type'] == 'comment'
        assert comment['id'] == '1'

    def test_null_in_to_many_relationship(self):
        """Tests that API correctly processes nulls in to-many relationships."""
        data = {
            'data': {
                'type': 'person',
                'relationships': {
                    'comments': {
                        'data': None
                    }
                }
            }
        }
        self.post_and_validate('/api/person', json=data, expected_response_code=400,
                               error_msg="Failed to deserialize object: 'comments' Incompatible collection type: None is not list-like")

    def test_null_in_to_one_relationship(self):
        """Tests that API correctly processes nulls in to-one relationships."""
        data = {
            'data': {
                'type': 'article',
                'relationships': {
                    'author': {
                        'data': None
                    }
                }
            }
        }
        document = self.post_and_validate('/api/article', json=data)
        assert document['data']['id'] == '1'

    def test_create(self):
        """Tests that the client can create a single resource.

        For more information, see the `Creating Resources`_ section of the JSON
        API specification.

        .. _Creating Resources: https://jsonapi.org/format/#crud-creating

        """
        data = {
            'data': {
                'type': 'person',
                'name': 'foo'
            }
        }
        response = self.client.post('/api/person', json=data)
        assert response.status_code == 201
        location = response.headers['Location']
        assert location.endswith('/api/person/1')
        person = response.json['data']
        assert person['type'] == 'person'
        assert person['id'] == '1'
        assert person['attributes']['name'] == 'foo'
        instance = self.session.query(Person).get(1)
        assert instance.pk == 1
        assert instance.name == 'foo'

    def test_without_type(self):
        """Tests for an error response if the client fails to specify the type
        of the object to create.

        For more information, see the `Creating Resources`_ section of the JSON
        API specification.

        .. _Creating Resources: https://jsonapi.org/format/#crud-creating

        """
        data = {'data': {'name': 'foo'}}
        self.post_and_validate('/api/person', json=data, expected_response_code=400, error_msg='missing "type"')

    def test_client_generated_id(self):
        """Tests that the client can specify a UUID to become the ID of the
        created object.

        For more information, see the `Client-Generated IDs`_ section of the
        JSON API specification.

        .. _Client-Generated IDs: https://jsonapi.org/format/#crud-creating-client-ids

        """
        generated_id = 111
        data = {'data': {'type': 'article', 'id': generated_id}}
        document = self.post_and_validate('/api/article', json=data)
        article = document['data']
        assert article['type'] == 'article'
        assert article['id'] == str(generated_id)

    def test_client_generated_id_forbidden(self):
        """Tests that the server returns correct response code if client provides 'id'
        when Client-Generated IDs are disabled

        .. _Client-Generated IDs: https://jsonapi.org/format/#crud-creating-client-ids
        """
        data = {'data': {'type': 'article', 'id': 13}}
        self.post_and_validate('/api/person', json=data, expected_response_code=403,
                               error_msg='Server does not allow client-generated IDS')

    def test_type_conflict(self):
        """Tests that if a client specifies a type that does not match the
        endpoint, a :http:status:`409` is returned.

        For more information, see the `409 Conflict`_ section of the JSON API
        specification.

        .. _409 Conflict: https://jsonapi.org/format/#crud-creating-responses-409

        """

        data = {'data': {'type': 'bogus_type', 'name': 'foo'}}
        self.post_and_validate('/api/person', json=data, expected_response_code=409,
                               error_msg='expected type "person" but got type "bogus_type"')

    def test_id_conflict(self):
        """Tests that if a client specifies a client-generated ID that already
        exists, a :http:status:`409` is returned.

        For more information, see the `409 Conflict`_ section of the JSON API
        specification.

        .. _409 Conflict: https://jsonapi.org/format/#crud-creating-responses-409

        """
        generated_id = 112
        self.session.add(Article(id=generated_id))
        self.session.commit()
        data = {'data': {'type': 'article', 'id': '112'}}
        self.post_and_validate('/api/article', json=data, expected_response_code=409, error_msg='UNIQUE constraint failed')

    def test_ignore_additional_members(self):
        """Tests that the server ignores any additional top-level members.

        For more information, see the `Document Structure`_ section of the JSON
        API specification.

        .. _Document Structure: https://jsonapi.org/format/#document-structure

        """
        # The key `bogus` is unknown to the JSON API specification, and therefore should be ignored.
        data = {'data': {'type': 'person'}, 'bogus': True}
        document = self.post_and_validate('/api/person', json=data)
        assert 'errors' not in document
        assert self.session.query(Person).count() == 1
