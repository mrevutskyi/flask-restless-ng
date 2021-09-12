import pytest

from flask_restless import APIManager

from ..conftest import BaseTestClass
from .models import Article
from .models import Base
from .models import Person


class TestSparseFieldsets(BaseTestClass):
    """Tests corresponding to the `Sparse Fieldsets`_ section of the
    JSON API specification.

    .. _Sparse Fieldsets: https://jsonapi.org/format/#fetching-sparse-fieldsets

    """

    @pytest.fixture(autouse=True)
    def setup(self):
        manager = APIManager(self.app, session=self.session)
        manager.create_api(Article)
        manager.create_api(Person)
        Base.metadata.create_all(bind=self.engine)
        yield
        Base.metadata.drop_all(bind=self.engine)

    def test_sparse_fieldsets(self):
        """Tests that the client can specify which fields to return in the
        response of a fetch request for a single object.

        For more information, see the `Sparse Fieldsets`_ section
        of the JSON API specification.

        .. _Sparse Fieldsets: https://jsonapi.org/format/#fetching-sparse-fieldsets

        """
        self.session.add(Person(pk=1, name=u'foo', age=99))
        self.session.commit()
        query_string = {'fields[person]': 'id,name'}
        document = self.fetch_and_validate('/api/person/1', query_string=query_string)
        person = document['data']
        # ID and type must always be included.
        assert ['attributes', 'id', 'type'] == sorted(person)
        assert ['name'] == sorted(person['attributes'])

    def test_sparse_fieldsets_id_and_type(self):
        """Tests that the ID and type of the resource are always included in a
        response from a request for sparse fieldsets, regardless of what the
        client requests.

        For more information, see the `Sparse Fieldsets`_ section
        of the JSON API specification.

        .. _Sparse Fieldsets: https://jsonapi.org/format/#fetching-sparse-fieldsets

        """
        self.session.add(Person(pk=1, name=u'foo', age=99))
        self.session.commit()
        query_string = {'fields[person]': 'id'}
        document = self.fetch_and_validate('/api/person/1', query_string=query_string)
        person = document['data']
        # ID and type must always be included.
        assert ['id', 'type'] == sorted(person)

    def test_sparse_fieldsets_collection(self):
        """Tests that the client can specify which fields to return in the
        response of a fetch request for a collection of objects.

        For more information, see the `Sparse Fieldsets`_ section
        of the JSON API specification.

        .. _Sparse Fieldsets: https://jsonapi.org/format/#fetching-sparse-fieldsets

        """
        self.session.add_all([
            Person(pk=1, name=u'foo', age=99),
            Person(pk=2, name=u'bar', age=80)
        ])
        self.session.commit()
        query_string = {'fields[person]': 'id,name'}
        document = self.fetch_and_validate('/api/person', query_string=query_string)
        people = document['data']
        assert all(['attributes', 'id', 'type'] == sorted(person) for person in people)
        assert all(['name'] == list(person['attributes']) for person in people)

    def test_sparse_fieldsets_multiple_types(self):
        """Tests that the client can specify which fields to return in the
        response with multiple types specified.

        For more information, see the `Sparse Fieldsets`_ section
        of the JSON API specification.

        .. _Sparse Fieldsets: https://jsonapi.org/format/#fetching-sparse-fieldsets

        """
        self.session.add_all([
            Person(pk=1, name=u'foo', age=99),
            Article(id=1, title=u'bar', author_id=1)
        ])
        self.session.commit()
        # Person objects should only have ID and name, while article objects
        # should only have ID.
        query_string = {'include': 'articles',
                        'fields[person]': 'id,name,articles',
                        'fields[article]': 'id'}
        document = self.fetch_and_validate('/api/person/1', query_string=query_string)
        person = document['data']
        linked = document['included']
        # We requested 'id', 'name', and 'articles'; 'id' and 'type' must
        # always be present; 'name' comes under an 'attributes' key; and
        # 'articles' comes under a 'links' key.
        assert ['attributes', 'id', 'relationships', 'type'] == sorted(person)
        assert ['articles'] == sorted(person['relationships'])
        assert ['name'] == sorted(person['attributes'])
        # We requested only 'id', but 'type' must always appear as well.
        assert all(['id', 'type'] == sorted(article) for article in linked)
