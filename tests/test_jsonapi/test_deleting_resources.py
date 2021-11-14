# test_deleting_resources.py - tests deleting resources according to JSON API
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
"""Unit tests for requests that delete resources.

The tests in this module correspond to the `Deleting Resources`_ section
of the JSON API specification.

.. _Deleting Resources: https://jsonapi.org/format/#crud-deleting

"""
import pytest

from flask_restless import APIManager
from flask_restless import ProcessingException

from ..conftest import BaseTestClass
from .models import Base
from .models import Person


class TestDeletingResources(BaseTestClass):
    """Tests corresponding to the `Deleting Resources`_ section of the JSON API specification.

    .. _Deleting Resources: https://jsonapi.org/format/#crud-deleting

    """

    @pytest.fixture(autouse=True)
    def setup(self):
        manager = APIManager(self.app, session=self.session)
        manager.create_api(Person, ['DELETE'])
        Base.metadata.create_all(bind=self.engine)
        yield
        Base.metadata.drop_all(bind=self.engine)

    def test_delete(self):
        """Tests for deleting a resource.

        For more information, see the `Deleting Resources`_ section of the JSON
        API specification.

        .. _Deleting Resources: https://jsonapi.org/format/#crud-deleting

        """
        self.session.add(Person(pk=1))
        self.session.commit()
        response = self.client.delete('/api/person/1')
        assert response.status_code == 204
        assert self.session.query(Person).count() == 0

    def test_delete_nonexistent(self):
        """Tests that deleting a nonexistent resource causes a
        :https:status:`404`.

        For more information, see the `404 Not Found`_ section of the JSON API
        specification.

        .. _404 Not Found: https://jsonapi.org/format/#crud-deleting-responses-404

        """
        response = self.client.delete('/api/person/1')
        assert response.status_code == 404

    def test_wrong_accept_header(self):
        """Tests that if a client specifies only :http:header:`Accept`
        headers with non-JSON API media types, then the server responds
        with a :http:status:`406`.

        """
        self.session.add(Person(pk=1))
        self.session.commit()
        headers = {'Accept': 'application/json'}
        response = self.client.delete('/api/person/1', headers=headers)
        assert response.status_code == 406
        assert self.session.query(Person).get(1) is not None

    def test_related_resource_url_forbidden(self):
        """Tests that :http:method:`delete` requests to a related resource URL are forbidden."""
        response = self.client.delete('/api/person/1/articles')
        assert response.status_code == 405

    def test_disallow_delete_many(self):
        """Tests that deleting an entire collection is disallowed by default.

        Deleting an entire collection is not discussed in the JSON API
        specification.

        """
        response = self.client.delete('/api/person')
        assert response.status_code == 405


class TestProcessors(BaseTestClass):
    """Tests for pre- and postprocessors."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.manager = APIManager(self.app, session=self.session)
        Base.metadata.create_all(bind=self.engine)
        self.session.add(Person(pk=1))
        self.session.commit()
        yield
        Base.metadata.drop_all(bind=self.engine)

    def test_resource(self):
        """Tests for running a preprocessor on a request to delete a single resource."""
        data = {'triggered': False}

        def update_data(*_, **__):
            data['triggered'] = True

        self.manager.create_api(Person, methods=['DELETE'], preprocessors=dict(DELETE_RESOURCE=[update_data]))
        self.client.delete('/api/person/1')
        assert data['triggered'] is True
        assert self.session.query(Person).count() == 0

    def test_change_id(self):
        """Tests that a return value from a preprocessor overrides the ID of the resource to fetch as given in the request URL."""
        def increment_id(resource_id=None, **__):
            if resource_id is None:
                raise ProcessingException
            return int(resource_id) + 1

        self.manager.create_api(Person, methods=['DELETE'], preprocessors=dict(DELETE_RESOURCE=[increment_id]))
        response = self.client.delete('/api/person/0')
        assert response.status_code == 204
        assert self.session.query(Person).count() == 0

    def test_processing_exception(self):
        """Tests for a preprocessor that raises a :exc:`ProcessingException` when deleting a single resource."""
        def forbidden(**__):
            raise ProcessingException(status=403, detail='forbidden')

        self.manager.create_api(Person, methods=['DELETE'], preprocessors=dict(DELETE_RESOURCE=[forbidden]))
        response = self.client.delete('/api/person/1')
        document = self.parse_and_validate_response(response, expected_response_code=403, error_msg='forbidden')
        assert len(document['errors']) == 1
        assert self.session.query(Person).get(1) is not None

    def test_postprocessor(self):
        """Tests that a postprocessor is invoked when deleting a resource."""

        def assert_deletion(was_deleted=False, **__):
            assert was_deleted

        self.manager.create_api(Person, methods=['DELETE'], postprocessors=dict(DELETE_RESOURCE=[assert_deletion]))
        response = self.client.delete('/api/person/1')
        assert response.status_code == 204
