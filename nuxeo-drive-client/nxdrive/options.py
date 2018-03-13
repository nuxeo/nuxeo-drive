# coding: utf-8
"""
Options management.

The goal is to have a unique object `Options` where the whole configuration
is centralized. Any other part of Drive should use it directly by just
importing the class. No instantiation is needed and therefore it is forbidden.

Using `repr` or `str` on `Options` has different meanings.

    >>> repr(Options)
    Options(delay[default]=30, ...)
    >>> str(Options)
    Options()

`str(Options)` will show only options that are non default (changed by another
configuration):

    >>> Options.set('delay', 42, setter='local')
    >>> Options.set('timeout', -1, setter='server')
    >>> Options.set('locale', 'fr', setter='cli')
    >>> str(Options)
    Options(delay[local]=42, locale[cli]='fr', timeout[server]=-1)

You can access a given option as simply as:

    >>> Options.delay
    30

To set an option, you must call `Options.set` only:

    >>> Options.set('delay', 42)

_For tests purpose_, you can set an option as simply as:

    >>> Options.delay = 42

This is the equivalent of:

    >>> Options.set('delay', 42, setter='manual')

_For tests purpose_, a `Options.mock` decorator is available.

---

We also provide the `server_updater()` helper.
It creates the worker that will check for options update on the server.
"""

from __future__ import unicode_literals

import locale
import logging
import os.path
import sys
from copy import deepcopy

try:
    from typing import Any, Dict, Tuple
except ImportError:
    pass


__all__ = ('Options', 'server_updater')

log = logging.getLogger(__name__)


