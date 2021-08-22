# test_document_structure.py - tests JSON API document structure
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
"""Tests that Flask-Restless responds to the client with correctly
structured JSON documents.

The tests in this module correspond to the `Document Structure`_ section
of the JSON API specification.

.. _Document Structure: https://jsonapi.org/format/#document-structure

"""
import string

import pytest

from flask_restless import APIManager

from ..conftest import BaseTestClass
from .models import Article
from .models import Base
from .models import Comment
from .models import Person


class TestDocumentStructure(BaseTestClass):
    """Tests corresponding to the `Document Structure`_ section of the JSON API
    specification.

    .. _Document Structure: https://jsonapi.org/format/#document-structure

    """

    @pytest.fixture(autouse=True)
    def setup(self):
        manager = APIManager(self.app, session=self.session, include_links=True)
        manager.create_api(Article)
        manager.create_api(Person, methods=['GET', 'POST'])
        manager.create_api(Comment)
        Base.metadata.create_all(bind=self.engine)
        yield
        Base.metadata.drop_all(bind=self.engine)

    def test_allowable_top_level_keys(self):
        """Tests that a response contains at least one of the top-level
        elements ``data``, ``errors``, and ``meta``.

        For more information, see the `Top Level`_ section of the JSON
        API specification.

        .. _Top Level: https://jsonapi.org/format/#document-top-level

        """
        document = self.fetch_and_validate('/api/person')
        allowed_keys = ('data', 'errors', 'meta')
        assert any(key in document for key in allowed_keys)

    def test_no_data_and_errors_good_request(self):
        """Tests that a response to a valid request does not contain
        both ``data`` and ``errors`` simultaneously as top-level
        elements.

        For more information, see the `Top Level`_ section of the JSON
        API specification.

        .. _Top Level: https://jsonapi.org/format/#document-top-level

        """
        document = self.fetch_and_validate('/api/person')
        assert all(key in document for key in ('data', 'errors')) is False

    def test_no_data_and_errors_bad_request(self):
        """Tests that a response to an invalid request does not contain
        both ``data`` and ``errors`` simultaneously as top-level
        elements.

        For more information, see the `Top Level`_ section of the JSON
        API specification.

        .. _Top Level: https://jsonapi.org/format/#document-top-level

        """
        document = self.fetch_and_validate('/api/person/bogus_key', expected_response_code=404)
        assert all(key in document for key in ('data', 'errors')) is False

    def test_errors_top_level_key(self):
        """Tests that errors appear under a top-level key ``errors``."""
        document = self.fetch_and_validate('/api/person/bogus_key', expected_response_code=404)
        assert 'errors' in document

    def test_no_other_top_level_keys(self):
        """Tests that no there are no other alphanumeric top-level keys in the
        response other than the allowed ones.

        For more information, see the `Top Level`_ section of the JSON API
        specification.

        .. _Top Level: https://jsonapi.org/format/#document-structure-top-level

        """
        document = self.fetch_and_validate('/api/person')
        allowed = ('data', 'errors', 'meta', 'jsonapi', 'links', 'included')
        alphanumeric = string.ascii_letters + string.digits
        assert all(key in allowed or key[0] not in alphanumeric for key in document)

    def test_no_foreign_keys(self):
        """By default, foreign keys should not appear in the representation of
        a resource.

        For more information, see the `Resource Object Attributes`_
        section of the JSON API specification.

        .. _Resource Object Attributes: https://jsonapi.org/format/#document-resource-object-attributes

        """
        self.session.add(Comment(id=1))
        self.session.commit()
        document = self.fetch_and_validate('/api/comment/1')
        article = document['data']
        assert 'attributes' not in article
        assert 'author_id' not in article

    def test_required_relationship_keys(self):
        """Tests that a relationship object contains at least one of the
        required keys, ``links``, ``data``, or ``meta``.

        For more information, see the `Resource Object Relationships`_
        section of the JSON API specification.

        .. _Resource Object Relationships: https://jsonapi.org/format/#document-resource-object-relationships

        """
        self.session.add(Person(pk=1))
        self.session.commit()
        document = self.fetch_and_validate('/api/person/1')
        articles = document['data']['relationships']['articles']
        assert any(key in articles for key in ('data', 'links', 'meta'))

    def test_required_relationship_link_keys(self):
        """Tests that a relationship links object contains at least one
        of the required keys, ``self`` or ``related``.

        For more information, see the `Resource Object Relationships`_
        section of the JSON API specification.

        .. _Resource Object Relationships: https://jsonapi.org/format/#document-resource-object-relationships

        """
        self.session.add(Person(pk=1))
        self.session.commit()
        document = self.fetch_and_validate('/api/person/1')
        articles = document['data']['relationships']['articles']
        links = articles['links']
        assert any(key in links for key in ('self', 'related'))

    def test_self_relationship_url(self):
        """Tests that a relationship object correctly identifies its own
        relationship URL.

        For more information, see the `Resource Object Relationships`_
        section of the JSON API specification.

        .. _Resource Object Relationships: https://jsonapi.org/format/#document-resource-object-relationships

        """
        self.session.add_all([Person(pk=1), Article(id=1, author_id=1)])
        self.session.commit()
        document = self.fetch_and_validate('/api/article/1')
        relationship_url = document['data']['relationships']['author']['links']['self']
        assert relationship_url.endswith('/api/article/1/relationships/author')

    def test_related_resource_url_to_one(self):
        """Tests that the related resource URL in a to-one relationship
        correctly identifies the related resource.

        For more information, see the `Related Resource Links`_ section
        of the JSON API specification.

        .. _Related Resource Links: https://jsonapi.org/format/#document-resource-object-related-resource-links

        """
        self.session.add_all([Person(pk=1), Article(id=1, author_id=1)])
        self.session.commit()
        # Get a resource that has links.
        document = self.fetch_and_validate('/api/article/1')
        # Get the related resource URL.
        resource_url = document['data']['relationships']['author']['links']['related']
        # Fetch the resource at the related resource URL.
        document = self.fetch_and_validate(resource_url)
        actual_person = document['data']
        # Compare it with what we expect to get.
        document = self.fetch_and_validate('/api/person/1')
        expected_person = document['data']
        assert actual_person == expected_person

    def test_related_resource_url_to_many(self):
        """Tests that the related resource URL in a to-many relationship
        correctly identifies the related resource.

        For more information, see the `Related Resource Links`_ section
        of the JSON API specification.

        .. _Related Resource Links: https://jsonapi.org/format/#document-resource-object-related-resource-links

        """
        self.session.add_all([Person(pk=1), Article(id=1, author_id=1)])
        self.session.commit()
        # Get a resource that has links.
        document = self.fetch_and_validate('/api/person/1')
        # Get the related resource URL.
        resource_url = document['data']['relationships']['articles']['links']['related']
        # Fetch the resource at the related resource URL.
        document = self.fetch_and_validate(resource_url)
        actual_articles = document['data']
        # Compare it with what we expect to get.
        document = self.fetch_and_validate('/api/article')
        expected_articles = document['data']
        assert actual_articles == expected_articles

    def test_resource_linkage_empty_to_one(self):
        """Tests that resource linkage for an empty to-one relationship
        is ``null``.

        For more information, see the `Resource Linkage`_ section of the
        JSON API specification.

        .. _Resource Linkage: https://jsonapi.org/format/#document-resource-object-linkage

        """
        self.session.add(Article(id=1))
        self.session.commit()
        document = self.fetch_and_validate('/api/article/1')
        linkage = document['data']['relationships']['author']['data']
        assert linkage is None

    def test_resource_linkage_empty_to_many(self):
        """Tests that resource linkage for an empty to-many relationship
        is an empty list.

        For more information, see the `Resource Linkage`_ section of the
        JSON API specification.

        .. _Resource Linkage: https://jsonapi.org/format/#document-resource-object-linkage

        """
        self.session.add(Person(pk=1))
        self.session.commit()
        document = self.fetch_and_validate('/api/person/1')
        linkage = document['data']['relationships']['articles']['data']
        assert linkage == []

    def test_resource_linkage_to_one(self):
        """Tests that resource linkage for a to-one relationship is
        a single resource identifier object.

        For more information, see the `Resource Linkage`_ section of the
        JSON API specification.

        .. _Resource Linkage: https://jsonapi.org/format/#document-resource-object-linkage

        """
        self.session.add_all([Person(pk=1), Article(id=1, author_id=1)])
        self.session.commit()
        document = self.fetch_and_validate('/api/article/1')
        linkage = document['data']['relationships']['author']['data']
        assert linkage['id'] == '1'
        assert linkage['type'] == 'person'

    def test_resource_linkage_to_many(self):
        """Tests that resource linkage for a to-many relationship is a
        list of resource identifier objects.

        For more information, see the `Resource Linkage`_ section of the
        JSON API specification.

        .. _Resource Linkage: https://jsonapi.org/format/#document-resource-object-linkage

        """
        self.session.add_all([
            Article(id=1, author_id=1),
            Article(id=2, author_id=1),
            Person(pk=1)
        ])
        self.session.commit()
        document = self.fetch_and_validate('/api/person/1')
        linkage = document['data']['relationships']['articles']['data']
        assert ['1', '2'] == sorted(link['id'] for link in linkage)
        assert all(link['type'] == 'article' for link in linkage)

    def test_self_link(self):
        """Tests that a request to a self link responds with the same
        object.

        For more information, see the `Resource Links`_ section of the
        JSON API specification.

        .. _Resource Links: https://jsonapi.org/format/#document-resource-object-links

        """
        self.session.add(Person(pk=1))
        self.session.commit()
        document1 = self.fetch_and_validate('/api/person/1')
        self_url = document1['data']['links']['self']
        document2 = self.fetch_and_validate(self_url)
        assert document1 == document2

    def test_resource_identifier_object_keys(self):
        """Tests that a resource identifier object contains the required
        keys.

        For more information, see the `Resource Identifier Objects`_
        section of the JSON API specification.

        .. _Resource Identifier Objects: https://jsonapi.org/format/#document-resource-identifier-objects

        """
        self.session.add_all([Person(pk=1), Article(id=1, author_id=1)])
        self.session.commit()
        document = self.fetch_and_validate('/api/article/1')
        linkage = document['data']['relationships']['author']['data']
        assert all(key in linkage for key in ('id', 'type'))
        assert linkage['id'] == '1'
        assert linkage['type'] == 'person'

    def test_top_level_self_link(self):
        """Tests that there is a top-level links object containing a
        self link.

        For more information, see the `Links`_ section of the JSON API
        specification.

        .. _Links: https://jsonapi.org/format/#document-links

        """
        document = self.fetch_and_validate('/api/person')
        assert document['links']['self'].endswith('/api/person')

    @pytest.mark.parametrize('url', [
        '/api/person',
        '/api/person/1',
        '/api/person/1/articles',

    ])
    def test_jsonapi_object(self, url):
        """Tests that the server provides a jsonapi object.

        For more information, see the `JSON API Object`_ section of the
        JSON API specification.

        .. _JSON API Object: https://jsonapi.org/format/#document-jsonapi-object

        """
        self.session.add(Person(pk=1))
        self.session.commit()
        document = self.fetch_and_validate(url)
        assert document['jsonapi']['version'] == '1.0'
