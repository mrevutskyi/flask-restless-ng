# setup.py - packaging and distribution configuration for Flask-Restless
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
"""Flask-Restless-NG is a `Flask`_ extension that provides simple
generation of ReSTful APIs that satisfy the `JSON API`_ specification
given database models defined using `SQLAlchemy`_ (or
`Flask-SQLAlchemy`_).

For more information, see the `documentation`_, `pypi`_, or the `source
code`_ repository.

.. _Flask: http://flask.pocoo.org
.. _SQLAlchemy: https://sqlalchemy.org
.. _Flask-SQLAlchemy: https://pypi.python.org/pypi/Flask-SQLAlchemy
.. _JSON API: http://jsonapi.org
.. _documentation: https://flask-restless-ng.readthedocs.org
.. _pypi: https://pypi.python.org/pypi/Flask-Restless-NG
.. _source code: https://github.com/mrevutskyi/flask-restless-ng

"""
import codecs
import os.path
import re

from setuptools import setup

#: A regular expression capturing the version number from Python code.
VERSION_RE = r"^__version__ = ['\"]([^'\"]*)['\"]"


#: The installation requirements Flask-SQLAlchemy is not
#: required, so the user must install it explicitly.
REQUIREMENTS = [
    'flask>=1.0',
    'sqlalchemy>=1.3',
    'python-dateutil>2.2',
]

#: The absolute path to this file.
HERE = os.path.abspath(os.path.dirname(__file__))


def read(*parts):
    """Reads the entire contents of the file whose path is given as `parts`."""
    with codecs.open(os.path.join(HERE, *parts), 'r') as f:
        return f.read()


def find_version(*file_path):
    """Returns the version number appearing in the file in the given file
    path.

    Each positional argument indicates a member of the path.

    """
    version_file = read(*file_path)
    version_match = re.search(VERSION_RE, version_file, re.MULTILINE)
    if version_match:
        return version_match.group(1)
    raise RuntimeError('Unable to find version string.')


setup(
    author='Maksym Revutskyi',
    author_email='maksym.revutskyi@gmail.com',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Web Environment',
        'Framework :: Flask',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Topic :: Database :: Front-Ends',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
    description='A fork of Flask-Restless with updated dependencies and bug fixes',
    download_url='https://pypi.python.org/pypi/Flask-Restless-NG',
    install_requires=REQUIREMENTS,
    include_package_data=True,
    keywords=['ReST', 'API', 'Flask'],
    license='GNU AGPLv3+ or BSD',
    long_description=__doc__,
    name='Flask-Restless-NG',
    platforms='any',
    python_requires='>=3.6',
    packages=['flask_restless', 'flask_restless.views'],
    test_suite='tests',
    tests_require=[],
    url='https://github.com/mrevutskyi/flask-restless-ng',
    version=find_version('flask_restless', '__init__.py'),
    zip_safe=False,
)
