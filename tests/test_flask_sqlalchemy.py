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

        self.Person = Person
        self.db.create_all()
        self.manager = APIManager(self.flaskapp, session=self.db.session)
        self.manager.create_api(self.Person, methods=['POST', 'DELETE'])

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
