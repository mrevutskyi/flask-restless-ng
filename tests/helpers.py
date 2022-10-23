# helpers.py - helper functions for unit tests
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
"""Helper functions for unit tests."""
import json
import unittest
import uuid
from datetime import date
from datetime import datetime
from datetime import time
from datetime import timedelta
from functools import wraps
from json import JSONEncoder

import jsonschema
from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy import event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.session import Session as SessionBase
from sqlalchemy.types import CHAR
from sqlalchemy.types import TypeDecorator

try:
    # SQLAlchemy 1.4+
    from sqlalchemy.orm import DeclarativeMeta
except ImportError:
    from sqlalchemy.ext.declarative.api import DeclarativeMeta  # type: ignore # noqa


from flask_restless import CONTENT_TYPE
from flask_restless import APIManager

try:
    import flask_sqlalchemy
    from flask_sqlalchemy import SQLAlchemy
except ImportError:
    has_flask_sqlalchemy = False
else:
    has_flask_sqlalchemy = True


dumps = json.dumps

with open('tests/jsonapi-schema.json', 'r') as f:
    json_api_schema = json.load(f)


def validate_schema(data: dict):
    jsonschema.validate(data, schema=json_api_schema)


def isclass(obj):
    """Returns ``True`` if and only if the specified object is a type (or a
    class).

    """
    return isinstance(obj, type)


def parse_version(version_string):
    """Parses the Flask-SQLAlchemy version string into a pair of
    integers.

    """
    # First, check for '-dev' suffix.
    split_on_hyphen = version_string.split('-')
    version_string = split_on_hyphen[0]
    return tuple(int(n) for n in version_string.split('.'))


def unregister_fsa_session_signals():
    """Unregisters Flask-SQLAlchemy session commit and rollback signal
    handlers.

    When a Flask-SQLAlchemy object is created, it registers signal handlers for
    ``before_commit``, ``after_commit``, and ``after_rollback`` signals. In
    case of using both a plain SQLAlchemy session and a Flask-SQLAlchemy
    session (as is happening in the tests in this package), we need to
    unregister handlers or there will be some exceptions during test
    executions like::

        AttributeError: 'Session' object has no attribute '_model_changes'

    """
    # We don't need to do this if Flask-SQLAlchemy is not installed.
    if not has_flask_sqlalchemy:
        return
    # We don't need to do this if Flask-SQLAlchemy version 2.0 or
    # greater is installed.
    version = parse_version(flask_sqlalchemy.__version__)
    if version >= (2, 0):
        return
    events = flask_sqlalchemy._SessionSignalEvents
    signal_names = ('before_commit', 'after_commit', 'after_rollback')
    for signal_name in signal_names:
        # For Flask-SQLAlchemy version less than 3.0.
        signal = getattr(events, 'session_signal_{0}'.format(signal_name))
        event.remove(SessionBase, signal_name, signal)


def check_sole_error(response, status, strings):
    """Asserts that the response is an errors response with a single
    error object whose detail message contains all of the given strings.

    `strings` may also be a single string object to check.

    `status` is the expected status code for the sole error object in
    the response.

    """
    if isinstance(strings, str):
        strings = [strings]
    assert response.status_code == status
    document = response.json
    errors = document['errors']
    assert len(errors) == 1
    error = errors[0]
    assert error['status'] == str(status)
    assert all(s in error['detail'] for s in strings)


def force_content_type_jsonapi(test_client):
    """Ensures that all requests made by the specified Flask test client
    that include data have the correct :http:header:`Content-Type`
    header.

    """

    def set_content_type(func):
        """Returns a decorated version of ``func``, as described in the
        wrapper defined below.

        """

        @wraps(func)
        def new_func(*args, **kw):
            """Sets the correct :http:header:`Content-Type` headers
            before executing ``func(*args, **kw)``.

            """
            headers = kw.get('headers') or {}
            kw['headers'] = headers
            if 'content_type' not in kw and 'Content-Type' not in headers:
                kw['content_type'] = CONTENT_TYPE
            return func(*args, **kw)
        return new_func

    # Decorate the appropriate test client request methods.
    test_client.patch = set_content_type(test_client.patch)
    test_client.post = set_content_type(test_client.post)


# This code is adapted from
# https://docs.sqlalchemy.org/en/latest/core/custom_types.html#backend-agnostic-guid-type
class GUID(TypeDecorator):
    """Platform-independent GUID type.

    Uses Postgresql's UUID type, otherwise uses CHAR(32), storing as
    stringified hex values.

    """
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        descriptor = UUID() if dialect.name == 'postgresql' else CHAR(32)
        return dialect.type_descriptor(descriptor)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == 'postgresql':
            return str(value)
        if not isinstance(value, uuid.UUID):
            return uuid.UUID(value).hex
        # If we get to this point, we assume `value` is a UUID object.
        return value.hex

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return uuid.UUID(value)


