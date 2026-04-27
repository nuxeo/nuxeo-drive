"""
This module contains the implementation of the MultiFolderDialog class.
This is a dialog for selecting multiple folders in the NxDrive application.
"""

import plistlib
import string
import struct
import subprocess
from logging import getLogger
from pathlib import Path

from PyQt6.QtWidgets import QListWidgetItem

from nxdrive.qt.imports import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDir,
    QEvent,
    QFileSystemModel,
    QFont,
    QFontMetricsF,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QModelIndex,
    QObject,
    QPushButton,
    QSize,
    QSizePolicy,
    QStandardItem,
    QStandardItemModel,
    Qt,
    QTreeView,
    QVBoxLayout,
)

from ..constants import LINUX, MAC, WINDOWS
from ..translator import Translator

if WINDOWS:
    import ctypes
    import winreg
    from ctypes import windll

log = getLogger(__name__)


class CenteredHeaderFileSystemModel(QFileSystemModel):
    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Qt.AlignmentFlag | object:
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignCenter
        return super().headerData(section, orientation, role)


class MultiFolderDialog(QDialog):
    # Maps English location names (used as navigation keys) to i18n translation keys
    _STD_LOC_KEYS: dict[str, str] = {
        "Home": "HOME",
        "Applications": "APPLICATIONS",
        "Desktop": "DESKTOP",
        "Documents": "DOCUMENTS",
        "Downloads": "DOWNLOADS",
        "Pictures": "PICTURES",
        "Music": "MUSIC",
        "Movies": "MOVIES",
        "Videos": "VIDEOS",
        "Root": "ROOT",
    }

    def __init__(self, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(Translator.get("SELECT_FILES_FOLDERS"))
        self._in_tag_mode = False

        # Load QSS stylesheet
        qss_path = Path(__file__).parent / "multi_folder_dialog.qss"
        if qss_path.exists():
            self.setStyleSheet(qss_path.read_text(encoding="utf-8"))

        # Set minimum size
        self.setMinimumSize(700, 450)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        path_layout = QHBoxLayout()
        path_layout.setSpacing(4)
        bottom_layout = QHBoxLayout()

        # Show hidden files checkbox
        self.showHidden = QCheckBox()
        self.showHidden.setText(Translator.get("SHOW_HIDDEN"))
        self.showHidden.setChecked(False)
        self.showHidden.checkStateChanged.connect(self.show_hidden_files)
        # Home button
        self.btnHome = QPushButton()
        self.btnHome.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.btnHome.setText(Translator.get("HOME"))
        self.btnHome.clicked.connect(self.go_home)
        # Up button
        self.btnUp = QPushButton()
        self.btnUp.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.btnUp.setText(Translator.get("GO_UP"))
        self.btnUp.clicked.connect(self.go_up)
        # Path bar
        self.path_bar = QLineEdit()
        self.path_bar.setText(QDir.homePath())
        self.path_bar.textChanged.connect(self.path_changed)

        # Path bar layout
        path_layout.addWidget(self.path_bar)
        path_layout.addWidget(self.showHidden)
        path_layout.addWidget(self.btnHome)
        path_layout.addWidget(self.btnUp)
        layout.addLayout(path_layout)

        # Add label
        self.label = QLabel(Translator.get("SELECT_FILES_FOLDERS_LABEL"))
        layout.addWidget(self.label)

        # File System Model
        self.model = CenteredHeaderFileSystemModel()
        self.model.setRootPath(QDir.homePath())

        # Allow files and directories except '.' and '..'
        self.model.setFilter(QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot)
        self.model.directoryLoaded.connect(
            lambda _: self.tree.resizeColumnToContents(0)
        )

        view_layout = QHBoxLayout()
        view_layout.setSpacing(6)
        panel_layout = QVBoxLayout()
        panel_layout.setSpacing(4)

        panel_layout.addWidget(self.panel_locations())
        view_layout.addLayout(panel_layout)

        # Create a tree view and set the model
        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(QDir.homePath()))
        # Allow Shift+Click and Ctrl+Click for multiple selection
        self.tree.setSelectionMode(QTreeView.SelectionMode.ExtendedSelection)
        # Show headers to display file attributes
        self.tree.setHeaderHidden(False)
        # Handle double-click to navigate into directories
        self.tree.doubleClicked.connect(self.load_directory)

        # Resize the width when the directory is collapsed/expanded
        self.tree.expanded.connect(lambda _: self.tree.resizeColumnToContents(0))
        self.tree.collapsed.connect(lambda _: self.tree.resizeColumnToContents(0))

        # Add the tree view to the layout
        view_layout.addWidget(self.tree)

        layout.addLayout(view_layout)

        bottom_layout.setContentsMargins(0, 6, 0, 0)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button:
            ok_button.setText(Translator.get("ADD"))
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button:
            cancel_button.setText(Translator.get("CANCEL"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        # Adding Add/Cancel buttons to the layout
        bottom_layout.addWidget(buttons)
        layout.addLayout(bottom_layout)

    def selected_paths(self) -> list[str]:
        # Tag mode: paths stored as UserRole data on QStandardItemModel items
        if self._in_tag_mode:
            selection_model = self.tree.selectionModel()
            if not selection_model:
                return []
            paths = []
            for index in selection_model.selectedIndexes():
                if index.column() == 0:
                    path = index.data(Qt.ItemDataRole.UserRole)
                    if path:
                        paths.append(path)
            return list(set(paths))

        selection_model = self.tree.selectionModel()
        if selection_model:
            indexes = selection_model.selectedIndexes()
        else:
            return []
        paths = []
        for index in indexes:
            if index.column() == 0:
                path = self.model.filePath(index)
                # Check for read access
                # if not os.access(path, os.R_OK):
                #     msg = QMessageBox()
                #     msg.setIcon(QMessageBox.Icon.Warning)
                #     msg.setWindowTitle(self.tr("Permission Denied"))
                #     msg.setText(self.tr(f"You don't have read access to {path}."))
                #     msg.exec()
                #     return []
                paths.append(path)
        return list(set(paths))  # remove duplicates

    def _restore_filesystem_model(self) -> None:
        """Switch back from tag mode to the normal filesystem model."""
        if self._in_tag_mode:
            self._in_tag_mode = False
            self.tree.setModel(self.model)
            self.model.directoryLoaded.connect(
                lambda _: self.tree.resizeColumnToContents(0)
            )

    def _show_empty_drive(self, drive_path: str) -> None:
        """Show an empty QTreeView for a drive with no accessible content."""
        empty_model = QStandardItemModel()
        empty_model.setHorizontalHeaderLabels(
            [
                Translator.get("NAME"),
                Translator.get("SIZE"),
                Translator.get("TYPE"),
                Translator.get("DATE_MODIFIED"),
            ]
        )
        self._in_tag_mode = True
        self.tree.setModel(empty_model)
        self.path_bar.blockSignals(True)
        self.path_bar.setText(drive_path)
        self.path_bar.setStyleSheet("")
        self.path_bar.blockSignals(False)

    def path_changed(self) -> None:
        self._restore_filesystem_model()
        path = Path(self.path_bar.text())
        if path.exists():
            self.model.setRootPath(str(path))
            self.tree.setRootIndex(self.model.index(str(path)))
            self.tree.resizeColumnToContents(0)
            self.path_bar.setStyleSheet("")
        else:
            self.path_bar.setStyleSheet("background-color: #ffcccc")

    def show_hidden_files(self) -> None:
        if self.showHidden.isChecked():
            self.model.setFilter(
                QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot | QDir.Filter.Hidden
            )
        else:
            self.model.setFilter(QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot)
        # Re-apply the current root path to force a refresh of the tree view
        current_path = self.path_bar.text()
        if Path(current_path).exists():
            self.model.setRootPath(current_path)
            self.tree.setRootIndex(self.model.index(current_path))

    def load_directory(self, index: QModelIndex) -> None:
        if index.column() == 0:
            folder_path = Path(self.model.filePath(index))
            if folder_path.is_dir():
                # Update the path bar to reflect the new directory
                # This automatically triggers the path_changed method to update the tree view
                self.path_bar.setText(str(folder_path))

    def go_home(self) -> None:
        self.path_bar.setText(QDir.homePath())

    def go_up(self) -> None:
        current_path = Path(self.path_bar.text())
        if current_path.exists():
            parent_path = current_path.parent
        else:
            parent_path = None

        # Prevent going above the root directory
        if not parent_path or not parent_path.exists():
            return

        self.path_bar.setText(str(parent_path))

    def navigate_to_location(self, item: QListWidgetItem) -> None:
        # Use English key stored in UserRole for standard locations; fall back to
        # item text for dynamic items (Finder favorites, tags, drives, mounts).
        location = item.data(Qt.ItemDataRole.UserRole) or item.text()
        # MacOS paths
        if MAC:
            # Tags are handled separately — don't restore filesystem model
            is_tag = hasattr(self, "_finder_tags") and location in self._finder_tags
            if not is_tag:
                self._restore_filesystem_model()
            match location:
                case "Home":
                    self.path_bar.setText(QDir.homePath())
                case "Applications":
                    self.path_bar.setText("/Applications")
                case "Desktop":
                    self.path_bar.setText(QDir.homePath() + "/Desktop")
                case "Documents":
                    self.path_bar.setText(QDir.homePath() + "/Documents")
                case "Downloads":
                    self.path_bar.setText(QDir.homePath() + "/Downloads")
                case "Pictures":
                    self.path_bar.setText(QDir.homePath() + "/Pictures")
                case "Music":
                    self.path_bar.setText(QDir.homePath() + "/Music")
                case "Movies":
                    self.path_bar.setText(QDir.homePath() + "/Movies")
                case loc if loc.startswith("Mount/"):
                    log.debug("Detecting mount points for MacOS")
                    mount_path = self.macos_mount_points().get(location)
                    if mount_path:
                        self.path_bar.setText(mount_path)
                case loc if hasattr(
                    self, "_finder_favorites"
                ) and loc in self._finder_favorites:
                    self.path_bar.setText(self._finder_favorites[loc])
                case loc if hasattr(self, "_finder_tags") and loc in self._finder_tags:
                    self._show_tagged_files(loc)
        # Windows paths
        elif WINDOWS:
            match location:
                case "Home":
                    self.path_bar.setText(QDir.homePath())
                case "Desktop":
                    self.path_bar.setText(QDir.homePath() + "/Desktop")
                case "Downloads":
                    self.path_bar.setText(QDir.homePath() + "/Downloads")
                case "Documents":
                    self.path_bar.setText(QDir.homePath() + "/Documents")
                case "Pictures":
                    self.path_bar.setText(QDir.homePath() + "/Pictures")
                case "Music":
                    self.path_bar.setText(QDir.homePath() + "/Music")
                case "Videos":
                    self.path_bar.setText(QDir.homePath() + "/Videos")
                case loc if loc in self._windows_fixed_drives:
                    self.path_bar.setText(loc)
                case loc if loc in self._windows_onedrive_paths:
                    self.path_bar.setText(self._windows_onedrive_paths[loc])
                case loc if loc in self._windows_mountable_drives:
                    drive_path = self._windows_mountable_drives[loc]
                    try:
                        has_content = Path(drive_path).exists() and any(
                            Path(drive_path).iterdir()
                        )
                    except OSError:
                        has_content = False
                    if has_content:
                        self.path_bar.setText(drive_path)
                    else:
                        self._show_empty_drive(drive_path)
                case loc if loc in self._windows_pinned_items:
                    self.path_bar.setText(self._windows_pinned_items[loc])
                case loc if loc in self._windows_network_locations:
                    self.path_bar.setText(self._windows_network_locations[loc])
        # Linux paths
        elif LINUX:
            self._restore_filesystem_model()
            linux_locs = self.linux_standard_locations()
            if location in linux_locs:
                self.path_bar.setText(linux_locs[location])
            elif (
                hasattr(self, "_linux_mount_points")
                and location in self._linux_mount_points
            ):
                self.path_bar.setText(self._linux_mount_points[location])

    @staticmethod
    def linux_standard_locations() -> dict[str, str]:
        """Gets standard folder locations on Linux."""
        home = QDir.homePath()
        return {
            "Root": "/",
            "Home": home,
            "Desktop": home + "/Desktop",
            "Documents": home + "/Documents",
            "Downloads": home + "/Downloads",
            "Pictures": home + "/Pictures",
            "Music": home + "/Music",
            "Videos": home + "/Videos",
        }

    @staticmethod
    def linux_mount_points() -> dict[str, str]:
        """Gets mountable locations on Linux from /media and /mnt."""
        mounts: dict[str, str] = {}
        for base in ("/media", "/mnt"):
            base_path = Path(base)
            if not base_path.is_dir():
                continue
            try:
                for entry in sorted(base_path.iterdir()):
                    if entry.is_dir():
                        # /media/<user>/<device> structure
                        if base == "/media":
                            try:
                                for sub in sorted(entry.iterdir()):
                                    if sub.is_dir():
                                        mounts[sub.name] = str(sub)
                            except PermissionError:
                                pass
                        else:
                            mounts[entry.name] = str(entry)
            except PermissionError:
                pass
        return mounts

    @staticmethod
    def macos_mount_points() -> dict[str, str]:
        output = subprocess.check_output(["mount"]).decode("utf-8")
        mounts = {}
        for line in output.splitlines():
            line = line.split(" on ")[1]
            if line.startswith("/Volumes/"):
                name = "Mount/" + (line.split(" (")[0].split("/Volumes/")[1])
                path = line.split(" (")[0]
                mounts.update({name: path})
        return mounts

    def macos_finder_favorites(self) -> dict[str, str]:
        """Gets Finder sidebar favorite paths on macOS from the shared file list."""
        favorites = {}
        sfl_dir = Path.home() / "Library/Application Support/com.apple.sharedfilelist"
        # Try sfl4, sfl3, sfl2 in order (newer macOS versions use higher numbers)
        for suffix in ("sfl4", "sfl3", "sfl2"):
            sfl_path = sfl_dir / f"com.apple.LSSharedFileList.FavoriteItems.{suffix}"
            if sfl_path.exists():
                try:
                    favorites = self._parse_sfl_file(sfl_path)
                except Exception:
                    log.error(
                        "Failed to parse Finder favorites from %s",
                        sfl_path,
                        exc_info=True,
                    )
                break
        return favorites

    @staticmethod
    def macos_finder_tags() -> list[str]:
        """Gets the Finder favorite tag names on macOS."""
        try:
            output = subprocess.check_output(
                ["defaults", "read", "com.apple.finder", "FavoriteTagNames"],
                stderr=subprocess.DEVNULL,
            ).decode("utf-8")
            # Parse the plist-style array output: lines between ( and )
            tags: list[str] = []
            for line in output.splitlines():
                line = line.strip().rstrip(",")
                if (
                    line in ("(", ")", "")
                    or line.startswith('"')
                    and not line.strip('"')
                ):
                    continue
                tag_name = line.strip('"')
                if tag_name:
                    tags.append(tag_name)
            return tags
        except Exception:
            log.debug("Failed to read Finder tags", exc_info=True)
            return []

    def _show_tagged_files(self, tag_name: str) -> None:
        """Find files with the given macOS Finder tag and show only them in the tree."""
        try:
            output = subprocess.check_output(
                ["mdfind", f'kMDItemUserTags == "{tag_name}"'],
                stderr=subprocess.DEVNULL,
                timeout=10,
            ).decode("utf-8")
            paths = [p for p in output.strip().splitlines() if p and Path(p).exists()]
        except Exception:
            log.error("Failed to find files for tag %r", tag_name, exc_info=True)
            paths = []

        # Build a QStandardItemModel with only the tagged files
        tag_model = QStandardItemModel()
        tag_model.setHorizontalHeaderLabels(
            [Translator.get("NAME"), Translator.get("PATH")]
        )
        for file_path in sorted(paths):
            name_item = QStandardItem(Path(file_path).name)
            name_item.setData(file_path, Qt.ItemDataRole.UserRole)
            name_item.setEditable(False)
            path_item = QStandardItem(file_path)
            path_item.setEditable(False)
            tag_model.appendRow([name_item, path_item])

        self._in_tag_mode = True
        self.tree.setModel(tag_model)
        self.tree.resizeColumnToContents(0)
        self.tree.resizeColumnToContents(1)

        # Update path bar to indicate tag mode
        self.path_bar.blockSignals(True)
        self.path_bar.setText(f"Tag: {tag_name}")
        self.path_bar.setStyleSheet("")
        self.path_bar.blockSignals(False)

        log.debug("Showing %d files for tag %r", len(paths), tag_name)

    @staticmethod
    def _parse_sfl_file(sfl_path: Path) -> dict[str, str]:
        """Parse an SFL/SFL2/SFL3/SFL4 file and return {name: path} for valid favorites."""
        favorites: dict[str, str] = {}
        try:
            with open(sfl_path, "rb") as f:
                plist_data = plistlib.load(f)
        except PermissionError:
            log.debug(
                "Direct read of %s denied by TCC, trying plutil subprocess",
                sfl_path,
            )
            plist_data = MultiFolderDialog._read_plist_via_plutil(sfl_path)
            if plist_data is None:
                log.error(
                    "Cannot read Finder favorites: grant Full Disk Access to this "
                    "app in System Settings > Privacy & Security > Full Disk Access"
                )
                return favorites

        # NSKeyedArchiver format (sfl3/sfl4): bookmark data is in $objects
        if "$objects" in plist_data:
            objects = plist_data["$objects"]
            for obj in objects:
                if isinstance(obj, bytes) and len(obj) > 48 and obj[:4] == b"book":
                    path = MultiFolderDialog._path_from_bookmark(obj)
                    if path and Path(path).exists():
                        favorites[Path(path).name] = path
        # Older plain plist format (sfl2): items list with Bookmark key
        elif "items" in plist_data:
            for item in plist_data["items"]:
                bookmark_data = item.get("Bookmark")
                if not bookmark_data:
                    continue
                path = MultiFolderDialog._path_from_bookmark(bytes(bookmark_data))
                if path and Path(path).exists():
                    name = item.get("Name") or Path(path).name
                    favorites[name] = path
        return favorites

    @staticmethod
    def _read_plist_via_plutil(sfl_path: Path) -> dict | None:
        """Read a binary plist file via the plutil system binary (TCC workaround)."""
        try:
            xml_bytes = subprocess.check_output(
                ["plutil", "-convert", "xml1", "-o", "-", str(sfl_path)],
                stderr=subprocess.DEVNULL,
            )
            return plistlib.loads(xml_bytes)
        except (subprocess.CalledProcessError, Exception):
            log.debug("plutil fallback also failed for %s", sfl_path, exc_info=True)
            return None

    @staticmethod
    def _path_from_bookmark(data: bytes) -> str | None:
        """Extract file path from macOS bookmark binary data."""
        try:
            if len(data) < 48 or data[:4] != b"book":
                return None

            # Data start offset is stored at header byte 12 (LE uint32)
            data_start = struct.unpack_from("<I", data, 12)[0]

            # First 4 bytes of data area: offset to TOC (relative to data_start)
            toc_offset = data_start + struct.unpack_from("<I", data, data_start)[0]
            if toc_offset + 20 > len(data):
                return None

            # TOC header: size(4) + magic(4) + id(4) + next_toc(4) + num_entries(4)
            num_entries = struct.unpack_from("<I", data, toc_offset + 16)[0]
            if num_entries > 100:
                return None

            # Build record map: record_type -> offset from data_start
            records: dict[int, int] = {}
            pos = toc_offset + 20
            for _ in range(num_entries):
                if pos + 12 > len(data):
                    break
                rtype, roffset, _ = struct.unpack_from("<IIi", data, pos)
                records[rtype] = roffset
                pos += 12

            def read_record(offset: int) -> tuple[bytes | None, int]:
                abs_off = data_start + offset
                if abs_off + 8 > len(data):
                    return None, 0
                length, dtype = struct.unpack_from("<II", data, abs_off)
                if abs_off + 8 + length > len(data):
                    return None, 0
                return data[abs_off + 8 : abs_off + 8 + length], dtype

            # 0x2002: volume path string
            volume_path = "/"
            if 0x2002 in records:
                raw, dtype = read_record(records[0x2002])
                if raw and dtype == 0x101:
                    volume_path = raw.decode("utf-8", errors="replace")

            # 0x1004: array of u32 offsets pointing to path component string records
            if 0x1004 not in records:
                return None
            raw, dtype = read_record(records[0x1004])
            if not raw or dtype != 0x601:
                return None

            components = []
            for i in range(0, len(raw), 4):
                if i + 4 > len(raw):
                    break
                comp_off = struct.unpack_from("<I", raw, i)[0]
                comp_raw, comp_dtype = read_record(comp_off)
                if comp_raw and comp_dtype == 0x101:
                    components.append(comp_raw.decode("utf-8", errors="replace"))

            if not components:
                return None

            return volume_path.rstrip("/") + "/" + "/".join(components)
        except Exception:
            return None

    def get_windows_onedrive_paths(self) -> dict[str, str]:
        """Gets all OneDrive folder paths from the Windows registry."""
        onedrive_paths: dict[str, str] = {}
        try:
            reg_key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\OneDrive\Accounts",
            )
            i = 0
            while True:
                try:
                    account_name = winreg.EnumKey(reg_key, i)
                    account_key = winreg.OpenKey(reg_key, account_name)
                    try:
                        user_folder, _ = winreg.QueryValueEx(account_key, "UserFolder")
                        if Path(user_folder).exists():
                            folder_name = Path(user_folder).name
                            onedrive_paths[folder_name] = user_folder
                    except OSError:
                        pass
                    finally:
                        winreg.CloseKey(account_key)
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(reg_key)
        except OSError:
            pass
        return onedrive_paths

    def get_windows_fixed_drives(self) -> list[str]:
        """Gets all available fixed disk drive letters on Windows."""
        DRIVE_FIXED = 3
        drives = []
        try:
            bitmask = windll.kernel32.GetLogicalDrives()
            for letter in string.ascii_uppercase:
                if bitmask & 1:
                    root = f"{letter}:\\"
                    if windll.kernel32.GetDriveTypeW(root) == DRIVE_FIXED:
                        drives.append(root)
                bitmask >>= 1
        except Exception as ex:
            log.error("Failed to get Windows fixed drives : %s", ex, exc_info=True)
        return drives

    def get_windows_mountable_drives(self) -> dict[str, str]:
        """Gets all mountable drives (USB, DVD, external SSD) on Windows."""
        DRIVE_REMOVABLE = 2
        DRIVE_CDROM = 5
        drives: dict[str, str] = {}
        try:
            bitmask = windll.kernel32.GetLogicalDrives()
            for letter in string.ascii_uppercase:
                if bitmask & 1:
                    root = f"{letter}:\\"
                    drive_type = windll.kernel32.GetDriveTypeW(root)
                    if drive_type in (DRIVE_REMOVABLE, DRIVE_CDROM):
                        # Try to get the volume label
                        vol_name_buf = ctypes.create_unicode_buffer(261)
                        result = windll.kernel32.GetVolumeInformationW(
                            root, vol_name_buf, 261, None, None, None, None, 0
                        )
                        vol_label = (
                            vol_name_buf.value if result and vol_name_buf.value else ""
                        )
                        display = (
                            f"{vol_label} ({letter}:)" if vol_label else f"{letter}:\\"
                        )
                        drives[display] = root
                bitmask >>= 1
        except Exception as ex:
            log.error("Failed to get Windows mountable drives : %s", ex, exc_info=True)
        return drives

    def get_windows_pinned_items(self) -> dict[str, str]:
        """Gets Windows File Explorer Quick Access pinned folder paths."""
        pinned: dict[str, str] = {}
        try:
            output = subprocess.check_output(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "(New-Object -ComObject Shell.Application)"
                    ".Namespace('shell:::{679f85cb-0220-4080-b29b-5540cc05aab6}')"
                    ".Items() | Where-Object { $_.IsFolder } "
                    "| ForEach-Object { $_.Path }",
                ],
                stderr=subprocess.DEVNULL,
                timeout=10,
            ).decode("utf-8", errors="replace")
            for line in output.strip().splitlines():
                path = line.strip()
                if path and Path(path).is_dir():
                    pinned[Path(path).name] = path
        except Exception:
            log.error("Failed to get Windows pinned items", exc_info=True)
        return pinned

    def get_windows_network_locations(self) -> dict[str, str]:
        """Gets mapped network drives and UNC network connections on Windows."""
        locations: dict[str, str] = {}
        DRIVE_REMOTE = 4
        try:
            # Mapped network drives (e.g. Z:\)
            bitmask = windll.kernel32.GetLogicalDrives()
            for letter in string.ascii_uppercase:
                if bitmask & 1:
                    root = f"{letter}:\\"
                    if windll.kernel32.GetDriveTypeW(root) == DRIVE_REMOTE:
                        locations[f"{letter}:\\"] = root
                bitmask >>= 1
        except Exception:
            log.error("Failed to get mapped network drives", exc_info=True)
        try:
            # UNC paths from Network Neighborhood via registry
            reg_key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Network",
            )
            i = 0
            while True:
                try:
                    drive_letter = winreg.EnumKey(reg_key, i)
                    drive_key = winreg.OpenKey(reg_key, drive_letter)
                    try:
                        remote_path, _ = winreg.QueryValueEx(drive_key, "RemotePath")
                        if remote_path:
                            display = f"{drive_letter}: ({remote_path})"
                            locations[display] = f"{drive_letter}:\\"
                    except OSError:
                        pass
                    finally:
                        winreg.CloseKey(drive_key)
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(reg_key)
        except OSError:
            pass
        except Exception:
            log.error("Failed to get network locations from registry", exc_info=True)
        return locations

    def panel_locations(self) -> QListWidget:
        locations = QListWidget()
        if MAC:
            self._finder_favorites = self.macos_finder_favorites()
            if self._finder_favorites:
                log.debug(
                    "Using Finder favorites for sidebar: %s",
                    list(self._finder_favorites.keys()),
                )
                # Use Finder favorites as primary, add Home and mounts, deduplicate
                seen: set[str] = set()
                self._add_std_loc_item(locations, "Home")
                seen.add("Home")
                for name in self._finder_favorites:
                    if name not in seen:
                        locations.addItem(name)
                        seen.add(name)
                mount_items: list[str] = []
                for name in self.macos_mount_points():
                    if name not in seen:
                        mount_items.append(name)
                        seen.add(name)
            else:
                log.error("Finder favorites unavailable, using fallback standard paths")
                # Fallback to standard paths if Finder favorites unavailable
                for name in [
                    "Home",
                    "Applications",
                    "Desktop",
                    "Documents",
                    "Downloads",
                    "Pictures",
                    "Music",
                    "Movies",
                ]:
                    self._add_std_loc_item(locations, name)
                mount_items = list(self.macos_mount_points().keys())
            # Add mount locations with a divider
            if mount_items:
                self._add_separator(locations)
                locations.addItems(mount_items)
            # Add macOS Finder tags with a divider
            tags = self.macos_finder_tags()
            if tags:
                self._finder_tags = tags
                self._add_separator(locations)
                locations.addItems(tags)
                log.debug("Added Finder tags to sidebar: %s", tags)
            else:
                self._finder_tags = []
        elif WINDOWS:
            self._windows_fixed_drives = self.get_windows_fixed_drives()
            self._windows_onedrive_paths = self.get_windows_onedrive_paths()
            self._windows_mountable_drives = self.get_windows_mountable_drives()
            self._windows_pinned_items = self.get_windows_pinned_items()
            self._windows_network_locations = self.get_windows_network_locations()
            if self._windows_pinned_items:
                log.debug(
                    "Using Explorer pinned items for sidebar: %s",
                    list(self._windows_pinned_items.keys()),
                )
                seen_win: set[str] = set()
                self._add_std_loc_item(locations, "Home")
                seen_win.add("Home")
                for name in self._windows_pinned_items:
                    if name not in seen_win:
                        locations.addItem(name)
                        seen_win.add(name)
                # Fixed, DVD, and USB drives
                drive_items: list[str] = []
                for name in self._windows_fixed_drives:
                    if name not in seen_win:
                        drive_items.append(name)
                        seen_win.add(name)
                for name in self._windows_mountable_drives:
                    if name not in seen_win:
                        drive_items.append(name)
                        seen_win.add(name)
                # OneDrive locations
                onedrive_items: list[str] = []
                for name in self._windows_onedrive_paths:
                    if name not in seen_win:
                        onedrive_items.append(name)
                        seen_win.add(name)
                if drive_items:
                    self._add_separator(locations)
                    locations.addItems(drive_items)
                if onedrive_items:
                    self._add_separator(locations)
                    locations.addItems(onedrive_items)
                # Add network locations with a divider
                net_items: list[str] = []
                for name in self._windows_network_locations:
                    if name not in seen_win:
                        net_items.append(name)
                        seen_win.add(name)
                if net_items:
                    self._add_separator(locations)
                    locations.addItems(net_items)
            else:
                log.error(
                    "Explorer pinned items unavailable, using fallback standard paths"
                )
                # Standard locations
                for name in [
                    "Home",
                    "Desktop",
                    "Downloads",
                    "Documents",
                    "Pictures",
                    "Music",
                    "Videos",
                ]:
                    self._add_std_loc_item(locations, name)
                # Fixed, DVD, and USB drives
                fallback_drives = [
                    *self._windows_fixed_drives,
                    *self._windows_mountable_drives.keys(),
                ]
                if fallback_drives:
                    self._add_separator(locations)
                    locations.addItems(fallback_drives)
                # OneDrive locations
                fallback_onedrive = list(self._windows_onedrive_paths.keys())
                if fallback_onedrive:
                    self._add_separator(locations)
                    locations.addItems(fallback_onedrive)
                # Network locations
                fallback_network = list(self._windows_network_locations.keys())
                if fallback_network:
                    self._add_separator(locations)
                    locations.addItems(fallback_network)
        elif LINUX:
            for name, path in self.linux_standard_locations().items():
                if Path(path).exists():
                    self._add_std_loc_item(locations, name)
            # Mountable locations
            self._linux_mount_points = self.linux_mount_points()
            if self._linux_mount_points:
                self._add_separator(locations)
                locations.addItems(list(self._linux_mount_points.keys()))

        # Compute width based on longest item text (using bold font for hover/selection)
        bold_font = QFont(locations.font())
        bold_font.setBold(True)
        fm = QFontMetricsF(bold_font)
        max_text_width = 0
        for i in range(locations.count()):
            item = locations.item(i)
            if item:
                text_width = fm.horizontalAdvance(item.text())
                if text_width > max_text_width:
                    max_text_width = text_width
        # Add padding for item padding (8px*2) + list padding (4px*2) + scrollbar margin + extra
        panel_width = int(max_text_width) + 8 * 2 + 4 * 2 + 20
        locations.setFixedWidth(max(80, panel_width))
        locations.setSpacing(3)
        # Enable mouse tracking for hover detection
        locations.setMouseTracking(True)
        self._hovered_item = None
        locations.itemEntered.connect(self._on_item_hover)
        locations.itemSelectionChanged.connect(
            lambda: self._on_selection_changed(locations)
        )
        viewport = locations.viewport()
        if viewport:
            viewport.installEventFilter(self)
        self._locations_widget = locations
        # Handle clicks on the locations list to navigate to the selected location
        locations.itemClicked.connect(self.navigate_to_location)
        return locations

    @classmethod
    def _add_std_loc_item(cls, locations: QListWidget, name: str) -> None:
        """Add a standard location item with translated display text and English key as UserRole data."""
        i18n_key = cls._STD_LOC_KEYS.get(name, name)
        item = QListWidgetItem(Translator.get(i18n_key))
        item.setData(Qt.ItemDataRole.UserRole, name)
        locations.addItem(item)

    @staticmethod
    def _add_separator(locations: QListWidget) -> None:
        """Add a horizontal divider item to the QListWidget."""
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        item.setSizeHint(QSize(0, 12))
        locations.addItem(item)
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        # Pick a contrasting separator color based on background luminance
        bg = locations.palette().color(locations.backgroundRole())
        luminance = 0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()
        color = "#555555" if luminance > 128 else "#aaaaaa"
        separator.setStyleSheet(f"border: none; border-top: 1px solid {color};")
        separator.setObjectName("panelSeparator")
        locations.setItemWidget(item, separator)

    def _set_item_bold(self, item: QListWidgetItem, bold: bool) -> None:
        font = item.font()
        font.setBold(bold)
        item.setFont(font)

    def _on_item_hover(self, item: QListWidgetItem) -> None:
        # Restore previous hovered item (if not selected)
        if self._hovered_item and self._hovered_item is not item:
            if not self._hovered_item.isSelected():
                self._set_item_bold(self._hovered_item, False)
        self._set_item_bold(item, True)
        self._hovered_item = item

    def _on_selection_changed(self, locations: QListWidget) -> None:
        for i in range(locations.count()):
            item = locations.item(i)
            if item:
                self._set_item_bold(item, item.isSelected())

    def eventFilter(self, a0: QObject | None, a1: QEvent | None) -> bool:
        # Clear hover bold when mouse leaves the list viewport
        if (
            hasattr(self, "_locations_widget")
            and a0 is self._locations_widget.viewport()
            and a1 is not None
            and a1.type() == QEvent.Type.Leave
        ):
            if self._hovered_item and not self._hovered_item.isSelected():
                self._set_item_bold(self._hovered_item, False)
            self._hovered_item = None
        return super().eventFilter(a0, a1)
