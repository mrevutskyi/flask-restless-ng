import datetime
import enum
import json

import pytest
from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import Enum
from sqlalchemy import Float
from sqlalchemy import Integer
from sqlalchemy import Interval
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import Time
from sqlalchemy import Unicode

from flask_restless.serialization import DefaultSerializer

from .helpers import DeclarativeMeta
from .helpers import declarative_base

Base: DeclarativeMeta = declarative_base()  # type: ignore

TEST_TEXT_PARAGRAPH = """
“Twenty years from now you will be more disappointed by the things that you didn't do than by the ones you did do. So throw off the bowlines.
Sail away from the safe harbor. Catch the trade winds in your sails. Explore. Dream. Discover.”

― H. Jackson Brown Jr., P.S. I Love You
"""


class MyEnum(enum.Enum):
    one = 1
    two = 2
    three = 3


class Model(Base):
    __tablename__ = 'article'
    id = Column(Integer, primary_key=True)
    string_field = Column(String(32))
    unicode_field = Column(Unicode(32))
    text_field = Column(Text())
    int_field = Column(Integer())
    float_field = Column(Float())
    bool_field = Column(Boolean())
    date_field = Column(Date())
    datetime_field = Column(DateTime())
    interval_field = Column(Interval())
    time_field = Column(Time())
    enum_field = Column(Enum(MyEnum))


def test_serialize_attributes():
    serializer = DefaultSerializer(Model, 'test-model', None, primary_key='id')
    instance = Model(
        id=1,
        string_field='string value',
        unicode_field='Ѧ',
        text_field=TEST_TEXT_PARAGRAPH,
        int_field=123,
        float_field=1.0,
        bool_field=True,
        date_field=datetime.date(2021, 1, 1),
        datetime_field=datetime.datetime(year=2021, month=1, day=1, hour=12, minute=0, second=0),
        time_field=datetime.time(12, 0, 0),
        interval_field=datetime.timedelta(minutes=1),
        enum_field=MyEnum.two
    )

    serialized = serializer.serialize_attributes(instance)
    # Make sure that the result is JSON serializable, and that deserializing back from JSON produces the same dictionary
    serialized_json = json.dumps(serialized, indent=2)
    assert serialized == json.loads(serialized_json)
    assert serialized == {
        'string_field': 'string value',
        'unicode_field': 'Ѧ',
        'text_field': TEST_TEXT_PARAGRAPH,
        'int_field': 123,
        'float_field': 1.0,
        'bool_field': True,
        'date_field': '2021-01-01',
        'datetime_field': '2021-01-01T12:00:00',
        'time_field': '12:00:00',
        'interval_field': 60.0,
        'enum_field': 'two'
    }


def test_raises_value_error_for_empty_pk():
    with pytest.raises(ValueError):
        DefaultSerializer(Model, 'test-model', None)


def test_raises_value_error_when_provided_pk_is_not_pk():
    with pytest.raises(ValueError):
        DefaultSerializer(Model, 'test-model', None, primary_key='date_field')


def test_skip_pk_test():
    assert DefaultSerializer(Model, 'test-model', None, primary_key='date_field', allow_non_primary_key_id=True)
