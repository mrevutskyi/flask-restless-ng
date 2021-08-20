from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Unicode
from sqlalchemy.ext.declarative import declarative_base
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
    name = Column(Unicode)
    age = Column(Integer)
    other = Column(Float)
    articles = relationship('Article', backref='author')
    comments = relationship('Comment', backref='author')


class Parent(Base):
    __tablename__ = 'parent'
    id = Column(Integer, primary_key=True)
    children = relationship('Child', primaryjoin='and_(Parent.id==Child.parent_id,Child.invisible==0)')


class Child(Base):
    __tablename__ = 'child'
    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey('parent.id'))
    invisible = Column(Boolean)