class MetaOptions(type):
    """
    All configurable options are used by this lone object.

    Each options is a dict of tuple:

        {
            name: (value, setter),
        }

        - name: option name
        - value: option value
        - setter: which part set it up (the server, the default conf, ...)

    Depending on the setter, the options can or cannot be updated.
    A simple log line will be sent using the logging module.
    """

    # Ignored files, checked lowercase
    __files = (
        r'^atmp\d+$',  # AutoCAD tmp file
    )  # type: Tuple[unicode]

    # Ignored prefixes, checked lowercase
    __prefixes = (
        '.',
        'desktop.ini',
        'icon\r',
        'thumbs.db',
        '~$',
    )  # type: Tuple[unicode]

    # Ignored suffixes, checked lowercase
    __suffixes = (
        '.bak',
        '.crdownload',
        '.dwl',
        '.dwl2',
        '.lnk',
        '.lock',
        '.nxpart',
        '.part',
        '.partial',
        '.swp',
        '.tmp',
        '~',
    )  # type: Tuple[unicode]

    # Setters weight, higher is more powerfull
    _setters = {
        'default': 0,
        'server': 1,
        'local': 2,
        'cli': 3,
        'manual': 4,
    }  # type: Dict[unicode, int]

    # Default options
    options = {
        'beta_channel': (False, 'default'),
        'beta_update_site_url': (
            'https://community.nuxeo.com/static/drive-updates', 'default'),
        'consider_ssl_errors': (False, 'default'),
        'debug': (False, 'default'),
        'debug_pydev': (False, 'default'),
        'delay': (30, 'default'),
        'force_locale': (None, 'default'),
        'handshake_timeout': (60, 'default'),
        'ignored_files': (__files, 'default'),
        'ignored_prefixes': (__prefixes, 'default'),
        'ignored_suffixes': (__suffixes, 'default'),
        'is_frozen': (getattr(sys, 'frozen', False), 'default'),
        'locale': ('en', 'default'),
        'log_filename': (None, 'default'),
        'log_level_console': ('INFO', 'default'),
        'log_level_file': ('DEBUG', 'default'),
        'max_errors': (3, 'default'),
        'max_sync_step': (10, 'default'),
        'nxdrive_home': (
            os.path.join(
                unicode(os.path.expanduser('~').decode(
                    locale.getpreferredencoding() or 'utf-8')),
                '.nuxeo-drive'),
            'default'),
        'nofscheck': (False, 'default'),
        'protocol_url': (None, 'default'),
        'proxy_exceptions': (None, 'default'),
        'proxy_server': (None, 'default'),
        'proxy_type': (None, 'default'),
        'remote_repo': ('default', 'default'),
        'res_dir': (
            os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(__file__)),
                         'data'),
            'default'),
        'server_version': (None, 'default'),
        'theme': ('ui5', 'default'),
        'startup_page': ('drive_login.jsp', 'default'),
        'timeout': (30, 'default'),
        'ui': ('jsf', 'default'),
        'update_check_delay': (3600, 'default'),
        'update_site_url': (
            'http://community.nuxeo.com/static/drive-updates', 'default'),
    }  # type: Dict[unicode, Tuple[Any, unicode]]

    default_options = deepcopy(options)

    # Callbacks for any option change.
    # Callable signature must be: (new_value: str) -> None
    # The return value is not checked.
    callbacks = {}  # type: Dict[unicode, callable]

    def __getattr__(self, item):
        # type (unicode) -> Any
        """
        Override to allow retrieving an option as simply as `Options.delay`.

        If the option does not exist, returns `None`.
        """

        try:
            value, _ = MetaOptions.options[item]
        except KeyError:
            value = None
        return value

    def __setattr__(self, item, value):
        # type: (unicode, Any) -> None
        """
        Override to allow setting an option as simply as `Options.delay = 42`.
        If the option does not exist, it does nothing.

        Use in tests only.
        """

        try:
            MetaOptions.set(item, value, setter='manual')
        except KeyError:
            pass

    def __repr__(self):
        """ Display all options. """
        options = ['{}[{}]={!r}'.format(name, setter, value)
                   for name, (value, setter) in MetaOptions.options.items()]
        return 'Options({})'.format(', '.join(options))

    def __str__(self):
        """ Display non default options. """
        options = ['{}[{}]={!r}'.format(name, setter, value)
                   for name, (value, setter) in MetaOptions.options.items()
                   if setter != 'default']
        return 'Options({})'.format(', '.join(options))

    @staticmethod
    def set(item, new_value, setter='default', fail_on_error=True):
        # type: (unicode, Any, unicode, bool) -> None
        """
        Set an option.

        If the option does not exist, if will be ignored if `fail_on_error`
        equals `False`, otherwise `KeyError` will be raised.

        If the `setter` has the right to override the option value, set
        `new_value`, else do nothing.

        Any `list` will be converted to a sorted `tuple`.
        Any `bytes` value will be decoded.

        If the type of the new value differs from the original one,
        raises `ValueError`.  It helps preventing assigning a `str` when
        a `tuple` is required to keep the rest of the code consistent.

        Finally, if a callback is set for that option and if the `new_value`
        is assigned to the option, the callback will be called with the
        `new_value` as sole argument.
        """

        try:
            old_value, old_setter = MetaOptions.options[item]
        except KeyError:
            if fail_on_error:
                raise
        else:
            if isinstance(new_value, list):
                # Need a tuple when JSON sends a simple list
                new_value = tuple(sorted(new_value))
            elif isinstance(new_value, bytes):
                # No option needs bytes
                # TODO NXDRIVE-691: Remove that part?
                new_value = new_value.decode(
                    locale.getpreferredencoding() or 'utf-8')

            # Try implicit conversions. We do not use isinstance to prevent
            # checking against subtypes.
            type_orig = type(old_value)
            if type_orig is bool:
                try:
                    new_value = bool(new_value)
                except (ValueError, TypeError):
                    pass
            elif type_orig is int:
                try:
                    new_value = int(new_value)
                except (ValueError, TypeError):
                    pass

            if new_value == old_value:
                return

            # We allow to set something when the default is None
            if (not isinstance(new_value, type_orig)
                    and not isinstance(old_value, type(None))):
                err = ('The value of the option %r is of type %s,'
                       ' while %s is required.')
                raise TypeError(err % (
                    item, type(new_value).__name__, type(old_value).__name__))

            # Only update if the setter has rights to
            setter = setter.lower()
            if MetaOptions._setters[setter] >= MetaOptions._setters[old_setter]:
                MetaOptions.options[item] = new_value, setter
                log.debug(
                    'Option %s updated: %r -> %r [%s]',
                    item, old_value, new_value, setter)

                # Callback for that option
                try:
                    callback = MetaOptions.callbacks[item]
                except KeyError:
                    pass
                else:
                    callback(new_value)

    @staticmethod
    def update(items, setter='default', fail_on_error=False):
        # type: (Any, unicode) -> None
        """
        Batch update options.
        If an option does not exist, it will be ignored.
        """

        if isinstance(items, dict):
            # To handle local and server config files
            items = items.items()
        elif not isinstance(items, list):
            # To handle CLI (type is argparse.Namespace)
            items = items._get_kwargs()

        for item, value in items:
            MetaOptions.set(
                item, value, setter=setter, fail_on_error=fail_on_error)

    @staticmethod
    def mock():
        # type: () -> callable
        """
        Decorator for tests.
        It saves initial states, launches the test and restores states then.

            @Options.mock()
            def test_method(self):
                ...

            @Options.mock()
            def test_function():
                ...

        """
        def reinit():
            setattr(MetaOptions, 'callbacks', {})
            setattr(MetaOptions, 'options',
                    deepcopy(MetaOptions.default_options))

        def decorator(func):
            def wrapper(*args, **kwargs):
                reinit()
                try:
                    return func(*args, **kwargs)
                finally:
                    reinit()
            return wrapper
        return decorator


class Options(object):
    __metaclass__ = MetaOptions

    def __init__(self):
        """ Prevent class instances. """
        raise RuntimeError('Cannot be instanciated.')


def server_updater(*args):
    # type: (*Any) -> ServerOptionsUpdater
    """
    Helper to create the worker that will check for options updates
    on the server.
    We use this to prevent loading any Drive related stuff and keep
    the possibility to import other classes without nothing else needed.
    """

    import json

    from PyQt4.QtCore import pyqtSlot
    from .engine.workers import PollWorker

    class ServerOptionsUpdater(PollWorker):
        """ Class for checking server's config.json updates. """

        def __init__(self, manager):
            # type: (Manager) -> None

            super(ServerOptionsUpdater, self).__init__(
                Options.update_check_delay)
            self.manager = manager

        @pyqtSlot()
        def _poll(self):
            # type: () -> bool
            """ Check for the configuration file and apply updates. """

            for _, engine in self.manager._engines.items():
                client = engine.get_remote_doc_client()
                if not client:
                    continue

                try:
                    raw, _ = client.do_get(
                        client.rest_api_url + 'drive/configuration')
                    conf = json.loads(raw, encoding='utf-8')
                except Exception as exc:
                    log.error('Polling error: {}'.format(exc))
                else:
                    Options.update(conf, setter='server', fail_on_error=True)
                    break

            return True

    return ServerOptionsUpdater(*args)
