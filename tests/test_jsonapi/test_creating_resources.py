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
from datetime import datetime

import pytest
from dateutil import parser

from flask_restless import APIManager

from ..conftest import BaseTestClass
from .models import Article
from .models import Base
from .models import Comment
from .models import Person
from .models import UnicodePK
from .models import Various


class TestCreatingResources(BaseTestClass):
    """Tests corresponding to the `Creating Resources`_ section of the JSON API
    specification.

    .. _Creating Resources: https://jsonapi.org/format/#crud-creating

    """

    @pytest.fixture(autouse=True)
    def setup(self):
        manager = APIManager(self.app, session=self.session)
        self.manager = manager
        manager.create_api(Article, methods=['POST'], allow_client_generated_ids=True)
        manager.create_api(Person, methods=['POST'])
        manager.create_api(Various, methods=['POST'])
        manager.create_api(UnicodePK, methods=['POST'])
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

    def test_to_one(self):
        """Tests the creation of a model with a to-one relation."""
        self.session.add(Person(pk=1))
        self.session.commit()
        data = {
            'data': {
                'type': 'article',
                'relationships': {
                    'author': {
                        'data': {'type': 'person', 'id': '1'}
                    }
                }
            }
        }
        document = self.post_and_validate('/api/article', json=data)
        person = document['data']['relationships']['author']['data']
        assert person['type'] == 'person'
        assert person['id'] == '1'

    def test_to_many(self):
        """Tests the creation of a model with a to-many relation."""
        self.session.bulk_save_objects([Article(id=1), Article(id=2)])
        self.session.commit()
        data = {
            'data': {
                'type': 'person',
                'relationships': {
                    'articles': {
                        'data': [
                            {'type': 'article', 'id': '1'},
                            {'type': 'article', 'id': '2'}
                        ]
                    }
                }
            }
        }
        document = self.post_and_validate('/api/person', json=data)
        articles = document['data']['relationships']['articles']['data']
        assert ['1', '2'] == sorted(article['id'] for article in articles)
        assert all(article['type'] == 'article' for article in articles)

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
                'attributes': {
                    'name': 'foo',
                }
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

    def test_related_resource_url_forbidden(self):
        """Tests that :http:method:`post` requests to a related resource URL are forbidden.

        """
        response = self.client.post('/api/person/1/articles', json={})
        assert response.status_code == 405

    def test_deserializing_time(self):
        """Test for deserializing a JSON representation of a time field."""
        test_time = datetime.now().time().isoformat()
        data = dict(data=dict(type='various', attributes=dict(time=test_time)))
        document = self.post_and_validate('/api/various', json=data)
        assert document['data']['attributes']['time'] == test_time

    def test_deserializing_date(self):
        """Test for deserializing a JSON representation of a date field."""
        test_date = datetime.now().date().isoformat()
        data = dict(data=dict(type='various', attributes=dict(date=test_date)))
        document = self.post_and_validate('/api/various', json=data)
        assert document['data']['attributes']['date'] == test_date

    def test_deserializing_datetime(self):
        """Test for deserializing a JSON representation of a date field."""
        test_datetime = datetime.now().isoformat()
        data = dict(data=dict(type='various', attributes=dict(datetime=test_datetime)))
        document = self.post_and_validate('/api/various', json=data)
        assert document['data']['attributes']['datetime'] == test_datetime

    def test_no_data(self):
        """Tests that a request with no data yields an error response."""
        self.post_and_validate('/api/person', expected_response_code=400, error_msg='Unable to decode data')

    def test_invalid_json(self):
        """Tests that a request with an invalid JSON causes an error response."""
        self.post_and_validate('/api/person', expected_response_code=400, data='not a JSON', error_msg='Unable to decode data')

    def test_rollback_on_integrity_error(self):
        """Tests that an integrity error in the database causes a session
        rollback, and that the server can still process requests correctly
        after this rollback.

        """
        self.session.add(Person(name=u'foo'))
        self.session.commit()
        data = dict(data=dict(type='person', attributes=dict(name=u'foo')))
        self.post_and_validate('/api/person', json=data, expected_response_code=409)
        assert self.session.is_active, 'Session is in `partial rollback` state'
        data = dict(data=dict(type='person', attributes=dict(name=u'bar')))
        self.post_and_validate('/api/person', json=data)

    def test_nonexistent_attribute(self):
        """Tests that the server rejects an attempt to create a resource with
        an attribute that does not exist in the resource.

        """
        data = dict(data=dict(type='person', attributes=dict(bogus=0)))
        self.post_and_validate('/api/person', json=data, expected_response_code=400, error_msg='model has no attribute "bogus"')

    def test_nonexistent_relationship(self):
        """Tests that the server rejects an attempt to create a resource with a relationship that does not exist in the resource."""
        data = {
            'data': {
                'type': 'person',
                'relationships': {
                    'bogus': {
                        'data': None
                    }
                }
            }
        }
        self.post_and_validate('/api/person', json=data, expected_response_code=400, error_msg='model has no relationship "bogus"')

    def test_invalid_relationship(self):
        """Tests that the server rejects an attempt to create a resource with an invalid relationship linkage object."""
        # In this request, the `articles` linkage object is missing the
        # `data` element.
        data = {
            'data': {
                'type': 'person',
                'relationships':
                {
                    'articles': {}
                }
            }
        }
        self.post_and_validate('/api/person', json=data, expected_response_code=400,
                               error_msg='missing "data" element in linkage object for relationship "articles"')

    def test_hybrid_property(self):
        """Tests that an attempt to set a read-only hybrid property causes an error.

        See issue #171 in the original Flask-Restless.
        """
        data = dict(data=dict(type='person', attributes=dict(is_minor=True)))
        self.post_and_validate('/api/person', json=data, expected_response_code=400, error_msg='model has no attribute "is_minor"')

    def test_nullable_datetime(self):
        """Tests for creating a model with a nullable datetime field.

        For more information, see issue #91 in the original Flask-Restless.
        """
        data = dict(data=dict(type='various', attributes=dict(datetime=None)))
        document = self.post_and_validate('/api/various', json=data)
        assert document['data']['attributes']['datetime'] is None

    def test_empty_date(self):
        """Tests that attempting to assign an empty date string to a date field actually assigns a value of ``None``.

        For more information, see issue #91 in the original Flask-Restless.
        """
        data = dict(data=dict(type='various', attributes=dict(datetime='')))
        document = self.post_and_validate('/api/various', json=data)
        assert document['data']['attributes']['datetime'] is None

    def test_current_timestamp(self):
        """Tests that the string ``'CURRENT_TIMESTAMP'`` gets converted into a
        datetime object when making a request to set a date or time field.

        """
        data = dict(data=dict(type='various', attributes=dict(datetime='CURRENT_TIMESTAMP')))
        document = self.post_and_validate('/api/various', json=data)
        datetime_value = document['data']['attributes']['datetime']
        assert datetime_value is not None
        diff = datetime.utcnow() - parser.parse(datetime_value)
        # Check that the total number of seconds from the server creating the
        # Person object to (about) now is not more than about a minute.
        assert diff.days == 0
        assert (diff.seconds + diff.microseconds / 1000000) < 3600

    def test_timedelta(self):
        """Tests for creating an object with a timedelta attribute."""
        data = dict(data=dict(type='various', attributes=dict(interval=300)))
        document = self.post_and_validate('/api/various', json=data)
        assert document['data']['attributes']['interval'] == 300

    def test_unicode_primary_key(self):
        """Test for creating a resource with a unicode primary key.
        And that even if a primary key is not named ``id``, it still appears in an ``id`` key in the response.
        """
        data = dict(data=dict(type='unicode_pk', attributes=dict(name=u'Юникод')))
        document = self.post_and_validate('/api/unicode_pk', json=data)
        assert document['data']['attributes']['name'] == u'Юникод'
        assert document['data']['id'] == u'Юникод'

    def test_collection_name(self):
        """Tests for creating a resource with an alternate collection name."""
        self.manager.create_api(Person, methods=['POST'], collection_name='people')
        data = dict(data=dict(type='people'))
        document = self.post_and_validate('/api/people', json=data)
        assert document['data']['type'] == 'people'


