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
        manager.create_api(Article, ['POST'], allow_client_generated_ids=True)
        manager.create_api(Person, ['POST'])
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
        response = self.client.post('/api/person', json=data, query_string=query_string)
        person = response.json['data']
        # ID and type must always be included.
        assert ['attributes', 'id', 'type'] == sorted(person)
        assert ['name'] == sorted(person['attributes'])

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
        response = self.client.post('/api/person', json=data, query_string=query_string)
        assert response.status_code == 201
        included = response.json['included']
        assert len(included) == 1
        comment = included[0]
        assert comment['type'] == 'comment'
        assert comment['id'] == '1'

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
        # TODO Technically, this test shouldn't know beforehand where the
        # location of the created object will be. We are testing implementation
        # here, assuming that the implementation of the server creates a new
        # Person object with ID 1, which is bad style.
        assert location.endswith('/api/person/1')
        person = response.json['data']
        assert person['type'] == 'person'
        assert person['id'] == '1'
        assert person['attributes']['name'] == 'foo'

    def test_without_type(self):
        """Tests for an error response if the client fails to specify the type
        of the object to create.

        For more information, see the `Creating Resources`_ section of the JSON
        API specification.

        .. _Creating Resources: https://jsonapi.org/format/#crud-creating

        """
        data = {'data': {'name': 'foo'}}
        response = self.client.post('/api/person', json=data)
        assert response.status_code == 400
        assert 'missing "type"' in response.json['errors'][0]['detail']

    def test_client_generated_id(self):
        """Tests that the client can specify a UUID to become the ID of the
        created object.

        For more information, see the `Client-Generated IDs`_ section of the
        JSON API specification.

        .. _Client-Generated IDs: https://jsonapi.org/format/#crud-creating-client-ids

        """
        generated_id = 111
        data = {'data': {'type': 'article', 'id': generated_id}}
        response = self.client.post('/api/article', json=data)
        assert response.status_code == 201
        article = response.json['data']
        assert article['type'] == 'article'
        assert article['id'] == str(generated_id)

    def test_client_generated_id_forbidden(self):
        """Tests that the server returns correct response code if client provides 'id'
        when Client-Generated IDs are disabled

        .. _Client-Generated IDs: https://jsonapi.org/format/#crud-creating-client-ids
        """
        data = {'data': {'type': 'article', 'id': 13}}
        response = self.client.post('/api/person', json=data)
        assert response.status_code == 403
        assert 'Server does not allow client-generated IDS' in response.json['errors'][0]['detail']

    def test_type_conflict(self):
        """Tests that if a client specifies a type that does not match the
        endpoint, a :http:status:`409` is returned.

        For more information, see the `409 Conflict`_ section of the JSON API
        specification.

        .. _409 Conflict: https://jsonapi.org/format/#crud-creating-responses-409

        """

        data = {'data': {'type': 'bogus_type', 'name': 'foo'}}
        response = self.client.post('/api/person', json=data)
        assert response.status_code == 409
        assert 'expected type "person" but got type "bogus_type"' in response.json['errors'][0]['detail']

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
        response = self.client.post('/api/article', json=data)
        assert response.status_code == 409
        assert 'UNIQUE constraint failed' in response.json['errors'][0]['detail']
