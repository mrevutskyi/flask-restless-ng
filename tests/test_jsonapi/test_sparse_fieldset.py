from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Unicode
from sqlalchemy.orm import relationship

from ..helpers import ManagerTestBase
from ..helpers import validate_schema


class TestSparseFieldsets(ManagerTestBase):
    """Tests corresponding to the `Sparse Fieldsets`_ section of the
    JSON API specification.

    .. _Sparse Fieldsets: http://jsonapi.org/format/#fetching-sparse-fieldsets

    """

    def setUp(self):
        super(TestSparseFieldsets, self).setUp()

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            title = Column(Unicode)
            author_id = Column(Integer, ForeignKey('person.id'))

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode)
            age = Column(Integer)
            articles = relationship('Article', backref='author')

        self.Article = Article
        self.Person = Person
        self.Base.metadata.create_all()
        self.manager.create_api(Article)
        self.manager.create_api(Person)

    def test_sparse_fieldsets(self):
        """Tests that the client can specify which fields to return in the
        response of a fetch request for a single object.

        For more information, see the `Sparse Fieldsets`_ section
        of the JSON API specification.

        .. _Sparse Fieldsets: http://jsonapi.org/format/#fetching-sparse-fieldsets

        """
        person = self.Person(id=1, name=u'foo', age=99)
        self.session.add(person)
        self.session.commit()
        query_string = {'fields[person]': 'id,name'}
        response = self.app.get('/api/person/1', query_string=query_string)
        document = response.json
        validate_schema(document)
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

        .. _Sparse Fieldsets: http://jsonapi.org/format/#fetching-sparse-fieldsets

        """
        person = self.Person(id=1, name=u'foo', age=99)
        self.session.add(person)
        self.session.commit()
        query_string = {'fields[person]': 'id'}
        response = self.app.get('/api/person/1', query_string=query_string)
        document = response.json
        validate_schema(document)
        person = document['data']
        # ID and type must always be included.
        assert ['id', 'type'] == sorted(person)

    def test_sparse_fieldsets_collection(self):
        """Tests that the client can specify which fields to return in the
        response of a fetch request for a collection of objects.

        For more information, see the `Sparse Fieldsets`_ section
        of the JSON API specification.

        .. _Sparse Fieldsets: http://jsonapi.org/format/#fetching-sparse-fieldsets

        """
        person1 = self.Person(id=1, name=u'foo', age=99)
        person2 = self.Person(id=2, name=u'bar', age=80)
        self.session.add_all([person1, person2])
        self.session.commit()
        query_string = {'fields[person]': 'id,name'}
        response = self.app.get('/api/person', query_string=query_string)
        document = response.json
        validate_schema(document)
        people = document['data']
        assert all(['attributes', 'id', 'type'] == sorted(p) for p in people)
        assert all(['name'] == sorted(p['attributes']) for p in people)

    def test_sparse_fieldsets_multiple_types(self):
        """Tests that the client can specify which fields to return in the
        response with multiple types specified.

        For more information, see the `Sparse Fieldsets`_ section
        of the JSON API specification.

        .. _Sparse Fieldsets: http://jsonapi.org/format/#fetching-sparse-fieldsets

        """
        article = self.Article(id=1, title=u'bar')
        person = self.Person(id=1, name=u'foo', age=99, articles=[article])
        self.session.add_all([person, article])
        self.session.commit()
        # Person objects should only have ID and name, while article objects
        # should only have ID.
        query_string = {'include': 'articles',
                        'fields[person]': 'id,name,articles',
                        'fields[article]': 'id'}
        response = self.app.get('/api/person/1', query_string=query_string)
        document = response.json
        validate_schema(document)
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
