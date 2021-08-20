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

from ..conftest import BaseTestClass
from .models import Base
from .models import Person


class TestDeletingResources(BaseTestClass):
    """Tests corresponding to the `Deleting Resources`_ section of the JSON API
    specification.

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
