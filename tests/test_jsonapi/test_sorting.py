
import pytest

from flask_restless import APIManager

from ..conftest import BaseTestClass
from .models import Article, Comment
from .models import Base
from .models import Person


class TestSorting(BaseTestClass):
    """Tests corresponding to the `Sorting`_ section of the JSON API
    specification.

    .. _Sorting: https://jsonapi.org/format/#fetching-sorting

    """

    @pytest.fixture(autouse=True)
    def setup(self):
        manager = APIManager(self.app, session=self.session)
        manager.create_api(Article)
        manager.create_api(Person)
        manager.create_api(Comment)
        Base.metadata.create_all(bind=self.engine)
        yield
        Base.metadata.drop_all(bind=self.engine)

    def test_sort_increasing(self):
        """Tests that the client can specify the fields on which to sort
        the response in increasing order.

        For more information, see the `Sorting`_ section of the JSON API
        specification.

        .. _Sorting: https://jsonapi.org/format/#fetching-sorting

        """
        self.session.bulk_save_objects([
            Person(name=u'foo', age=20),
            Person(name=u'bar', age=10),
            Person(name=u'baz', age=30)
        ])
        self.session.commit()
        document = self.fetch_and_validate('/api/person', query_string={'sort': 'age'})
        people = document['data']
        age1, age2, age3 = (person['attributes']['age'] for person in people)
        assert age1 <= age2 <= age3

    def test_sort_decreasing(self):
        """Tests that the client can specify the fields on which to sort
        the response in decreasing order.

        For more information, see the `Sorting`_ section of the JSON API
        specification.

        .. _Sorting: https://jsonapi.org/format/#fetching-sorting

        """
        self.session.bulk_save_objects([
            Person(name=u'foo', age=20),
            Person(name=u'bar', age=10),
            Person(name=u'baz', age=30)
        ])
        self.session.commit()
        document = self.fetch_and_validate('/api/person', query_string={'sort': '-age'})
        people = document['data']
        age1, age2, age3 = (person['attributes']['age'] for person in people)
        assert age1 >= age2 >= age3

    def test_sort_multiple_fields(self):
        """Tests that the client can sort by multiple fields.

        For more information, see the `Sorting`_ section of the JSON API
        specification.

        .. _Sorting: https://jsonapi.org/format/#fetching-sorting

        """
        self.session.bulk_save_objects([
            Person(name=u'foo', age=99),
            Person(name=u'bar', age=99),
            Person(name=u'baz', age=80),
            Person(name=u'xyz', age=80)
        ])
        self.session.commit()
        # Sort by age, decreasing, then by name, increasing.
        query_string = {'sort': '-age,name'}
        document = self.fetch_and_validate('/api/person', query_string=query_string)
        people = document['data']
        p1, p2, p3, p4 = (person['attributes'] for person in people)
        assert p1['age'] == p2['age'] >= p3['age'] == p4['age']
        assert p1['name'] <= p2['name']
        assert p3['name'] <= p4['name']

    def test_sort_relationship_attributes(self):
        """Tests that the client can sort by relationship attributes.

        For more information, see the `Sorting`_ section of the JSON API
        specification.

        .. _Sorting: https://jsonapi.org/format/#fetching-sorting

        """
        self.session.add_all([
            Person(pk=1, age=20),
            Person(pk=2, age=10),
            Person(pk=3, age=30),
            Article(id=1, author_id=1),
            Article(id=2, author_id=2),
            Article(id=3, author_id=3),
        ])
        self.session.commit()
        query_string = {'sort': 'author.age'}
        document = self.fetch_and_validate('/api/article', query_string=query_string)
        articles = document['data']
        assert ['2', '1', '3'] == [article['id'] for article in articles]

    def test_sort_multiple_relationship_attributes(self):
        """Tests that the client can sort by multiple relationship
        attributes.

        For more information, see the `Sorting`_ section of the JSON API
        specification.

        .. _Sorting: https://jsonapi.org/format/#fetching-sorting

        """
        self.session.bulk_save_objects([
            Person(pk=1, age=2, name=u'd'),
            Person(pk=2, age=1, name=u'b'),
            Person(pk=3, age=1, name=u'a'),
            Person(pk=4, age=2, name=u'c'),
        ])
        self.session.bulk_save_objects([Article(id=i, author_id=i) for i in range(1, 5)])
        self.session.commit()
        query_string = {'sort': 'author.age,author.name'}
        document = self.fetch_and_validate('/api/article', query_string=query_string)
        articles = document['data']
        assert ['3', '2', '4', '1'] == [article['id'] for article in articles]

    def test_sorting_relationship(self):
        """Tests for sorting relationship objects when requesting
        information from a to-many relationship endpoint.

        For more information, see the `Sorting`_ section of the JSON API
        specification.

        .. _Sorting: https://jsonapi.org/format/#fetching-sorting

        """
        self.session.add(Person(pk=1))
        self.session.bulk_save_objects([Article(id=i, title=str(i), author_id=1) for i in range(5)])
        self.session.commit()
        query_string = {'sort': '-title'}
        document = self.fetch_and_validate('/api/person/1/relationships/articles', query_string=query_string)
        articles = document['data']
        article_ids = [article['id'] for article in articles]
        assert ['4', '3', '2', '1', '0'] == article_ids

    def test_bad_request_on_incorrect_sorting_field(self):
        query_string = {'sort': 'unknown'}
        self.fetch_and_validate('/api/person', query_string=query_string, expected_response_code=400, error_msg='No such field unknown')

    def test_bad_request_on_incorrect_sorting_relationship_field(self):
        query_string = {'sort': 'articles.unknown'}
        self.fetch_and_validate('/api/person', query_string=query_string, expected_response_code=400, error_msg='No such field unknown')

    def test_sort_nested_relationship_attributes(self):
        """Tests that the client can sort by nested relationship attributes.

        For more information, see the `Sorting`_ section of the JSON API
        specification.

        .. _Sorting: https://jsonapi.org/format/#fetching-sorting

        """
        self.session.add_all([
            Person(pk=1, age=20),
            Person(pk=2, age=10),
            Person(pk=3, age=30),
            Article(id=1, author_id=1),
            Article(id=2, author_id=2),
            Article(id=3, author_id=3),
            Comment(id=1, author_id=1, article_id=1),
            Comment(id=2, author_id=1, article_id=2),
            Comment(id=3, author_id=1, article_id=3),
            Comment(id=4, author_id=2, article_id=1),
            Comment(id=5, author_id=2, article_id=2),
            Comment(id=6, author_id=3, article_id=1)
        ])
        self.session.commit()
        query_string = {'sort': 'article.author.age'}
        document = self.fetch_and_validate('/api/comment', query_string=query_string)
        comments = document['data']
        assert ['2', '5', '1', '4', '6', '3'] == [comment['id'] for comment in comments]

    def test_sort_multiple_nested_relationship_attributes(self):
        """Tests that the client can sort by multiple nested relationship
        attributes.

        For more information, see the `Sorting`_ section of the JSON API
        specification.

        .. _Sorting: https://jsonapi.org/format/#fetching-sorting

        """
        self.session.bulk_save_objects([
            Person(pk=1, age=2, name=u'b'),
            Person(pk=2, age=1, name=u'd'),
            Person(pk=3, age=1, name=u'a'),
            Article(id=1, author_id=1),
            Article(id=2, author_id=2),
            Article(id=3, author_id=3),
            Comment(id=1, author_id=1, article_id=1),
            Comment(id=2, author_id=1, article_id=2),
            Comment(id=3, author_id=1, article_id=3),
            Comment(id=4, author_id=2, article_id=1),
            Comment(id=5, author_id=2, article_id=2),
            Comment(id=6, author_id=3, article_id=1)
        ])
        self.session.commit()
        query_string = {'sort': 'article.author.age,article.author.name'}
        document = self.fetch_and_validate('/api/comment', query_string=query_string)
        comments = document['data']
        assert ['3', '2', '5', '1', '4', '6'] == [comment['id'] for comment in comments]

    def test_bad_request_on_incorrect_sorting_nested_relationship_field(self):
        query_string = {'sort': 'article.author.unknown'}
        self.fetch_and_validate('/api/comment', query_string=query_string, expected_response_code=400, error_msg='No such field unknown')
