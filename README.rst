pretix Tables
=============

This is a plugin for `pretix`_. It adds table management to pretix events.

Development setup
------------------

1. Make sure you have a working pretix development setup (this repository is meant
   to live alongside a `pretix`_ checkout, e.g. as ``pretix-dev/pretix``, sharing a
   single virtual environment).

2. Clone this repository next to your pretix checkout.

3. Activate the virtual environment you use for pretix development.

4. Execute ``pip install -e .`` within this directory to register this application
   with pretix's plugin registry.

5. Execute ``make`` within this directory to compile translations.

6. Restart your local pretix server. You can now use the plugin from this repository
   for your events by enabling it in the 'plugins' tab in the settings.

This plugin has CI set up to enforce a few code style rules. To check locally, you
need these packages installed::

    pip install flake8 isort black docformatter

To check your plugin for rule violations, run::

    docformatter --check -r .
    black --check .
    isort -c .
    flake8 .

You can auto-fix some of these issues by running::

    docformatter -r .
    isort .
    black .

To automatically check for these issues before you commit, you can run ``.install-hooks.sh``.


License
-------

Copyright 2026 Backslash Seven

Released under the terms of the Apache License 2.0


.. _pretix: https://github.com/pretix/pretix
