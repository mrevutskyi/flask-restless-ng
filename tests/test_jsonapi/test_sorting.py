from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Unicode
from sqlalchemy.orm import relationship

from ..helpers import ManagerTestBase
from ..helpers import validate_schema


class TestSorting(ManagerTestBase):
    """Tests corresponding to the `Sorting`_ section of the JSON API
    specification.

    .. _Sorting: http://jsonapi.org/format/#fetching-sorting

    """

    def setUp(self):
        super(TestSorting, self).setUp()

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

    def test_sort_increasing(self):
        """Tests that the client can specify the fields on which to sort
        the response in increasing order.

        For more information, see the `Sorting`_ section of the JSON API
        specification.

        .. _Sorting: http://jsonapi.org/format/#fetching-sorting

        """
        person1 = self.Person(name=u'foo', age=20)
        person2 = self.Person(name=u'bar', age=10)
        person3 = self.Person(name=u'baz', age=30)
        self.session.add_all([person1, person2, person3])
        self.session.commit()
        query_string = {'sort': 'age'}
        response = self.app.get('/api/person', query_string=query_string)
        document = response.json
        validate_schema(document)
        people = document['data']
        age1, age2, age3 = (p['attributes']['age'] for p in people)
        assert age1 <= age2 <= age3

    def test_sort_decreasing(self):
        """Tests that the client can specify the fields on which to sort
        the response in decreasing order.

        For more information, see the `Sorting`_ section of the JSON API
        specification.

        .. _Sorting: http://jsonapi.org/format/#fetching-sorting

        """
        person1 = self.Person(name=u'foo', age=20)
        person2 = self.Person(name=u'bar', age=10)
        person3 = self.Person(name=u'baz', age=30)
        self.session.add_all([person1, person2, person3])
        self.session.commit()
        query_string = {'sort': '-age'}
        response = self.app.get('/api/person', query_string=query_string)
        document = response.json
        validate_schema(document)
        people = document['data']
        age1, age2, age3 = (p['attributes']['age'] for p in people)
        assert age1 >= age2 >= age3

    def test_sort_multiple_fields(self):
        """Tests that the client can sort by multiple fields.

        For more information, see the `Sorting`_ section of the JSON API
        specification.

        .. _Sorting: http://jsonapi.org/format/#fetching-sorting

        """
        person1 = self.Person(name=u'foo', age=99)
        person2 = self.Person(name=u'bar', age=99)
        person3 = self.Person(name=u'baz', age=80)
        person4 = self.Person(name=u'xyzzy', age=80)
        self.session.add_all([person1, person2, person3, person4])
        self.session.commit()
        # Sort by age, decreasing, then by name, increasing.
        query_string = {'sort': '-age,name'}
        response = self.app.get('/api/person', query_string=query_string)
        document = response.json
        validate_schema(document)
        people = document['data']
        p1, p2, p3, p4 = (p['attributes'] for p in people)
        assert p1['age'] == p2['age'] >= p3['age'] == p4['age']
        assert p1['name'] <= p2['name']
        assert p3['name'] <= p4['name']

    def test_sort_relationship_attributes(self):
        """Tests that the client can sort by relationship attributes.

        For more information, see the `Sorting`_ section of the JSON API
        specification.

        .. _Sorting: http://jsonapi.org/format/#fetching-sorting

        """
        person1 = self.Person(age=20)
        person2 = self.Person(age=10)
        person3 = self.Person(age=30)
        article1 = self.Article(id=1, author=person1)
        article2 = self.Article(id=2, author=person2)
        article3 = self.Article(id=3, author=person3)
        self.session.add_all([person1, person2, person3, article1, article2,
                              article3])
        self.session.commit()
        query_string = {'sort': 'author.age'}
        response = self.app.get('/api/article', query_string=query_string)
        document = response.json
        validate_schema(document)
        articles = document['data']
        assert ['2', '1', '3'] == [c['id'] for c in articles]

    def test_sort_multiple_relationship_attributes(self):
        """Tests that the client can sort by multiple relationship
        attributes.

        For more information, see the `Sorting`_ section of the JSON API
        specification.

        .. _Sorting: http://jsonapi.org/format/#fetching-sorting

        """
        person1 = self.Person(age=2, name=u'd')
        person2 = self.Person(age=1, name=u'b')
        person3 = self.Person(age=1, name=u'a')
        person4 = self.Person(age=2, name=u'c')
        people = [person1, person2, person3, person4]
        articles = [self.Article(id=i, author=person)
                    for i, person in enumerate(people, start=1)]
        self.session.add_all(people + articles)
        self.session.commit()
        query_string = {'sort': 'author.age,author.name'}
        response = self.app.get('/api/article', query_string=query_string)
        document = response.json
        validate_schema(document)
        articles = document['data']
        assert ['3', '2', '4', '1'] == [c['id'] for c in articles]

    def test_sorting_relationship(self):
        """Tests for sorting relationship objects when requesting
        information from a to-many relationship endpoint.

        For more information, see the `Sorting`_ section of the JSON API
        specification.

        .. _Sorting: http://jsonapi.org/format/#fetching-sorting

        """
        person = self.Person(id=1)
        articles = [self.Article(id=i, title=str(i), author=person) for i in range(5)]
        self.session.add(person)
        self.session.add_all(articles)
        self.session.commit()
        query_string = dict(sort='-title')
        response = self.app.get('/api/person/1/relationships/articles',
                                query_string=query_string)
        document = response.json
        validate_schema(document)
        articles = document['data']
        articleids = [article['id'] for article in articles]
        assert ['4', '3', '2', '1', '0'] == articleids
