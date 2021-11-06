# test_server_responsibilities.py - tests JSON API server responsibilities
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
"""Tests that Flask-Restless handles the responsibilities of a server
according to the JSON API specification.

The tests in this module correspond to the `Server Responsibilities`_
section of the JSON API specification.

.. _Server Responsibilities: https://jsonapi.org/format/#content-negotiation-servers

"""
import json

import pytest

from flask_restless import CONTENT_TYPE
from flask_restless import APIManager

from ..conftest import BaseTestClass
from .models import Base
from .models import Person


class TestServerResponsibilities(BaseTestClass):
    """Tests corresponding to the `Inclusion of Related Resources`_section of the JSON API specification.

    .. _Inclusion of Related Resources: https://jsonapi.org/format/#fetching-includes

    """

    @pytest.fixture(autouse=True)
    def setup(self):
        manager = APIManager(self.app, session=self.session)
        manager.create_api(Person, methods=['GET', 'POST', 'PATCH', 'DELETE'])
        Base.metadata.create_all(bind=self.engine)
        yield
        Base.metadata.drop_all(bind=self.engine)

    def test_get_content_type(self):
        """"Tests that a response to a :https:method:`get` request has
        the correct content type.

        For more information, see the `Server Responsibilities`_ section
        of the JSON API specification.

        .. _Server Responsibilities: https://jsonapi.org/format/#content-negotiation-servers

        """
        response = self.client.get('/api/person')
        assert response.mimetype == CONTENT_TYPE

    def test_post_content_type(self):
        """"Tests that a response to a :https:method:`post` request has
        the correct content type.

        Our implementation of the JSON API specification always responds
        to a :https:method:`post` request with a representation of the
        created resource.

        For more information, see the `Server Responsibilities`_ section
        of the JSON API specification.

        .. _Server Responsibilities: https://jsonapi.org/format/#content-negotiation-servers

        """
        data = {'data': {'type': 'person'}}
        response = self.client.post('/api/person', json=data)
        assert response.mimetype == CONTENT_TYPE

    def test_no_content_type(self):
        """Tests that the server responds with :http:status:`415` if the
        request has no content type.

        """
        data = dict(data=dict(type='person'))
        response = self.client.post('/api/person', json=data, content_type=None)
        assert response.status_code == 415
        assert response.headers['Content-Type'] == CONTENT_TYPE
        assert response.json['errors'][0]['detail'] == 'Request must have "Content-Type: application/vnd.api+json" header'

    def test_no_response_media_type_params(self):
        """"Tests that a server responds with :https:status:`415` if any
        media type parameters appear in the request content type header.

        For more information, see the `Server Responsibilities`_ section
        of the JSON API specification.

        .. _Server Responsibilities: https://jsonapi.org/format/#content-negotiation-servers

        """
        headers = {'Content-Type': f'{CONTENT_TYPE}; version=1'}
        # flask 1.0.1 overrides headers when `json` parameter is used, so have to use json.dumps
        self.post_and_validate('/api/person', data=json.dumps({}), headers=headers, expected_response_code=415,
                               error_msg='header must not have any media type parameters')

    def test_wrong_content_type(self):
        """Tests that if a client specifies only
        :http:header:`Content-Type` headers with non-JSON API media
        types, then the server responds with a :http:status:`415`.

        """
        headers = {'Content-Type': 'application/json'}
        data = {
            'data': {
                'type': 'person'
            }
        }
        self.post_and_validate('/api/person', json=data, headers=headers, expected_response_code=415, error_msg='application/vnd.api+json')

    def test_empty_accept_header(self):
        """Tests that an empty :https:header:`Accept` header, which is
        technically legal according to :rfc:`2616#sec14.1`, is allowed,
        since it is not explicitly forbidden by JSON API.

        For more information, see the `Server Responsibilities`_ section
        of the JSON API specification.

        .. _Server Responsibilities: https://jsonapi.org/format/#content-negotiation-servers

        """
        headers = {'Accept': ''}
        document = self.fetch_and_validate('/api/person', headers=headers)
        assert len(document['data']) == 0

    def test_valid_accept_header(self):
        """Tests that we handle requests with an :https:header:`Accept`
        header specifying the JSON API mimetype are handled normally.

        For more information, see the `Server Responsibilities`_ section
        of the JSON API specification.

        .. _Server Responsibilities: https://jsonapi.org/format/#content-negotiation-servers

        """
        headers = {'Accept': CONTENT_TYPE}
        document = self.fetch_and_validate('/api/person', headers=headers)
        assert len(document['data']) == 0

    def test_no_accept_media_type_params(self):
        """"Tests that a server responds with :https:status:`406` if each
        :https:header:`Accept` header is the JSON API media type, but
        each instance of that media type has a media type parameter.

        For more information, see the `Server Responsibilities`_ section
        of the JSON API specification.

        .. _Server Responsibilities: https://jsonapi.org/format/#content-negotiation-servers

        """
        headers = {'Accept': f'{CONTENT_TYPE}; q=.8, {CONTENT_TYPE}; q=.9'}
        self.fetch_and_validate('/api/person', headers=headers, expected_response_code=406, error_msg='media type parameter')

    def test_wrong_accept_header(self):
        """Tests that if a client specifies only :http:header:`Accept`
        headers with non-JSON API media types, then the server responds
        with a :http:status:`406`.

        """
        headers = {'Accept': 'application/json'}
        self.post_and_validate('/api/person', json={}, headers=headers, expected_response_code=406,
                               error_msg='Accept header, if specified, must be the JSON API media type: application/vnd.api+json')
