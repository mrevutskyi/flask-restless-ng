# test_manager.py - unit tests for the manager module
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
"""Unit tests for the :mod:`flask_restless.manager` module."""
from flask import Flask
from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Unicode
from sqlalchemy.orm import backref
from sqlalchemy.orm import relationship

from flask_restless import APIManager
from flask_restless import IllegalArgumentError

from .helpers import ManagerTestBase
from .helpers import SQLAlchemyTestBase
from .helpers import force_content_type_jsonapi


class TestLocalAPIManager(SQLAlchemyTestBase):
    """Provides tests for :class:`flask_restless.APIManager` when the tests
    require that the instance of :class:`flask_restless.APIManager` has not
    yet been instantiated.

    """

    def setUp(self):
        super().setUp()

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)

        self.Person = Person
        self.Article = Article
        self.Base.metadata.create_all(bind=self.engine)

    def test_missing_session(self):
        """Tests that setting neither a session nor a Flask-SQLAlchemy
        object yields an error.

        """
        with self.assertRaises(ValueError):
            APIManager(app=self.flaskapp)

    def test_constructor_app(self):
        """Tests for providing a :class:`~flask.Flask` application in
        the constructor.

        """
        manager = APIManager(app=self.flaskapp, session=self.session)
        manager.create_api(self.Person)
        response = self.app.get('/api/person')
        assert response.status_code == 200

    def test_single_manager_init_single_app(self):
        """Tests for calling :meth:`~APIManager.init_app` with a single
        :class:`~flask.Flask` application after calling
        :meth:`~APIManager.create_api`.

        """
        manager = APIManager(session=self.session)
        manager.create_api(self.Person)
        manager.init_app(self.flaskapp)
        response = self.app.get('/api/person')
        assert response.status_code == 200

    def test_single_manager_init_multiple_apps(self):
        """Tests for calling :meth:`~APIManager.init_app` on multiple
        :class:`~flask.Flask` applications after calling
        :meth:`~APIManager.create_api`.

        """
        manager = APIManager(session=self.session)
        flaskapp1 = self.flaskapp
        flaskapp2 = Flask(__name__)
        testclient1 = self.app
        testclient2 = flaskapp2.test_client()
        force_content_type_jsonapi(testclient2)
        manager.create_api(self.Person)
        manager.init_app(flaskapp1)
        manager.init_app(flaskapp2)
        response = testclient1.get('/api/person')
        assert response.status_code == 200
        response = testclient2.get('/api/person')
        assert response.status_code == 200

    def test_multiple_managers_init_single_app(self):
        """Tests for calling :meth:`~APIManager.init_app` on a single
        :class:`~flask.Flask` application after calling
        :meth:`~APIManager.create_api` on multiple instances of
        :class:`APIManager`.

        """
        manager1 = APIManager(session=self.session)
        manager2 = APIManager(session=self.session)

        # First create the API, then initialize the Flask applications after.
        manager1.create_api(self.Person)
        manager2.create_api(self.Article)
        manager1.init_app(self.flaskapp)
        manager2.init_app(self.flaskapp)

        # Tests that both endpoints are accessible on the Flask application.
        response = self.app.get('/api/person')
        assert response.status_code == 200
        response = self.app.get('/api/article')
        assert response.status_code == 200

    def test_multiple_managers_init_multiple_apps(self):
        """Tests for calling :meth:`~APIManager.init_app` on multiple
        :class:`~flask.Flask` applications after calling
        :meth:`~APIManager.create_api` on multiple instances of
        :class:`APIManager`.

        """
        manager1 = APIManager(session=self.session)
        manager2 = APIManager(session=self.session)

        # Create the Flask applications and the test clients.
        flaskapp1 = self.flaskapp
        flaskapp2 = Flask(__name__)
        testclient1 = self.app
        testclient2 = flaskapp2.test_client()
        force_content_type_jsonapi(testclient2)

        # First create the API, then initialize the Flask applications after.
        manager1.create_api(self.Person)
        manager2.create_api(self.Article)
        manager1.init_app(flaskapp1)
        manager2.init_app(flaskapp2)

        # Tests that only the first Flask application gets requests for
        # /api/person and only the second gets requests for /api/article.
        response = testclient1.get('/api/person')
        assert response.status_code == 200
        response = testclient1.get('/api/article')
        assert response.status_code == 404
        response = testclient2.get('/api/person')
        assert response.status_code == 404
        response = testclient2.get('/api/article')
        assert response.status_code == 200

    def test_universal_preprocessor(self):
        """Tests universal preprocessor and postprocessor applied to all
        methods created with the API manager.

        """
        class Counter:
            """An object that increments a counter on each invocation."""

            def __init__(self):
                self._counter = 0

            def __call__(self, *args, **kw):
                self._counter += 1

            def __eq__(self, other):
                if isinstance(other, Counter):
                    return self._counter == other._counter
                if isinstance(other, int):
                    return self._counter == other
                return False

        increment1 = Counter()
        increment2 = Counter()

        preprocessors = dict(GET_COLLECTION=[increment1])
        postprocessors = dict(GET_COLLECTION=[increment2])
        manager = APIManager(self.flaskapp, session=self.session,
                             preprocessors=preprocessors,
                             postprocessors=postprocessors)
        manager.create_api(self.Person)
        manager.create_api(self.Article)
        # After each request, regardless of API endpoint, both counters should
        # be incremented.
        self.app.get('/api/person')
        self.app.get('/api/article')
        self.app.get('/api/person')
        assert increment1 == increment2 == 3

    def test_url_prefix(self):
        """Tests for specifying a URL prefix at the manager level but
        not when creating an API.

        """
        manager = APIManager(self.flaskapp, session=self.session,
                             url_prefix='/foo')
        manager.create_api(self.Person)
        response = self.app.get('/foo/person')
        assert response.status_code == 200
        response = self.app.get('/api/person')
        assert response.status_code == 404

    def test_empty_url_prefix(self):
        """Tests for specifying an empty string as URL prefix at the manager
        level but not when creating an API.

        """
        manager = APIManager(self.flaskapp, session=self.session,
                             url_prefix='')
        manager.create_api(self.Person)
        response = self.app.get('/person')
        assert response.status_code == 200
        response = self.app.get('/api/person')
        assert response.status_code == 404

    def test_override_url_prefix(self):
        """Tests that a call to :meth:`APIManager.create_api` can
        override the URL prefix provided in the constructor to the
        manager class, if the new URL starts with a slash.

        """
        manager = APIManager(self.flaskapp, session=self.session, url_prefix='/foo')
        manager.create_api(self.Person, url_prefix='/bar')
        manager.create_api(self.Article, url_prefix='')
        response = self.app.get('/bar/person')
        assert response.status_code == 200
        response = self.app.get('/article')
        assert response.status_code == 200
        response = self.app.get('/foo/person')
        assert response.status_code == 404
        response = self.app.get('/foo/article')
        assert response.status_code == 404


