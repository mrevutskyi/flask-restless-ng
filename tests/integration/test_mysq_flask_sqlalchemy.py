import pytest
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

from flask_restless import APIManager

pytestmark = pytest.mark.integration

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


# Models for Many-to-Many test case

class Sheet(db.Model):
    __tablename__ = "sheet"

    id = db.Column(db.Integer, primary_key=True)

    report = db.relationship(
        "Report",
        cascade="all, delete",
        passive_deletes=True,
        single_parent=True,
        secondary="join(Report, Device, Report.device_id == Device.id)",
        order_by="Device.parent_device_id",
    )


class Report(db.Model):
    __tablename__ = "report"

    id = db.Column(db.Integer, primary_key=True)

    device_id = db.Column(db.Integer, db.ForeignKey("device.id", ondelete="CASCADE"), nullable=False)
    sheet_id = db.Column(db.Integer, db.ForeignKey("sheet.id", ondelete="CASCADE"), nullable=False)


class Device(db.Model):
    __tablename__ = "device"

    id = db.Column(db.Integer, primary_key=True)
    parent_device_id = db.Column(db.Integer, db.ForeignKey("device.id", ondelete="CASCADE"), nullable=True)


@pytest.fixture(scope='module')
def api():

    with app.app_context():
        api_manager = APIManager(app=app, session=db.session, url_prefix='', include_links=False)
        api_manager.create_api(Client, collection_name='clients', page_size=0)
        api_manager.create_api(Order, collection_name='orders', page_size=0)

        api_manager.create_api(Report, collection_name='reports', page_size=0)
        api_manager.create_api(Device, collection_name='devices', page_size=0)
        api_manager.create_api(Sheet, collection_name='sheets', page_size=0)

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


def test_responses(api):
    response = api.get('/clients/1?include=orders,starred_orders')
    assert response.status_code == 200
    document = response.json
    assert len(document['included']) == 5


def test_selectin_for_many_to_many(api):
    """
    Test case to catch https://github.com/mrevutskyi/flask-restless-ng/issues/27
    """
    db.session.add_all([
        Device(id=1),
        Device(id=2, parent_device_id=1),
        Sheet(id=1),
        Sheet(id=2)
    ])
    db.session.commit()
    db.session.add_all([
        Report(id=1, device_id=2, sheet_id=1),
        Report(id=2, device_id=1, sheet_id=1),
        Report(id=3, device_id=1, sheet_id=2),
    ])
    db.session.commit()

    response = api.get('/sheets/1')
    assert response.status_code == 200
    assert len(response.json['data']['relationships']['report']['data']) == 2
