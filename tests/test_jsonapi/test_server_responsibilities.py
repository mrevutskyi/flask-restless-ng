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
from ..helpers import check_sole_error
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

    def test_no_response_media_type_params(self):
        """"Tests that a server responds with :https:status:`415` if any
        media type parameters appear in the request content type header.

        For more information, see the `Server Responsibilities`_ section
        of the JSON API specification.

        .. _Server Responsibilities: https://jsonapi.org/format/#content-negotiation-servers

        """
        headers = {'Content-Type': f'{CONTENT_TYPE}; version=1'}
        # flask 1.0.1 overrides headers when `json` parameter is used, so have to use json.dumps
        response = self.client.post('/api/person', data=json.dumps({}), headers=headers)
        check_sole_error(response, 415, ['Content-Type', 'media type parameters'])

    def test_empty_accept_header(self):
        """Tests that an empty :https:header:`Accept` header, which is
        technically legal according to :rfc:`2616#sec14.1`, is allowed,
        since it is not explicitly forbidden by JSON API.

        For more information, see the `Server Responsibilities`_ section
        of the JSON API specification.

        .. _Server Responsibilities: https://jsonapi.org/format/#content-negotiation-servers

        """
        headers = {'Accept': ''}
        response = self.client.get('/api/person', headers=headers)
        assert response.status_code == 200
        document = response.json
        assert len(document['data']) == 0

    def test_valid_accept_header(self):
        """Tests that we handle requests with an :https:header:`Accept`
        header specifying the JSON API mimetype are handled normally.

        For more information, see the `Server Responsibilities`_ section
        of the JSON API specification.

        .. _Server Responsibilities: https://jsonapi.org/format/#content-negotiation-servers

        """
        headers = {'Accept': CONTENT_TYPE}
        response = self.client.get('/api/person', headers=headers)
        assert response.status_code == 200
        document = response.json
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
        response = self.client.get('/api/person', headers=headers)
        check_sole_error(response, 406, ['Accept', 'media type parameter'])
