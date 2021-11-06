import http
from typing import Any
from typing import Dict
from typing import Optional

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

    @staticmethod
    def _decode_and_validate(response, expected_response_code, error_msg=None):
        assert response.status_code == expected_response_code
        if expected_response_code == http.HTTPStatus.NO_CONTENT:
            return
        document = response.json
        validate_schema(document)
        if error_msg:
            assert error_msg in document['errors'][0]['detail']

        return document

    def fetch_and_validate(
            self,
            uri: str,
            expected_response_code: int = 200,
            query_string: Optional[Dict[str, Any]] = None,
            error_msg: Optional[str] = None,
            headers: Optional[Dict[str, Any]] = None
    ):
        response = self.client.get(uri, query_string=query_string, headers=headers)
        return self._decode_and_validate(response, expected_response_code, error_msg=error_msg)

    def post_and_validate(
            self,
            uri: str,
            expected_response_code: int = 201,
            error_msg: Optional[str] = None,
            **kwargs
    ):
        response = self.client.post(uri, **kwargs)
        return self._decode_and_validate(response, expected_response_code, error_msg=error_msg)

    def patch_and_validate(
            self,
            uri: str,
            json: Dict[str, Any],
            expected_response_code: int = 204,
            error_msg: Optional[str] = None
    ):
        response = self.client.patch(uri, json=json)
        return self._decode_and_validate(response, expected_response_code, error_msg=error_msg)