# In versions of Flask before 1.0, datetime and time objects are not
# serializable by default so we need to create a custom JSON encoder class.
#
# TODO When Flask 1.0 is required, remove this.
class BetterJSONEncoder(JSONEncoder):
    """Extends the default JSON encoder to serialize objects from the
    :mod:`datetime` module.

    """

    def default(self, obj):
        if isinstance(obj, (date, datetime, time)):
            return obj.isoformat()
        if isinstance(obj, timedelta):
            return int(obj.days * 86400 + obj.seconds)
        return super(BetterJSONEncoder, self).default(obj)


class FlaskTestBase(unittest.TestCase):
    """Base class for tests which use a Flask application.

    The Flask test client can be accessed at ``self.app``. The Flask
    application itself is accessible at ``self.flaskapp``.

    """

    def setUp(self):
        """Creates the Flask application and the APIManager."""
        # create the Flask application
        app = Flask(__name__)
        app.config['DEBUG'] = True
        app.config['TESTING'] = True
        # This is required by `manager.url_for()` in order to construct
        # absolute URLs.
        app.config['SERVER_NAME'] = 'localhost'
        app.logger.disabled = True
        self.flaskapp = app

        # create the test client
        self.app = app.test_client()

        force_content_type_jsonapi(self.app)


class DatabaseMixin(object):
    """A class that accesses a database via a connection URI.

    Subclasses can override the :meth:`database_uri` method to return a
    connection URI for the desired database backend.

    """

    def database_uri(self):
        """The database connection URI to use for the SQLAlchemy engine.

        By default, this returns the URI for the SQLite in-memory
        database. Subclasses that wish to use a different SQL backend
        should override this method so that it returns the desired URI
        string.

        """
        return 'sqlite://'


class FlaskSQLAlchemyTestBase(FlaskTestBase, DatabaseMixin):
    """Base class for tests that use Flask-SQLAlchemy (instead of plain
    old SQLAlchemy).

    If Flask-SQLAlchemy is not installed, the :meth:`.setUp` method will
    raise :exc:`nose.SkipTest`, so that each test method will be
    skipped individually.

    """

    def setUp(self):
        super().setUp()
        if not has_flask_sqlalchemy:
            self.skipTest('Flask-SQLAlchemy not found.')
        self.flaskapp.config['SQLALCHEMY_DATABASE_URI'] = self.database_uri()
        # This is to avoid a warning in earlier versions of
        # Flask-SQLAlchemy.
        self.flaskapp.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        # Store some attributes for convenience and so the test methods
        # read more like the tests for plain old SQLAlchemy.
        self.db = SQLAlchemy(self.flaskapp)
        self.session = self.db.session
        self.client = self.flaskapp.test_client()

        # 'Flask-SQLAlchemy > 3.0 requires app context for everything
        self.app_context = self.flaskapp.app_context()
        self.app_context.push()

    def tearDown(self):
        """Drops all tables and unregisters Flask-SQLAlchemy session
        signals.

        """
        self.db.drop_all()
        self.app_context.pop()
        unregister_fsa_session_signals()


class SQLAlchemyTestBase(FlaskTestBase, DatabaseMixin):
    """Base class for tests that use a SQLAlchemy database.

    The :meth:`setUp` method does the necessary SQLAlchemy
    initialization, and the subclasses should populate the database with
    models and then create the database (by calling
    ``self.Base.metadata.create_all()``).

    By default, this class creates a SQLite database; subclasses can
    override the :meth:`.database_uri` method to enable configuration of
    an alternate database backend.

    """

    def setUp(self):
        """Initializes the components necessary for models in a SQLAlchemy
        database.

        """
        super().setUp()
        engine = create_engine(self.database_uri())
        self.Session = sessionmaker(autocommit=False, autoflush=False,
                                    bind=engine)
        self.session = scoped_session(self.Session)
        self.Base = declarative_base()
        self.Base.metadata.bind = engine

    def tearDown(self):
        """Drops all tables from the temporary database."""
        self.session.remove()
        self.Base.metadata.drop_all()


class ManagerTestBase(SQLAlchemyTestBase):
    """Base class for tests that use a SQLAlchemy database and an
    :class:`~flask_restless.APIManager`.

    Nearly all test classes should subclass this class. Since we strive
    to make Flask-Restless compliant with plain old SQLAlchemy first,
    the default database abstraction layer used by tests in this class
    will be SQLAlchemy. Test classes requiring Flask-SQLAlchemy must
    instantiate their own :class:`~flask_restless.APIManager`.

    The :class:`~flask_restless.APIManager` instance for use in
    tests is accessible at ``self.manager``.

    """

    def setUp(self):
        """Initializes an instance of
        :class:`~flask_restless.APIManager` with a SQLAlchemy
        session.

        """
        super().setUp()
        self.manager = APIManager(self.flaskapp, session=self.session)

    def tearDown(self):
        super().tearDown()
