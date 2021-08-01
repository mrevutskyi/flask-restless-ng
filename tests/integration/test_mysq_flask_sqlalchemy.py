import pytest
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

from flask_restless import APIManager

app = Flask(__name__)
app.testing = True
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://db_user:password@localhost/flask_restless'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

starred_orders = db.Table(
    'starred_orders',
    db.Column('client_id', db.Integer, db.ForeignKey('client.id')),
    db.Column('order_id', db.Integer, db.ForeignKey('order.id')),
)


class Client(db.Model):
    __tablename__ = 'client'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64))

    orders = db.relationship('Order', backref=db.backref('client'), primaryjoin='and_(Client.id==Order.client_id, Order.archived==0)')
    starred_orders = db.relationship("Order",
                                     secondary='starred_orders',
                                     primaryjoin='and_(Client.id==starred_orders.c.client_id, Order.archived==0)')


class Order(db.Model):
    __tablename__ = 'order'

    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(64))
    archived = db.Column(db.Boolean(), default=False)

    client_id = db.Column(db.Integer, db.ForeignKey('client.id'))


@pytest.fixture(scope='module')
def api():

    with app.app_context():
        api_manager = APIManager(app=app, session=db.session, url_prefix='', include_links=False)
        api_manager.create_api(Client, collection_name='clients', page_size=0)
        api_manager.create_api(Order, collection_name='orders', page_size=0)

        db.drop_all()
        db.create_all()

        client = Client(id=1, name='Client')
        client.starred_orders.append(Order(id=1, client_id=1))
        db.session.add(client)
        db.session.commit()
        db.session.bulk_save_objects([Order(id=i, client_id=1) for i in range(2, 6)])
        db.session.bulk_save_objects([Order(id=i, client_id=1, archived=True) for i in range(6, 11)])
        db.session.commit()

        yield app.test_client()


@pytest.mark.integration
def test_responses(api):
    response = api.get('/clients/1?include=orders,starred_orders')
    assert response.status_code == 200
    document = response.json
    assert len(document['included']) == 5
