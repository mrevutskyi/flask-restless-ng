from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Interval
from sqlalchemy import String
from sqlalchemy import Time
from sqlalchemy import Unicode
from sqlalchemy import func
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Query
from sqlalchemy.orm import backref
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import relationship

from ..helpers import DeclarativeMeta

Base: DeclarativeMeta = declarative_base()  # type: ignore


class Article(Base):
    __tablename__ = 'article'
    id = Column(Integer, primary_key=True)
    title = Column(Unicode)
    author_id = Column(Integer, ForeignKey('person.pk'))
    comments = relationship('Comment', backref='article', cascade_backrefs=False)


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
    articles = relationship('Article', backref='author', cascade_backrefs=False)
    comments = relationship('Comment', backref='author', cascade_backrefs=False)


class Tag(Base):
    __tablename__ = 'tag'
    id = Column(Integer, primary_key=True)
    name = Column(Unicode)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.current_timestamp())


class Post(Base):
    __tablename__ = 'post'
    id = Column(Integer, primary_key=True)
    title = Column(String(64))
    tags = association_proxy("posttags", "tag", creator=lambda tag: PostTag(tag=tag))


class PostTag(Base):
    __tablename__ = 'posttag'
    # id = Column(Integer)
    post_id = Column(Integer, ForeignKey('post.id'), primary_key=True)
    tag_id = Column(Integer, ForeignKey('tag.id'), primary_key=True)
    tag = relationship(Tag, cascade_backrefs=False)
    post = relationship(Post, backref=backref('posttags'), cascade_backrefs=False)


class Parent(Base):
    __tablename__ = 'parent'
    id = Column(Integer, primary_key=True)
    children = relationship('Child', primaryjoin='and_(Parent.id==Child.parent_id,Child.invisible==0)', cascade_backrefs=False)


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

    @classmethod
    def query(cls):
        return Query(cls).filter(cls.id < 2)


class UnicodePK(Base):
    """Model with a primary key that has Unicode type. """
    __tablename__ = 'unicode_pk'
    name = Column(Unicode, primary_key=True)


class Unsorted(Base):
    """Model that should not have a primary_key to dest disabled sorting.

    SQLAlchemy does not actually let us define a model without a primary key,
    so the table has to be created without the PK manually before create_all()
    """
    __tablename__ = 'unsorted'
    id = Column(Integer, primary_key=True)
