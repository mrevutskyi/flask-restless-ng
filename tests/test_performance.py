import cProfile
import pstats
import time
import unittest

from flask import Flask
from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Unicode
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import backref
from sqlalchemy.orm import relationship
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm import sessionmaker

from flask_restless import APIManager

Base = declarative_base()


class Person(Base):
    __tablename__ = 'person'

    id = Column(Integer, primary_key=True)
    name = Column(Unicode)


class Article(Base):
    __tablename__ = 'article'

    id = Column(Integer, primary_key=True)
    title = Column(String(16))
    author_id = Column(Integer, ForeignKey('person.id'))

    author = relationship('Person', backref=backref('articles'))
    comments = relationship('Comment', backref=backref('article'))


class Comment(Base):
    __tablename__ = 'comment'

    id = Column(Integer, primary_key=True)
    author_id = Column(Integer, ForeignKey('person.id'))
    article_id = Column(Integer, ForeignKey('article.id'))


@unittest.skip("Slow test, for manual run only")
class TestPerformance(unittest.TestCase):

    def setUp(self):
        app = Flask(__name__)
        self.engine = create_engine('sqlite://', echo=False)
        session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=self.engine))()

        Base.metadata.create_all(bind=self.engine)
        session.bulk_save_objects([Person(id=i, name=f'Person {i}') for i in range(1, 10001)])
        session.bulk_save_objects([Article(id=i, title=f'Title {i}', author_id=i % 3) for i in range(1, 101)])
        session.bulk_save_objects([Comment(id=i, author_id=i, article_id=i) for i in range(1, 11)])

        self.test_client = app.test_client()

        api_manager = APIManager(app=app, session=session, url_prefix='/api', include_links=False)
        api_manager.create_api(Person, collection_name='people', page_size=0)
        api_manager.create_api(Article, collection_name='articles', page_size=0)
        api_manager.create_api(Comment, collection_name='comments', page_size=0)
        self.profile = cProfile.Profile()

    def tearDown(self):
        Base.metadata.drop_all(self.engine)

    def test_loading_collection(self):
        self.profile.enable()
        start_time = time.time()
        response = self.test_client.get('/api/people?include=articles')
        self.profile.disable()
        processing_time = time.time() - start_time
        print('Fetch 10000 authors with include time:', processing_time)
        stats = pstats.Stats(self.profile)
        stats.sort_stats('time', 'cumulative').print_stats(40)
        assert response.status_code == 200

    def test_loading_single(self):
        start_time = time.time()
        response = self.test_client.get('/api/people/1')
        processing_time = time.time() - start_time
        print('Fetch time:', processing_time)
        assert response.status_code == 200
