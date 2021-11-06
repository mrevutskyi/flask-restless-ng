# test_updating_resources.py - tests updating resources according to JSON API
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
"""Unit tests for updating resources according to the JSON API
specification.

The tests in this module correspond to the `Updating Resources`_ section
of the JSON API specification.

.. _Updating Resources: https://jsonapi.org/format/#crud-updating

"""
from operator import attrgetter

import pytest

from flask_restless import APIManager

from ..conftest import BaseTestClass
from .models import Article
from .models import Base
from .models import Person
from .models import Tag


class TestUpdatingResources(BaseTestClass):
    """Tests corresponding to the `Updating Resources`_ section of the JSON API
    specification.

    .. _Updating Resources: https://jsonapi.org/format/#crud-updating

    """

    @pytest.fixture(autouse=True)
    def setup(self):
        manager = APIManager(self.app, session=self.session)
        manager.create_api(Article, methods=['PATCH'])
        manager.create_api(Person, methods=['PATCH'])
        manager.create_api(Person, methods=['PATCH'], url_prefix='/api2', allow_to_many_replacement=True)
        manager.create_api(Tag, methods=['GET', 'PATCH'])
        Base.metadata.create_all(bind=self.engine)
        yield
        Base.metadata.drop_all(bind=self.engine)

    def test_update(self):
        """Tests that the client can update a resource's attributes.

        For more information, see the `Updating a Resource's Attributes`_
        section of the JSON API specification.

        .. _Updating a Resource's Attributes: https://jsonapi.org/format/#crud-updating-resource-attributes

        """
        person = Person(pk=1, name=u'foo', age=10)
        self.session.add(person)
        self.session.commit()
        data = dict(data=dict(type='person', id='1', attributes=dict(name=u'bar')))
        self.patch_and_validate('/api/person/1', json=data)
        assert person.pk == 1
        assert person.name == 'bar'
        assert person.age == 10

    def test_to_one(self):
        """Tests that the client can update a resource's to-one relationships.

        For more information, see the `Updating a Resource's To-One Relationships`_
        section of the JSON API specification.

        .. _Updating a Resource's To-One Relationships: https://jsonapi.org/format/#crud-updating-resource-to-one-relationships

        """
        person1 = Person(pk=1)
        person2 = Person(pk=2)
        article = Article(id=1, author_id=1)
        self.session.add_all([person1, person2, article])
        self.session.commit()
        # Change the author of the article from person 1 to person 2.
        data = {
            'data': {
                'type': 'article',
                'id': '1',
                'relationships': {
                    'author': {
                        'data': {'type': 'person', 'id': '2'}
                    }
                }
            }
        }
        self.patch_and_validate('/api/article/1', json=data)
        assert article.author is person2

    def test_remove_to_one(self):
        """Tests that the client can remove a resource's to-one relationship.

        For more information, see the `Updating a Resource's To-One Relationships`_
        section of the JSON API specification.

        .. _Updating a Resource's To-One Relationships: https://jsonapi.org/format/#crud-updating-resource-to-one-relationships

        """
        person = Person(pk=1)
        article = Article(id=1, author_id=1)
        self.session.add_all([person, article])
        self.session.commit()
        # Change the author of the article to None.
        data = {
            'data': {
                'type': 'article',
                'id': '1',
                'relationships': {'author': {'data': None}}
            }
        }
        self.patch_and_validate('/api/article/1', json=data)
        assert article.author is None

    def test_to_many(self):
        """Tests that the client can update a resource's to-many relationships.

        For more information, see the `Updating a Resource's To-Many Relationships`_
        section of the JSON API specification.

        .. _Updating a Resource's To-Many Relationships: https://jsonapi.org/format/#crud-updating-resource-to-many-relationships

        """
        person = Person(pk=1)
        article1 = Article(id=1)
        article2 = Article(id=2)
        self.session.add_all([person, article1, article2])
        self.session.commit()
        data = {
            'data': {
                'type': 'person',
                'id': '1',
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
        self.patch_and_validate('/api2/person/1', json=data)
        articles = sorted(person.articles, key=attrgetter('id'))
        assert [article1, article2] == articles

    def test_to_many_clear(self):
        """Tests that the client can clear a resource's to-many relationships.

        For more information, see the `Updating a Resource's To-Many Relationships`_
        section of the JSON API specification.

        .. _Updating a Resource's To-Many Relationships: https://jsonapi.org/format/#crud-updating-resource-to-many-relationships

        """
        person = Person(pk=1)
        self.session.add_all([
            person,
            Article(id=1, author_id=1),
            Article(id=2, author_id=1)
        ])
        self.session.commit()
        data = {
            'data': {
                'type': 'person',
                'id': '1',
                'relationships': {
                    'articles': {
                        'data': []
                    }
                }
            }
        }
        self.patch_and_validate('/api2/person/1', json=data)
        assert person.articles == []

    def test_to_many_forbidden(self):
        """Tests that the client receives a :https:status:`403` if the server
        has been configured to disallow full replacement of a to-many
        relationship.

        For more information, see the `Updating a Resource's To-Many Relationships`_
        section of the JSON API specification.

        .. _Updating a Resource's To-Many Relationships: https://jsonapi.org/format/#crud-updating-resource-to-many-relationships

        """
        self.session.add(Person(pk=1))
        self.session.commit()
        data = {
            'data': {
                'type': 'person',
                'id': '1',
                'relationships': {'articles': {'data': []}}
            }
        }
        self.patch_and_validate('/api/person/1', json=data, expected_response_code=403)

    def test_other_modifications(self):
        """Tests that if an update causes additional changes in the resource in
        ways other than those specified by the client, the response has status
        :https:status:`200` and includes the updated resource.

        For more information, see the `200 OK`_ section of the JSON API
        specification.

        .. _200 OK: https://jsonapi.org/format/#crud-updating-responses-200

        """
        self.session.add(Tag(id=1))
        self.session.commit()
        data = {
            'data': {
                'type': 'tag',
                'id': '1',
                'attributes': {'name': u'foo'}
            }
        }
        document = self.patch_and_validate('/api/tag/1', json=data, expected_response_code=200)
        tag1 = document['data']
        document = self.fetch_and_validate('/api/tag/1')
        tag2 = document['data']
        assert tag1 == tag2

    def test_nonexistent(self):
        """Tests that an attempt to update a nonexistent resource causes a
        :https:status:`404` response.

        For more information, see the `404 Not Found`_ section of the JSON API
        specification.

        .. _404 Not Found: https://jsonapi.org/format/#crud-updating-responses-404

        """
        data = dict(data=dict(type='person', id='1'))
        self.patch_and_validate('/api/person/1', json=data, expected_response_code=404)

    def test_nonexistent_relationship(self):
        """Tests that an attempt to update a nonexistent resource causes a
        :https:status:`404` response.

        For more information, see the `404 Not Found`_ section of the JSON API
        specification.

        .. _404 Not Found: https://jsonapi.org/format/#crud-updating-responses-404

        """
        self.session.add(Person(pk=1))
        self.session.commit()
        data = {
            'data': {
                'type': 'person',
                'id': '1',
                'relationships': {
                    'articles': {'data': [{'type': 'article', 'id': '1'}]}
                }
            }
        }
        self.patch_and_validate('/api2/person/1', json=data, expected_response_code=404, error_msg='No object of type article found with ID 1')

    def test_conflicting_attributes(self):
        """Tests that an attempt to update a resource with a non-unique
        attribute value where uniqueness is required causes a
        :https:status:`409` response.

        For more information, see the `409 Conflict`_ section of the JSON API
        specification.

        .. _409 Conflict: https://jsonapi.org/format/#crud-updating-responses-409

        """

        self.session.add_all([
            Person(pk=1, name=u'foo'),
            Person(pk=2)
        ])
        self.session.commit()
        data = dict(data=dict(type='person', id='2', attributes=dict(name=u'foo')))
        self.patch_and_validate('/api/person/2', json=data, expected_response_code=409, error_msg='IntegrityError')

    def test_conflicting_type(self):
        """Tests that an attempt to update a resource with the wrong type
        causes a :https:status:`409` response.

        For more information, see the `409 Conflict`_ section of the JSON API
        specification.

        .. _409 Conflict: https://jsonapi.org/format/#crud-updating-responses-409

        """
        self.session.add(Person(pk=1))
        self.session.commit()
        data = dict(data=dict(type='bogus', id='1'))
        self.patch_and_validate('/api/person/1', json=data, expected_response_code=409, error_msg='Type must be person, not bogus')

    def test_conflicting_id(self):
        """Tests that an attempt to update a resource with the wrong ID causes
        a :https:status:`409` response.

        For more information, see the `409 Conflict`_ section of the JSON API
        specification.

        .. _409 Conflict: https://jsonapi.org/format/#crud-updating-responses-409

        """
        self.session.add(Person(pk=1))
        self.session.commit()
        data = dict(data=dict(type='person', id='bogus'))
        self.patch_and_validate('/api/person/1', json=data, expected_response_code=409, error_msg='ID must be 1, not bogus')
