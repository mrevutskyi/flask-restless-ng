from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm import sessionmaker

from .helpers import force_content_type_jsonapi
from .helpers import validate_schema


def pytest_configure(config):
    # do not run integration tests by default
    if not config.option.markexpr:
        setattr(config.option, 'markexpr', 'not integration')


class BaseTestClass:
    """Base test class that contains required fixtures."""

    app = None
    client = None  # type: FlaskClient
    session = None
    engine = None

    @classmethod
    def setup_class(cls):
        cls.engine = create_engine('sqlite://')
        cls.scoped_session_cls = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=cls.engine))

    def setup_method(self):
        app = Flask(__name__)
        app.config['TESTING'] = True
        self.app = app
        self.client = app.test_client()
        force_content_type_jsonapi(self.client)
        self.session = self.scoped_session_cls()

    def teardown_method(self):
        self.session.close()

    def fetch_and_validate(self, uri: str, expected_response_code: int = 200):
        response = self.client.get(uri)
        assert response.status_code == expected_response_code
        document = response.json
        validate_schema(document)

        return document
