from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Interval
from sqlalchemy import Time
from sqlalchemy import Unicode
from sqlalchemy import func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship

from ..helpers import DeclarativeMeta

Base: DeclarativeMeta = declarative_base()  # type: ignore


class Article(Base):
    __tablename__ = 'article'
    id = Column(Integer, primary_key=True)
    title = Column(Unicode)
    author_id = Column(Integer, ForeignKey('person.pk'))
    comments = relationship('Comment', backref='article')


class Comment(Base):
    __tablename__ = 'comment'
    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey('article.id'))
    author_id = Column(Integer, ForeignKey('person.pk'))


class Person(Base):
    __tablename__ = 'person'
    pk = Column(Integer, primary_key=True)  # non-standard name for primary key
    name = Column(Unicode, unique=True)
    age = Column(Integer)
    other = Column(Float)
    articles = relationship('Article', backref='author')
    comments = relationship('Comment', backref='author')


class Tag(Base):
    __tablename__ = 'tag'
    id = Column(Integer, primary_key=True)
    name = Column(Unicode)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.current_timestamp())


class Parent(Base):
    __tablename__ = 'parent'
    id = Column(Integer, primary_key=True)
    children = relationship('Child', primaryjoin='and_(Parent.id==Child.parent_id,Child.invisible==0)')


class Child(Base):
    __tablename__ = 'child'
    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey('parent.id'))
    invisible = Column(Boolean)


class Various(Base):
    """A test model that contains fields of various types, for testing serialization/deserialization"""
    __tablename__ = 'various'
    id = Column(Integer, primary_key=True)
    age = Column(Integer)
    date = Column(Date)
    datetime = Column(DateTime)
    time = Column(Time)
    interval = Column(Interval)

    @hybrid_property
    def is_minor(self):
        if hasattr(self, 'age'):
            if self.age is None:
                return None
            return self.age < 18
        return None


class UnicodePK(Base):
    """Model with a primary key that has Unicode type. """
    __tablename__ = 'unicode_pk'
    name = Column(Unicode, primary_key=True)
