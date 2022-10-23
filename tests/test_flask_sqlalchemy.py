from flask_restless import APIManager

from .helpers import FlaskSQLAlchemyTestBase


class TestFlaskSQLAlchemy(FlaskSQLAlchemyTestBase):
    """
    Tests for resources defined as Flask-SQLAlchemy models instead of pure SQLAlchemy models.
    """

    def setUp(self):
        """Creates the Flask-SQLAlchemy database and models."""
        super(TestFlaskSQLAlchemy, self).setUp()

        class Person(self.db.Model):
            id = self.db.Column(self.db.Integer, primary_key=True)
            team_id = self.db.Column(self.db.Integer, self.db.ForeignKey('team.id'))

        class Team(self.db.Model):
            id = self.db.Column(self.db.Integer, primary_key=True)

            members = self.db.relationship('Person')

        self.Person = Person
        self.Team = Team
        self.db.create_all()
        self.manager = APIManager(self.flaskapp, session=self.db.session)
        self.manager.create_api(self.Person, methods=['GET', 'POST', 'DELETE'])
        self.manager.create_api(self.Team, methods=['GET'])

    def test_create(self):
        """Tests for creating a resource."""
        data = dict(data=dict(type='person'))
        response = self.app.post('/api/person', json=data)
        assert response.status_code == 201
        document = response.json
        person = document['data']
        # TODO: To make this test more robust, should query for person objects.
        assert person['id'] == '1'
        assert person['type'] == 'person'

    def test_delete(self):
        """Tests for deleting a resource."""
        self.session.add(self.Person(id=1))
        self.session.commit()
        response = self.app.delete('/api/person/1')
        assert response.status_code == 204
        assert self.Person.query.count() == 0

    def test_get_many(self):
        """Tests pagination in Flask-SQLAlchemy"""
        self.session.add(self.Team(id=1))
        self.session.bulk_save_objects([
            self.Person(id=i, team_id=1) for i in range(50)
        ])
        self.session.commit()
        response = self.app.get('/api/team/1/members')
        assert response.status_code == 200
