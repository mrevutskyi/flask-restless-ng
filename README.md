# Flask-Restless-NG #

[![PyPI version](https://badge.fury.io/py/Flask-Restless-NG.svg)](https://badge.fury.io/py/Flask-Restless-NG)
[![Build Status](https://travis-ci.com/mrevutskyi/flask-restless-ng.svg?branch=master)](https://travis-ci.com/mrevutskyi/flask-restless-ng)
[![Coverage Status](https://coveralls.io/repos/github/mrevutskyi/flask-restless-ng/badge.svg?branch=master)](https://coveralls.io/github/mrevutskyi/flask-restless-ng?branch=master)
[![Documentation Status](https://readthedocs.org/projects/flask-restless-ng/badge/?version=latest)](https://flask-restless-ng.readthedocs.io/en/latest/?badge=latest)

## About

This is a Flask extension that creates URL endpoints that satisfy the requirements of the [JSON API][2] specification. 
It is compatible with models that have been defined using either SQLAlchemy or Flask-SQLAlchemy.

This is a fork of [Flask-Restless](https://github.com/jfinkels/flask-restless) module originally written by Jeffrey Finkelstein.

Version `1.0.*` of `Flask-Restless-NG` is fully API compatible with `Flask-Restless` version `1.0.0b1`
with the following improvements:

  * Supports Flask 1.0+ and SQLAlchemy 1.3+
  * 2-5x faster serialization of JSON responses.
  * Miscellaneous bugs fixed

Version `2.0.*` adds a few backward incompatible changes with more performance improvements 

## Introduction ##

This is Flask-Restless, a [Flask][1] extension that creates URL endpoints that
satisfy the requirements of the [JSON API][2] specification. It is compatible
with models that have been defined using either [SQLAlchemy][3] or
[Flask-SQLAlchemy][4].

This document contains some brief instructions concerning installation of
requirements, installation of this extension, configuration and usage of this
extension, and building of documentation.

For more information, see the

  * [documentation][5],
  * [Python Package Index listing][6],
  * [source code repository][7].

[1]: http://flask.pocoo.org
[2]: https://jsonapi.org
[3]: https://sqlalchemy.org
[4]: https://packages.python.org/Flask-SQLAlchemy
[5]: https://flask-restless-ng.readthedocs.org
[6]: https://pypi.python.org/pypi/Flask-Restless-NG
[7]: https://github.com/mrevutskyi/flask-restless-ng

## Installing

This application can be used with any Python version 3.6+

    pip install Flask-Restless-NG

## Example ##

```python
import flask
import flask_restless
import flask_sqlalchemy

# Create the Flask application and the Flask-SQLAlchemy object.
app = flask.Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'
db = flask_sqlalchemy.SQLAlchemy(app)


class Person(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Unicode)
    birth_date = db.Column(db.Date)


class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.Unicode)
    published_at = db.Column(db.DateTime)
    author_id = db.Column(db.Integer, db.ForeignKey('person.id'))
    author = db.relationship(Person, backref=db.backref('articles'))


# Create the database tables.
db.create_all()

# Create the Flask-Restless API manager.
manager = flask_restless.APIManager(app, session=db.session)

# Create API endpoints, which will be available at /api/<table_name> by
# default. Allowed HTTP methods can be specified as well.
manager.create_api(Person, methods=['GET', 'POST', 'DELETE'])
manager.create_api(Article, methods=['GET'])

# start the flask loop
app.run()
```

More information on how to use this extension is available in the [documentation][5].

## Feedback ##

Please fill out the [feedback form](https://forms.gle/Bpj3fEJbFMvDqsDUA), this would help me determine if this
package is still valuable

## Contact ##

Maksym Revutskyi <maksym.revutskyi@gmail.com>
