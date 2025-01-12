.. _main_page:

prawcore
========

.. image:: https://img.shields.io/pypi/v/prawcore.svg
    :alt: Latest prawcore Version
    :target: https://pypi.python.org/pypi/prawcore

.. image:: https://travis-ci.org/praw-dev/prawcore.svg?branch=main
    :target: https://travis-ci.org/praw-dev/prawcore

.. image:: https://coveralls.io/repos/github/praw-dev/prawcore/badge.svg?branch=main
    :target: https://coveralls.io/github/praw-dev/prawcore?branch=main

prawcore is a low-level communication layer used by PRAW 4+.

Installation
------------

Install prawcore using ``pip`` via:

.. code-block:: console

    pip install prawcore

Execution Example
-----------------

The following example demonstrates how to use prawcore to obtain the list of trophies
for a given user using the script-app type. This example assumes you have the
environment variables ``PRAWCORE_CLIENT_ID`` and ``PRAWCORE_CLIENT_SECRET`` set to the
appropriate values for your application.

.. code-block:: python

    #!/usr/bin/env python
    import os
    import pprint
    import prawcore

    authenticator = prawcore.TrustedAuthenticator(
        prawcore.Requestor("YOUR_VALID_USER_AGENT"),
        os.environ["PRAWCORE_CLIENT_ID"],
        os.environ["PRAWCORE_CLIENT_SECRET"],
    )
    authorizer = prawcore.ReadOnlyAuthorizer(authenticator)
    authorizer.refresh()

    with prawcore.session(authorizer) as session:
        pprint.pprint(session.request("GET", "/api/v1/user/bboe/trophies"))

Save the above as ``trophies.py`` and then execute via:

.. code-block:: console

    python trophies.py

Additional examples can be found at:
https://github.com/praw-dev/prawcore/tree/main/examples

Depending on prawcore
---------------------

prawcore follows `semantic versioning <http://semver.org/>`_ with the exception that
deprecations will not be preceded by a minor release. In essense, expect only major
versions to introduce breaking changes to prawcore's public interface. As a result, if
you depend on prawcore then it is a good idea to specify not only the minimum version of
prawcore your package requires, but to also limit the major version.

Below are two examples of how you may want to specify your prawcore dependency:

setup.py
~~~~~~~~

.. code-block:: python

    setup(..., install_requires=["prawcore >=0.1, <1"], ...)

requirements.txt
~~~~~~~~~~~~~~~~

.. code-block:: text

    prawcore >=1.5.1, <2
