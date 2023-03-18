# test_updating_relationships.py - tests updating relationships via JSON API
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
"""Unit tests for requests that update relationships.

The tests in this module correspond to the `Updating Relationships`_
section of the JSON API specification.

.. _Updating Relationships: https://jsonapi.org/format/#crud-updating-relationships

"""
import pytest

from flask_restless import APIManager

from ..conftest import BaseTestClass
from .models import Article
from .models import Base
from .models import Person


class TestUpdatingRelationships(BaseTestClass):
    """Tests corresponding to the `Updating Relationships`_ section of the JSON
    API specification.

    .. _Updating Relationships: https://jsonapi.org/format/#crud-updating-relationships

    """

    @pytest.fixture(autouse=True)
    def setup(self):
        manager = APIManager(self.app, session=self.session)
        manager.create_api(Article, methods=['PATCH'])
        manager.create_api(Person, methods=['PATCH'])
        manager.create_api(Person, methods=['PATCH'], url_prefix='/api2', allow_to_many_replacement=True, allow_delete_from_to_many_relationships=True)
        Base.metadata.create_all(bind=self.engine)
        yield
        Base.metadata.drop_all(bind=self.engine)

    def test_to_one(self):
        """Tests for updating a to-one relationship via a :https:method:`patch`
        request to a relationship URL.

        For more information, see the `Updating To-One Relationships`_ section
        of the JSON API specification.

        .. _Updating To-One Relationships: https://jsonapi.org/format/#crud-updating-to-one-relationships

        """
        self.session.add_all([
            Person(pk=1),
            Person(pk=2),
            Article(id=1, author_id=1)
        ])
        self.session.commit()
        data = dict(data=dict(type='person', id='2'))
        response = self.client.patch('/api/article/1/relationships/author', json=data)
        assert response.status_code == 204
        article = self.session.get(Article, 1)
        assert article.author_id == 2

    def test_remove_to_one(self):
        """Tests for removing a to-one relationship via a :https:method:`patch`
        request to a relationship URL.

        For more information, see the `Updating To-One Relationships`_ section
        of the JSON API specification.

        .. _Updating To-One Relationships: https://jsonapi.org/format/#crud-updating-to-one-relationships

        """
        self.session.add_all([
            Person(pk=1),
            Person(pk=2),
            Article(id=1, author_id=1)
        ])
        self.session.commit()
        data = dict(data=None)
        response = self.client.patch('/api/article/1/relationships/author', json=data)
        assert response.status_code == 204
        article = self.session.get(Article, 1)
        assert article.author_id is None

    def test_to_many(self):
        """Tests for replacing a to-many relationship via a
        :https:method:`patch` request to a relationship URL.

        For more information, see the `Updating To-Many Relationships`_ section
        of the JSON API specification.

        .. _Updating To-Many Relationships: https://jsonapi.org/format/#crud-updating-to-many-relationships

        """
        self.session.add_all([
            Person(pk=1),
            Article(id=1),
            Article(id=2),
        ])
        self.session.commit()
        data = {'data': [{'type': 'article', 'id': '1'},
                         {'type': 'article', 'id': '2'}]}
        response = self.client.patch('/api2/person/1/relationships/articles', json=data)
        assert response.status_code == 204
        person = self.session.get(Person, 1)
        articles_ids = sorted(article.id for article in person.articles)
        assert articles_ids == [1, 2]

    def test_to_many_append(self):
        """Tests for appending to a to-many relationship via a
        :https:method:`post` request to a relationship URL.

        For more information, see the `Updating To-Many Relationships`_ section
        of the JSON API specification.

        .. _Updating To-Many Relationships: https://jsonapi.org/format/#crud-updating-to-many-relationships

        """
        self.session.add_all([
            Person(pk=1),
            Article(id=1, author_id=1),
            Article(id=2),
            Article(id=3),
        ])
        self.session.commit()
        data = {'data': [{'type': 'article', 'id': '2'},
                         {'type': 'article', 'id': '3'}]}
        response = self.client.post('/api/person/1/relationships/articles', json=data)
        assert response.status_code == 204
        person = self.session.get(Person, 1)
        articles_ids = sorted(article.id for article in person.articles)
        assert articles_ids == [1, 2, 3]

    def test_to_many_not_found(self):
        """Tests that an attempt to replace a to-many relationship with a
        related resource that does not exist yields an error response.

        For more information, see the `Updating To-Many Relationships`_ section
        of the JSON API specification.

        .. _Updating To-Many Relationships: https://jsonapi.org/format/#crud-updating-to-many-relationships

        """
        self.session.add_all([
            Person(pk=1),
            Article(id=1),
        ])
        self.session.commit()
        data = {'data': [{'type': 'article', 'id': '1'},
                         {'type': 'article', 'id': '2'}]}
        response = self.client.patch('/api2/person/1/relationships/articles', json=data)
        assert response.status_code == 404
        assert response.json['errors'][0]['detail'] == 'No object of type article found with ID 2'

    def test_to_many_forbidden(self):
        """Tests that full replacement of a to-many relationship is forbidden
        by the server configuration, then the response is :https:status:`403`.

        For more information, see the `Updating To-Many Relationships`_ section
        of the JSON API specification.

        .. _Updating To-Many Relationships: https://jsonapi.org/format/#crud-updating-to-many-relationships

        """
        self.session.add(Person(pk=1))
        self.session.commit()
        response = self.client.patch('/api/person/1/relationships/articles', json={'data': []})
        assert response.status_code == 403
        assert response.json['errors'][0]['detail'] == 'Not allowed to replace a to-many relationship'

    def test_to_many_preexisting(self):
        """Tests for attempting to append an element that already exists in a
        to-many relationship via a :https:method:`post` request to a
        relationship URL.

        For more information, see the `Updating To-Many Relationships`_ section
        of the JSON API specification.

        .. _Updating To-Many Relationships: https://jsonapi.org/format/#crud-updating-to-many-relationships

        """
        self.session.add_all([
            Person(pk=1),
            Article(id=1, author_id=1),
        ])
        self.session.commit()
        data = {'data': [{'type': 'article', 'id': '1'}]}
        response = self.client.post('/api/person/1/relationships/articles', json=data)
        assert response.status_code == 204
        person = self.session.get(Person, 1)
        assert [article.id for article in person.articles] == [1]

    def test_to_many_delete(self):
        """Tests for deleting from a to-many relationship via a
        :https:method:`delete` request to a relationship URL.

        For more information, see the `Updating To-Many Relationships`_ section
        of the JSON API specification.

        .. _Updating To-Many Relationships: https://jsonapi.org/format/#crud-updating-to-many-relationships

        """
        self.session.add_all([
            Person(pk=1),
            Article(id=1, author_id=1),
            Article(id=2, author_id=1),
        ])
        self.session.commit()
        data = {'data': [{'type': 'article', 'id': '1'}]}
        response = self.client.delete('/api2/person/1/relationships/articles', json=data)
        assert response.status_code == 204
        person = self.session.get(Person, 1)
        assert [article.id for article in person.articles] == [2]

    def test_to_many_delete_nonexistent(self):
        """Tests for deleting a nonexistent member from a to-many relationship
        via a :https:method:`delete` request to a relationship URL.

        For more information, see the `Updating To-Many Relationships`_ section
        of the JSON API specification.

        .. _Updating To-Many Relationships: https://jsonapi.org/format/#crud-updating-to-many-relationships

        """
        self.session.add_all([
            Person(pk=1),
            Article(id=1, author_id=1),
            Article(id=2),
        ])
        self.session.commit()
        data = {'data': [{'type': 'article', 'id': '2'}]}
        response = self.client.delete('/api2/person/1/relationships/articles', json=data)
        assert response.status_code == 204
        person = self.session.get(Person, 1)
        assert [article.id for article in person.articles] == [1]

    def test_to_many_delete_forbidden(self):
        """Tests that attempting to delete from a to-many relationship via a
        :https:method:`delete` request to a relationship URL when the server has
        disallowed it yields a :https:status:`409` response.

        For more information, see the `Updating To-Many Relationships`_ section
        of the JSON API specification.

        .. _Updating To-Many Relationships: https://jsonapi.org/format/#crud-updating-to-many-relationships

        """
        self.session.add_all([
            Person(pk=1),
            Article(id=1, author_id=1),
        ])
        self.session.commit()
        data = {'data': [{'type': 'article', 'id': '1'}]}
        response = self.client.delete('/api/person/1/relationships/articles', json=data)
        assert response.status_code == 403
        person = self.session.get(Person, 1)
        assert [article.id for article in person.articles] == [1]
