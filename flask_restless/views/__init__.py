# __init__.py - indicates that this directory is a Python package
#
# Copyright 2011 Lincoln de Sousa <lincoln@comum.org>.
# Copyright 2012, 2013, 2014, 2015, 2016 Jeffrey Finkelstein
#           <jeffrey.finkelstein@gmail.com> and contributors.
# Copyright 2020, 2021 Maksym Revutskyi <maksym.revutskyi@gmail.com>
#
# This file is part of Flask-Restless-NG.
#
# Flask-Restless is distributed under both the GNU Affero General Public
# License version 3 and under the 3-clause BSD license. For more
# information, see LICENSE.AGPL and LICENSE.BSD.
"""View classes for responding to JSON API requests with a SQLAlchemy
backend.

The classes :class:`API`, :class:`FunctionAPI`, and
:class:`RelationshipAPI` are the :class:`~flask.MethodView` subclasses
that do most of the work.

"""
from .base import CONTENT_TYPE  # noqa
from .base import ProcessingException  # noqa
from .relationships import RelationshipAPI  # noqa
from .resources import API  # noqa
