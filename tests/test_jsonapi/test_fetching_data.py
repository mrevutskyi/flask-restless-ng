"""Unit tests for requests that fetch resources and relationships.

The tests in this module correspond to the `Fetching Data`_ section of
the JSON API specification.

.. _Fetching Data: https://jsonapi.org/format/#fetching

"""
import pytest

from flask_restless import APIManager

from ..conftest import BaseTestClass
from .models import Article
from .models import Base
from .models import Child
from .models import Comment
from .models import Parent
from .models import Person


class TestFetching(BaseTestClass):
    """Tests corresponding to the `Fetching Data`_ section of the JSON API specification.

    .. _Fetching Data: https://jsonapi.org/format/#fetching

    """

    @pytest.fixture(autouse=True)
    def setup(self):
        manager = APIManager(self.app, session=self.session)
        manager.create_api(Article)
        manager.create_api(Person)
        manager.create_api(Comment)
        manager.create_api(Parent, page_size=0)
        manager.create_api(Child)

        Base.metadata.create_all(bind=self.engine)
        yield
        Base.metadata.drop_all(bind=self.engine)

    def test_single_resource(self):
        """Tests for fetching a single resource.

        For more information, see the `Fetching Resources`_ section of JSON API specification.

        .. _Fetching Resources: https://jsonapi.org/format/#fetching-resources

        """
        self.session.add(Article(id=1, title='Some title'))
        self.session.commit()

        document = self.fetch_and_validate('/api/article/1')

        assert document['data'] == {
            'id': '1',
            'type': 'article',
            'attributes': {
                'title': 'Some title'
            },
            'relationships': {
                'author': {
                    'data': None
                },
                'comments': {
                    'data': []
                }
            },
        }

    def test_collection(self):
        """Tests for fetching a collection of resources.

        For more information, see the `Fetching Resources`_ section of JSON API specification.

        .. _Fetching Resources: https://jsonapi.org/format/#fetching-resources

        """

        self.session.bulk_save_objects([
            Article(id=1, title='Some title'),
            Article(id=2)
        ])
        self.session.commit()

        document = self.fetch_and_validate('/api/article')
        articles = document['data']
        assert ['1', '2'] == sorted(article['id'] for article in articles)

    def test_collection_with_complex_relationship(self):
        document = self.fetch_and_validate('/api/parent')
        assert document['data'] == []

    def test_related_resource(self):
        """Tests for fetching a to-one related resource.

        For more information, see the `Fetching Resources`_ section of JSON API specification.

        .. _Fetching Resources: https://jsonapi.org/format/#fetching-resources

        """
        self.session.bulk_save_objects([
            Article(id=1, author_id=1),
            Person(pk=1)
        ])
        self.session.commit()

        document = self.fetch_and_validate('/api/article/1/author')

        data = document['data']
        assert data['type'] == 'person'
        assert data['id'] == '1'

    def test_empty_collection(self):
        """Tests for fetching an empty collection of resources.

        For more information, see the `Fetching Resources`_ section of JSON API specification.

        .. _Fetching Resources: https://jsonapi.org/format/#fetching-resources

        """
        document = self.fetch_and_validate('/api/person')

        assert document['data'] == []

    def test_to_many_related_resource_url(self):
        """Tests for fetching to-many related resources from a related  resource URL.

        The response to a request to a to-many related resource URL should
        include an array of resource objects, *not* linkage objects.

        For more information, see the `Fetching Resources`_ section of JSON API specification.

        .. _Fetching Resources: https://jsonapi.org/format/#fetching-resources

        """
        self.session.bulk_save_objects([
            Person(pk=1),
            Article(id=1, author_id=1),
            Article(id=2, author_id=1),
        ])
        self.session.commit()

        document = self.fetch_and_validate('/api/person/1/articles')

        data = document['data']
        assert ['1', '2'] == sorted(article['id'] for article in data)
        assert all(article['type'] == 'article' for article in data)
        assert all('title' in article['attributes'] for article in data)
        assert all('author' in article['relationships'] for article in data)

    def test_to_one_related_resource_url(self):
        """Tests for fetching a to-one related resource from a related resource URL.

        The response to a request to a to-one related resource URL should
        include a resource object, *not* a linkage object.

        For more information, see the `Fetching Resources`_ section of JSON API specification.

        .. _Fetching Resources: https://jsonapi.org/format/#fetching-resources

        """
        self.session.bulk_save_objects([
            Person(pk=1),
            Article(id=1, author_id=1),
        ])
        self.session.commit()

        document = self.fetch_and_validate('/api/article/1/author')
        data = document['data']
        assert data['id'] == '1'
        assert data['type'] == 'person'
        assert all(field in data['attributes'] for field in ('name', 'age', 'other'))

    def test_empty_to_many_related_resource_url(self):
        """Tests for fetching an empty to-many related resource from a related resource URL.

        For more information, see the `Fetching Resources`_ section of JSON API specification.

        .. _Fetching Resources: https://jsonapi.org/format/#fetching-resources

        """
        self.session.add(Person(pk=1))
        self.session.commit()

        document = self.fetch_and_validate('/api/person/1/articles')

        assert document['data'] == []

    def test_empty_to_one_related_resource(self):
        """Tests for fetching an empty to-one related resource from a related resource URL.

        For more information, see the `Fetching Resources`_ section of JSON API specification.

        .. _Fetching Resources: https://jsonapi.org/format/#fetching-resources

        """
        self.session.add(Article(id=1))
        self.session.commit()

        document = self.fetch_and_validate('/api/article/1/author')

        assert document['data'] is None

    def test_nonexistent_resource(self):
        """Tests for fetching a nonexistent resource.

        For more information, see the `Fetching Resources`_ section of JSON API specification.

        .. _Fetching Resources: https://jsonapi.org/format/#fetching-resources

        """
        response = self.client.get('/api/article/1')
        assert response.status_code == 404

    def test_nonexistent_collection(self):
        """Tests for fetching a nonexistent collection of resources.

        For more information, see the `Fetching Resources`_ section of JSON API specification.

        .. _Fetching Resources: https://jsonapi.org/format/#fetching-resources

        """
        response = self.client.get('/api/bogus')
        assert response.status_code == 404

    def test_empty_to_many_relationship_url(self):
        """Test for fetching from an empty to-many relationship URL.

        A server MUST respond to a successful request to fetch a relationship with a 200 OK response.

        The primary data in the response document MUST match the appropriate value for resource linkage:
        an empty array ([]) for empty to-many relationships.

        For more information, see the `Fetching Relationships`_ section of JSON API specification.

        .. _Fetching Relationships: https://jsonapi.org/format/#fetching-relationships-responses-200

        """
        self.session.add(Article(id=1))
        self.session.commit()

        document = self.fetch_and_validate('/api/article/1/relationships/comments')

        assert document['data'] == []

    def test_to_many_relationship_url(self):
        """Test for fetching linkage objects from a to-many relationship URL.

        The response to a request to a to-many relationship URL should
        be a linkage object, *not* a resource object.

        For more information, see the `Fetching Relationships`_ section of JSON API specification.

        .. _Fetching Relationships: https://jsonapi.org/format/#fetching-relationships

        """
        self.session.bulk_save_objects([
            Article(id=1),
            Comment(id=1, article_id=1),
            Comment(id=2, article_id=1),
            Comment(id=3),
        ])
        self.session.commit()

        document = self.fetch_and_validate('/api/article/1/relationships/comments')

        data = document['data']
        assert all(['id', 'type'] == sorted(comment) for comment in data)
        assert ['1', '2'] == sorted(comment['id'] for comment in data)
        assert all(comment['type'] == 'comment' for comment in data)

    def test_to_one_relationship_url(self):
        """Test for fetching a resource from a to-one relationship URL.

        The response to a request to a to-many relationship URL should
        be a linkage object, *not* a resource object.

        For more information, see the `Fetching Relationships`_ section  of JSON API specification.

        .. _Fetching Relationships: https://jsonapi.org/format/#fetching-relationships

        """
        self.session.bulk_save_objects([
            Person(pk=1),
            Article(id=1, author_id=1)
        ])
        self.session.commit()

        document = self.fetch_and_validate('/api/article/1/relationships/author')

        data = document['data']
        assert ['id', 'type'] == sorted(data)
        assert data['id'] == '1'
        assert data['type'] == 'person'

    def test_empty_to_one_relationship_url(self):
        """Test for fetching from an empty to-one relationship URL.

        For more information, see the `Fetching Relationships`_ section of JSON API specification.

        .. _Fetching Relationships: https://jsonapi.org/format/#fetching-relationships

        """

        self.session.add(Article(id=1))
        self.session.commit()

        document = self.fetch_and_validate('/api/article/1/relationships/author')

        assert document['data'] is None

    def test_relationship_links(self):
        """Tests for links included in relationship objects.

        For more information, see the `Fetching Relationships`_ section
        of JSON API specification.

        .. _Fetching Relationships: https://jsonapi.org/format/#fetching-relationships

        """

        self.session.add(Article(id=1))
        self.session.commit()
        document = self.fetch_and_validate('/api/article/1/relationships/author')

        links = document['links']
        assert links['self'] == '/api/article/1/relationships/author'
        assert links['related'] == '/api/article/1/author'
