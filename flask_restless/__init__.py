# Copyright 2011 Lincoln de Sousa <lincoln@comum.org>.
# Copyright 2012, 2013, 2014, 2015, 2016 Jeffrey Finkelstein
#           <jeffrey.finkelstein@gmail.com> and contributors.
# Copyright 2020, 2021 Maksym Revutskyi <maksym.revutskyi@gmail.com> and contributors.
#
# This file is part of Flask-Restless-NG.
#
# Flask-Restless is distributed under both the GNU Affero General Public
# License version 3 and under the 3-clause BSD license. For more
# information, see LICENSE.AGPL and LICENSE.BSD.
"""Provides classes for creating endpoints for interacting with
SQLAlchemy models via the JSON API protocol.

"""
#: The current version of this extension.
__version__ = '2.2.1'


# The following names are available as part of the public API for Flask-Restless-NG.
# End users of this package can import these names by doing
# ``from flask_restless import APIManager``, for example.
from .manager import APIManager  # noqa
from .manager import IllegalArgumentError  # noqa
from .serialization import DeserializationException  # noqa
from .serialization import Deserializer  # noqa
from .serialization import SerializationException  # noqa
from .serialization import Serializer  # noqa
from .views import CONTENT_TYPE  # noqa
from .views import ProcessingException  # noqa
