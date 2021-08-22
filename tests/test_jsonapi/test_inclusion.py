import pytest

from flask_restless import APIManager

from ..conftest import BaseTestClass
from .models import Article
from .models import Base
from .models import Comment
from .models import Person


class TestInclusion(BaseTestClass):
    """Tests corresponding to the `Inclusion of Related Resources`_section of the JSON API specification.

    .. _Inclusion of Related Resources: https://jsonapi.org/format/#fetching-includes

    """

    @pytest.fixture(autouse=True)
    def setup(self):
        manager = APIManager(self.app, session=self.session)
        manager.create_api(Article)
        manager.create_api(Person)
        manager.create_api(Comment)
        self.manager = manager

        Base.metadata.create_all(bind=self.engine)
        yield
        Base.metadata.drop_all(bind=self.engine)

    def test_default_inclusion(self):
        """Tests that by default, Flask-Restless includes no information in compound documents.

        For more information, see the `Inclusion of Related Resources`_ section of the JSON API specification.

        .. _Inclusion of Related Resources: https://jsonapi.org/format/#fetching-includes

        """

        self.session.add_all([Person(pk=1), Article(id=1, author_id=1)])
        self.session.commit()
        document = self.fetch_and_validate('/api/person/1')
        articles = document['data']['relationships']['articles']['data']
        assert ['1'] == sorted(article['id'] for article in articles)
        # By default, no links will be included at the top level of the document.
        assert 'included' not in document

    def test_set_default_inclusion(self):
        """Tests that the user can specify default compound document inclusions when creating an API.

        For more information, see the `Inclusion of Related Resources`_ section of the JSON API specification.

        .. _Inclusion of Related Resources: https://jsonapi.org/format/#fetching-includes

        """
        self.session.add_all([Person(pk=1), Article(id=1, author_id=1)])
        self.session.commit()
        self.manager.create_api(Person, includes=['articles'], url_prefix='/api2')
        # In the alternate API, articles are included by default in compound documents.
        document = self.fetch_and_validate('/api2/person/1')
        person = document['data']
        linked = document['included']
        articles = person['relationships']['articles']['data']
        assert ['1'] == sorted(article['id'] for article in articles)
        assert linked[0]['type'] == 'article'
        assert linked[0]['id'] == '1'

    def test_include(self):
        """Tests that the client can specify which linked relations to include in a compound document.

        For more information, see the `Inclusion of Related Resources`_ section of the JSON API specification.

        .. _Inclusion of Related Resources: https://jsonapi.org/format/#fetching-includes

        """
        self.session.add_all([
            Person(pk=1, name=u'foo'),
            Article(id=1, author_id=1),
            Article(id=2, author_id=1),
            Comment(author_id=1)
        ])

        self.session.commit()
        document = self.fetch_and_validate('/api/person/1?include=articles')
        # If a client supplied an include request parameter, no other types of objects should be included.
        assert all(resource['type'] == 'article' for resource in document['included'])
        assert ['1', '2'] == sorted(resource['id'] for resource in document['included'])

    def test_include_for_collection(self):
        self.session.add_all([Person(pk=1, name=u'foo'), Person(pk=2, name=u'bar'), Person(pk=3, name=u'baz')])
        self.session.add_all([Article(id=1, author_id=1), Article(id=2, author_id=2), Article(id=3, author_id=3)])
        self.session.add_all([Comment(id=1, author_id=1, article_id=1)])
        self.session.commit()
        document = self.fetch_and_validate('/api/person?include=articles,articles.comments')
        assert len(document['included']) == 4

    def test_include_multiple(self):
        """Tests that the client can specify multiple linked relations to include in a compound document.

        For more information, see the `Inclusion of Related Resources`_ section of the JSON API specification.

        .. _Inclusion of Related Resources: https://jsonapi.org/format/#fetching-includes

        """
        self.session.add_all([
            Person(pk=1, name=u'foo'),
            Article(id=2, author_id=1),
            Comment(id=3, author_id=1)
        ])
        self.session.commit()
        document = self.fetch_and_validate('/api/person/1?include=articles,comments')
        # Sort the linked objects by type; 'article' comes before 'comment' lexicographically.
        included = sorted(document['included'], key=lambda x: x['type'])
        linked_article, linked_comment = included
        assert linked_article['type'] == 'article'
        assert linked_article['id'] == '2'
        assert linked_comment['type'] == 'comment'
        assert linked_comment['id'] == '3'

    def test_include_does_not_try_to_serialize_none(self):
        """Tests that API correctly processes inclusion of empty relationships"""
        self.session.add_all([Article(id=1), Comment(id=1, article_id=1)])
        self.session.commit()
        document = self.fetch_and_validate('/api/article/1?include=comments.author')
        assert len(document['included']) == 1

    def test_include_relationship_of_none(self):
        """If in a chain of relationships A -> B -> C,  B is Null/None, include=b.c should not cause an error"""
        self.session.add(Article(id=1))
        self.session.commit()
        document = self.fetch_and_validate('/api/article/1?include=author.comments')
        assert document['included'] == []

    @pytest.mark.parametrize('endpoint', ['/api/article/1/relationships/comments', '/api/article/1'])
    def test_include_intermediate_resources(self, endpoint):
        """Tests that intermediate resources from a multi-part relationship path are included in a compound document.

        For more information, see the `Inclusion of Related Resources`_ section of the JSON API specification.

        .. _Inclusion of Related Resources: https://jsonapi.org/format/#fetching-includes

        """
        self.session.add_all([
            Person(pk=1),
            Person(pk=2),
            Article(id=1),
            Comment(id=1, article_id=1, author_id=1),
            Comment(id=2, article_id=1, author_id=2),
        ])
        self.session.commit()

        document = self.fetch_and_validate(f'{endpoint}?include=comments.author')
        included = document['included']
        # The included resources should be the two comments and the two authors of those comments.
        assert len(included) == 4
        authors = [resource for resource in included if resource['type'] == 'person']
        comments = [resource for resource in included if resource['type'] == 'comment']
        assert ['1', '2'] == sorted(author['id'] for author in authors)
        assert ['1', '2'] == sorted(comment['id'] for comment in comments)

    def test_client_overrides_server_includes(self):
        """Tests that if a client supplies an include query parameter, the server does not include any other resource objects in the included
        section of the compound document.

        For more information, see the `Inclusion of Related Resources`_ section of the JSON API specification.

        .. _Inclusion of Related Resources: https://jsonapi.org/format/#fetching-includes

        """
        self.session.add_all([
            Person(pk=1),
            Article(id=2, author_id=1),
            Comment(id=3, author_id=1)
        ])
        self.session.commit()
        # The server will, by default, include articles. The client will override this and request only comments.
        self.manager.create_api(Person, url_prefix='/api3', includes=['articles'])
        document = self.fetch_and_validate('/api3/person/1?include=comments')
        included = document['included']
        assert ['3'] == sorted(resource['id'] for resource in included)
        assert ['comment'] == sorted(resource['type'] for resource in included)
