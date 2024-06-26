# test_metadata.py - unit tests for response metadata
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
"""Unit tests for metadata in server responses."""
from sqlalchemy import Column
from sqlalchemy import Integer

from .helpers import ManagerTestBase


class TestMetadata(ManagerTestBase):
    """Tests for receiving metadata in responses."""

    def setUp(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application, and
        creates the ReSTful API endpoints for the :class:`TestSupport.Person`.

        """
        super(TestMetadata, self).setUp()

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)

        self.Person = Person
        self.Base.metadata.create_all(bind=self.engine)
        self.manager.create_api(Person)

    def test_total(self):
        """Tests that a request for (a subset of) all instances of a model
        includes the total number of results as part of the JSON response.

        """
        people = [self.Person() for _ in range(15)]
        self.session.add_all(people)
        self.session.commit()
        response = self.app.get('/api/person')
        document = response.json
        assert document['meta']['total'] == 15
