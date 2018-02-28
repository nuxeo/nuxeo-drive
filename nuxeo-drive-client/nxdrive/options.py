# coding: utf-8
"""
Options managements.

The goal is to have a uniq object `Options` where the whole configuration
is centralized.  Any other part of Drive should use it directly by just
importing the class.  No instanciation is needed and therefore forbidden.

    >>> from nxdrive.options import Options

Using `repr` or `str` on `Options` has different meaning.

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

You can access to a given option as simply as:

    >>> Options.delay
    30

To set an option, you must call `Options.set` only:

    >>> Options.set('delay', 42)

_For tests purpose_, you can set an option as simply as:

    >>> Options.delay = 42

This is the equivalent of:

    >>> Options.set('delay', 42, setter='manual')

_For tests purpose_, a `Options.mock` decorator is available.
"""

from __future__ import unicode_literals

import locale
import logging
import os.path
import sys

# from typing import Any, Dict, Tuple

__all__ = ('Options',)

log = logging.getLogger(__name__)


class MetaOptions(type):
    """
    All configurable options are used by this lone object.

    Each options is a dict of tuple:

        {
            name: (value, setter),
        }

        - name: option's name
        - value: option's value
        - setter: which part setted it up (the server, the default conf, ...)

    Depending the setter, the options can or cannot be updated.  A simple log
    line will be sent using the logging module.
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
            'http://community.nuxeo.com/static/drive-tests/', 'default'),
        'consider_ssl_errors': (False, 'default'),
        'debug': (False, 'default'),
        'debug_pydev': (False, 'default'),
        'delay': (30, 'default'),
        'force_locale': (None, 'default'),
        'handshake_timeout': (60, 'default'),
        'ignored_files': (__files, 'default'),
        'ignored_prefixes': (__prefixes, 'default'),
        'ignored_suffixes': (__suffixes, 'default'),
        'is_frozen': (getattr(sys, 'frozen', False), 'manual'),
        'locale': ('en', 'default'),
        'log_filename': (None, 'default'),
        'log_level_console': ('INFO', 'default'),
        'log_level_file': ('DEBUG', 'default'),
        'max_errors': (3, 'default'),
        'max_sync_step': (10, 'default'),
        'nxdrive_home': (
            os.path.join(os.path.expanduser('~'), '.nuxeo-drive'), 'default'),
        'nofscheck': (False, 'default'),
        'protocol_url': (None, 'default'),
        'proxy_exceptions': (None, 'default'),
        'proxy_server': (None, 'default'),
        'proxy_type': (None, 'default'),
        'remote_repo': ('default', 'default'),
        'res_dir': (
            os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(__file__)),
                         'data'),
            'manual'),
        'server_version': (None, 'default'),
        'theme': ('ui5', 'default'),
        'startup_page': ('drive_login.jsp', 'default'),
        'stop_on_error': (True, 'default'),
        'timeout': (30, 'default'),
        'ui': ('jsf', 'default'),
        'update_check_delay': (3600, 'default'),
        'update_site_url': (
            'http://community.nuxeo.com/static/drive/', 'default'),
    }  # type: Dict[unicode, Tuple[Any, unicode]]

    # Callbacks for any option change.
    # Callable signature must be: (new_value: str) -> None
    # The return value is not checked.
    callbacks = {}  # type: Dict[unicode, callable]

    def __getattr__(self, item):
        # type (unicode) -> Any
        """
        Override to permit retreiving an option as simply as `Options.delay`.

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
        Override to permit setting an option as simply as `Options.delay = 42`.
        If the option does not exist, does nothing.

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
        equals `False`, overwise `KeyError` will be raised.

        If the `setter` has the right to override the option's value, set
        `new_value`, else do nothing.

        Any `list` will be converted to a sorted `tuple`.
        Any `bytes` value will be decoded.

        If the type of the new value differs from the original one,
        raises `ValueError`.  It helps preventing assigning a `str` when
        a `tuple` is required to keep the rest of code consistent.

        Finally, if a callback is set for that option and if the `new_value`
        is assigned to the option, the callback will be called with the
        `new_value` as lone argument.
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

            # Try implicit conversions.  We do not use isinstance to prevent
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

        from copy import deepcopy

        def decorator(func):
            def wrapper(*args, **kwargs):
                callbacks_orig = deepcopy(MetaOptions.__dict__['callbacks'])
                options_orig = deepcopy(MetaOptions.__dict__['options'])
                try:
                    return func(*args, **kwargs)
                finally:
                    setattr(MetaOptions, 'callbacks', callbacks_orig)
                    setattr(MetaOptions, 'options', options_orig)
            return wrapper
        return decorator


class Options(object):
    __metaclass__ = MetaOptions

    def __init__(self):
        """ Prevent class instances. """
        raise RuntimeError('Cannot be instanciated.')
