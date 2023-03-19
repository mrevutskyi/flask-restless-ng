# helpers.py - helper functions for view classes
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
"""Helper functions for view classes."""
from sqlalchemy.inspection import inspect as sqlalchemy_inspect
from sqlalchemy.sql import func


def upper_keys(dictionary):
    """Returns a new dictionary with the keys of ``dictionary``
    converted to upper case and the values left unchanged.

    """
    return {k.upper(): v for k, v in dictionary.items()}


def count(session, query):
    """Returns the count of the specified `query`.

    This function employs an optimization that bypasses the
    :meth:`sqlalchemy.orm.Query.count` method, which can be very slow
    for large queries.

    """
    # There is no straightforward way to find if SQLAlchemy Statement class has limit set
    if ' LIMIT ' in str(query.statement):
        return query.order_by(None).count()
    counts = query.selectable.with_only_columns(func.count(query.selectable.selected_columns[0]))
    num_results = session.execute(counts.order_by(None)).scalar()
    if num_results is None:
        return query.order_by(None).count()
    return num_results


def changes_on_update(model):
    """Returns a best guess at whether the specified SQLAlchemy model class is
    modified on updates.

    We guess whether this happens by checking whether any columns of model have
    the :attr:`sqlalchemy.Column.onupdate` attribute set.

    """
    return any(column.onupdate is not None for column in sqlalchemy_inspect(model).columns)
