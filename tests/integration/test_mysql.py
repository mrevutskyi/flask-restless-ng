import pytest
from flask import Flask
from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Table
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import backref
from sqlalchemy.orm import relationship
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm import sessionmaker

from flask_restless import APIManager

Base = declarative_base()


starred_orders = Table(
    'starred_orders', Base.metadata,
    Column('client_id', Integer, ForeignKey('client.id')),
    Column('order_id', Integer, ForeignKey('order.id')),
)


class Client(Base):
    __tablename__ = 'client'

    id = Column(Integer, primary_key=True)
    name = Column(String(64))

    orders = relationship('Order', backref=backref('client'), primaryjoin='and_(Client.id==Order.client_id, Order.archived==0)')
    starred_orders = relationship("Order",
                                  secondary='starred_orders',
                                  primaryjoin='and_(Client.id==starred_orders.c.client_id, Order.archived==0)')
    all_orders = relationship('Order')


class Order(Base):
    __tablename__ = 'order'

    id = Column(Integer, primary_key=True)
    description = Column(String(64))
    archived = Column(Boolean(), default=False)

    client_id = Column(Integer, ForeignKey('client.id'))


@pytest.fixture(scope='module', autouse=True)
def api():
    engine = create_engine('mysql+pymysql://db_user:password@localhost/flask_restless', echo=True)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))()
    client = Client(id=1, name='Client')
    client.starred_orders.append(Order(id=1, client_id=1))
    session.add(client)
    session.commit()
    session.bulk_save_objects([Order(id=i, client_id=1) for i in range(2, 6)])
    session.bulk_save_objects([Order(id=i, client_id=1, archived=True) for i in range(6, 11)])
    session.commit()

    app = Flask(__name__)
    app.testing = True

    api_manager = APIManager(app=app, session=session, url_prefix='', include_links=False)
    api_manager.create_api(Client, collection_name='clients', page_size=0)
    api_manager.create_api(Order, collection_name='orders', page_size=0)
    yield app.test_client()


@pytest.mark.integration
def test_responses(api):
    response = api.get('/clients/1?include=orders,starred_orders')
    assert response.status_code == 200
    document = response.json
    assert len(document['included']) == 5
