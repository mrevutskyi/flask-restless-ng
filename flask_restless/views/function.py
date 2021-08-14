# function.py - views for evaluating SQL functions on SQLAlchemy models
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
"""Views for evaluating functions on a SQLAlchemy model.

The main class in this module, :class:`FunctionAPI`, is a
:class:`~flask.MethodView` subclass that creates endpoints for fetching
the result of evaluating a SQL function on a SQLAlchemy model.

"""
from flask import escape
from flask import json
from flask import request
from sqlalchemy.exc import OperationalError

from .base import ModelView
from .base import error_response
from .helpers import evaluate_functions


class FunctionAPI(ModelView):
    """Provides method-based dispatching for :http:method:`get` requests which
    wish to apply SQL functions to all instances of a model.

    .. versionadded:: 0.4

    """

    def get(self):
        """Returns the result of evaluating the SQL functions specified in the
        body of the request.

        For a description of the request and response formats, see
        :ref:`functionevaluation`.

        """
        if 'functions' not in request.args:
            return error_response(400, detail='Must provide `functions` query parameter')
        functions = request.args.get('functions')
        try:
            data = json.loads(str(functions)) or []
        except (TypeError, ValueError, OverflowError):
            return error_response(400, detail='Unable to decode JSON in `functions` query parameter')
        try:
            result = evaluate_functions(self.session, self.model, data)
        except AttributeError as exception:
            return error_response(400, detail=f'No such field "{escape(exception.field)}"')
        except KeyError as exception:
            detail = str(exception)
            return error_response(400, detail=detail)
        except OperationalError as exception:
            return error_response(400, detail=f'No such function "{exception.function}"')
        return dict(data=result), 200, {}