class TestProcessors(BaseTestClass):
    """Tests for pre- and post-processors."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.manager = APIManager(self.app, session=self.session)
        Base.metadata.create_all(bind=self.engine)
        yield
        Base.metadata.drop_all(bind=self.engine)

    def test_preprocessor(self):
        """Tests :http:method:`post` requests with a preprocessor function."""

        def set_name(data=None, **kw):
            """Sets the name attribute of the incoming data object, regardless
            of the value requested by the client.

            """
            if data is not None:
                data['data']['attributes']['name'] = u'bar'

        preprocessors = dict(POST_RESOURCE=[set_name])
        self.manager.create_api(Person, methods=['POST'], preprocessors=preprocessors)
        data = dict(data=dict(type='person', attributes=dict(name=u'foo')))
        document = self.post_and_validate('/api/person', json=data)
        assert document['data']['attributes']['name'] == 'bar'

    def test_postprocessor(self):
        """Tests that a postprocessor is invoked when creating a resource."""

        def modify_result(result=None, **kw):
            result['foo'] = 'bar'

        postprocessors = dict(POST_RESOURCE=[modify_result])
        self.manager.create_api(Person, methods=['POST'], postprocessors=postprocessors)
        data = dict(data=dict(type='person'))
        response = self.client.post('/api/person', json=data)
        assert response.status_code == 201
        document = response.json
        assert document['foo'] == 'bar'

    def test_postprocessor_can_rollback_transaction(self):
        """Tests that a postprocessor can rollback the transaction."""

        def rollback_transaction(result=None, **kw):
            self.session.rollback()

        postprocessors = dict(POST_RESOURCE=[rollback_transaction])
        self.manager.create_api(Person, methods=['POST'], postprocessors=postprocessors)
        data = dict(data=dict(type='person'))
        self.post_and_validate('/api/person', json=data)
        assert self.session.query(Person).count() == 0
