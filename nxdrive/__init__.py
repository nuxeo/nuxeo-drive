"""
Nuxeo Drive - Synchronization client for Nuxeo.
https://doc.nuxeo.com/nxdoc/nuxeo-drive/

You can always get the latest version of this module at:
    https://github.com/nuxeo/nuxeo-drive
If that URL should fail, try contacting the author.

Contributors:
    Olivier Grisel
    Antoine Taillefer
    Rémi Cattiau
    Mickaël Schoentgen
    Léa Klein
    Romain Grasland <rgrasland@nuxeo.com>
    Shekhar Gupta <shekhar.gupta@hyland.com>
    and https://github.com/nuxeo/nuxeo-drive/graphs/contributors

Versioning
----------

We use semantic versioning (https://semver.org) compliant with distutils
and the PEP-440.

To declare a beta, use this schema:
    - X.Y.ZbN i.e. "2.4.5b1"
"""

__author__ = "Nuxeo"
__version__ = "7.1.0"
__alfresco_version__ = "1.0.0"
__copyright__ = """
    Copyright © 2025 Hyland Software, Inc. and its affiliates. All rights reserved.
    All Hyland product names are registered or unregistered trademarks of Hyland Software, Inc. or its affiliates
    (https://www.hyland.com/products/nuxeo-platform) and others.

    Licensed under the GNU Lesser General Public License, version 2.1
    (the "License"); you may not use this file except in compliance
    with the License. You may obtain a copy of the License at

        https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

# Auto-discover and register server-type configurations.
# Each server-type package (nuxeo/, alfresco/, …) has a registration.py that
# calls ``nxdrive.drive.server_type.register()``.  We discover them here so
# that drive/ never hard-codes which packages exist.
#
# Note: pkgutil.iter_modules() does not work in frozen (PyInstaller) builds,
# so we fall back to importing known packages when iter_modules yields nothing.
import importlib
import pkgutil
import sys

_discovered = set()
if not getattr(sys, "frozen", False):
    for _finder, _name, _ispkg in pkgutil.iter_modules(__path__):
        if _ispkg and _name not in ("drive",):
            try:
                importlib.import_module(f"nxdrive.{_name}.registration")
                _discovered.add(_name)
            except ModuleNotFoundError:
                pass  # package has no registration – skip

# Frozen fallback: if iter_modules found nothing, try known packages directly.
if not _discovered:
    for _name in ("nuxeo", "alfresco"):
        try:
            importlib.import_module(f"nxdrive.{_name}.registration")
        except ModuleNotFoundError:
            pass