class TestAPIManager(ManagerTestBase):
    """Unit tests for the :class:`flask_restless.manager.APIManager` class."""

    def setUp(self):
        super().setUp()

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode)

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            title = Column(Unicode)
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship(Person, backref=backref('articles'))

        class Tag(self.Base):
            __tablename__ = 'tag'
            name = Column(Unicode, primary_key=True)

        class Foo(self.Base):
            __tablename__ = 'foo'

            a = Column(Unicode, primary_key=True)
            b = Column(Integer)

        self.Article = Article
        self.Person = Person
        self.Tag = Tag
        self.Foo = Foo
        self.Base.metadata.create_all(bind=self.engine)

    def test_url_for(self):
        """Tests the global :func:`flask_restless.url_for` function."""
        self.manager.create_api(self.Person, collection_name='people')
        self.manager.create_api(self.Article, collection_name='articles')
        with self.flaskapp.test_request_context():
            url1 = self.manager.url_for(self.Person)
            url2 = self.manager.url_for(self.Person, resource_id=1)
            url3 = self.manager.url_for(self.Person, resource_id=1, relation_name='articles')
            url4 = self.manager.url_for(self.Person, resource_id=1, relation_name='articles', related_resource_id=2)
            assert url1.endswith('/api/people')
            assert url2.endswith('/api/people/1')
            assert url3.endswith('/api/people/1/articles')
            assert url4.endswith('/api/people/1/articles/2')

    def test_url_for_explicitly_sets_primary_key_in_links(self):
        """Should use the primary_key explicitly set when generating links"""
        instance = self.Foo(b=1, a=u'foo_bar')
        self.session.add(instance)
        self.session.commit()
        self.manager.include_links = True
        self.manager.create_api(self.Foo, primary_key='a')

        response = self.app.get('/api/foo')
        document = response.json
        articles = document['data']
        article = articles[0]

        assert 'foo_bar' in article['links']['self']
        assert '/1' not in article['links']['self']

    def test_url_for_nonexistent(self):
        """Tests that attempting to get the URL for an unknown model yields an
        error.

        """
        with self.assertRaises(ValueError):
            self.manager.url_for(self.Person)

    def test_collection_name(self):
        """Tests the global :func:`flask_restless.collection_name`
        function.

        """
        self.manager.create_api(self.Person, collection_name='people')
        assert self.manager.collection_name(self.Person) == 'people'

    def test_collection_name_nonexistent(self):
        """Tests that attempting to get the collection name for an unknown
        model yields an error.

        """
        with self.assertRaises(ValueError):
            self.manager.collection_name(self.Person)

    def test_serializer_for(self):
        """Tests the global :func:`flask_restless.serializer_for`
        function.

        """
        def my_function(*args, **kw):
            pass

        self.manager.create_api(self.Person, serializer=my_function)

    def test_disallowed_methods(self):
        """Tests that disallowed methods respond with :http:status:`405`."""
        self.manager.create_api(self.Person, methods=[])
        for method in 'get', 'post', 'patch', 'delete':
            func = getattr(self.app, method)
            response = func('/api/person')
            assert response.status_code == 405

    def test_missing_id(self):
        """Tests that calling :meth:`APIManager.create_api` on a model without
        an ``id`` column does not raise an exception if `primary_key` is not
        provided
        """
        self.manager.create_api(self.Tag)

    def test_empty_collection_name(self):
        """Tests that calling :meth:`APIManager.create_api` with an empty
        collection name raises an exception.

        """
        with self.assertRaises(IllegalArgumentError):
            self.manager.create_api(self.Person, collection_name='')

    def test_only_and_exclude(self):
        """Tests that attempting to use both ``only`` and ``exclude``
        keyword arguments yields an error.

        """
        with self.assertRaises(IllegalArgumentError):
            self.manager.create_api(self.Person, only=['id'], exclude=['name'])

    def test_additional_attributes_nonexistent(self):
        """Tests that an attempt to include an additional attribute that
        does not exist on the model raises an exception at the time of
        API creation.

        """
        with self.assertRaises(AttributeError):
            self.manager.create_api(self.Person, additional_attributes=['bogus'])
