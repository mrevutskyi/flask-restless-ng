from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm import sessionmaker

from .helpers import validate_schema


class BaseTestClass:
    """Tests corresponding to the `Fetching Data`_ section of the JSON API specification.

    .. _Fetching Data: https://jsonapi.org/format/#fetching

    """

    @classmethod
    def setup_class(cls):
        cls.engine = create_engine('sqlite://')
        scoped_session_cls = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=cls.engine))
        cls.session = scoped_session_cls()

    def setup_method(self):
        app = Flask(__name__)
        app.config['TESTING'] = True
        self.app = app
        self.client = app.test_client()

    def fetch_and_validate(self, uri: str, expected_response_code: int = 200):
        response = self.client.get(uri)
        assert response.status_code == expected_response_code
        document = response.json
        validate_schema(document)

        return document
