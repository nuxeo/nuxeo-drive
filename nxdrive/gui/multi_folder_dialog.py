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

from nxdrive.qt.imports import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDir,
    QFileSystemModel,
    QFont,
    QFontMetricsF,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSizePolicy,
    Qt,
    QTreeView,
    QVBoxLayout,
)

from ..constants import LINUX, MAC, WINDOWS

if WINDOWS:
    import winreg
    from ctypes import windll

log = getLogger(__name__)


class CenteredHeaderFileSystemModel(QFileSystemModel):
    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignCenter
        return super().headerData(section, orientation, role)


class MultiFolderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Files/Folders")

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
        self.showHidden.setText("Show Hidden")
        self.showHidden.checkStateChanged.connect(self.show_hidden_files)
        # Home button
        self.btnHome = QPushButton()
        self.btnHome.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.btnHome.setText("Home")
        self.btnHome.clicked.connect(self.go_home)
        # Up button
        self.btnUp = QPushButton()
        self.btnUp.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.btnUp.setText("Go Up")
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
        self.label = QLabel("Select files/folders:")
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
            ok_button.setText("Add")
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button:
            cancel_button.setText("Cancel")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        # Adding Add/Cancel buttons to the layout
        bottom_layout.addWidget(buttons)
        layout.addLayout(bottom_layout)

    def selected_paths(self) -> list[str]:
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

    def path_changed(self) -> None:
        path = Path(self.path_bar.text())
        if path.exists():
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

    def load_directory(self, index):
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

    def navigate_to_location(self, item) -> None:
        location = item.text()
        # MacOS paths
        if MAC:
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
                case loc if loc in self.get_windows_fixed_drives():
                    self.path_bar.setText(loc)
                case loc if loc in self.get_windows_onedrive_paths():
                    self.path_bar.setText(self.get_windows_onedrive_paths()[loc])
        # Linux paths

    def macos_mount_points(self) -> dict[str, str]:
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
                    log.debug("Failed to read %s", sfl_path, exc_info=True)
                break
        return favorites

    @staticmethod
    def _parse_sfl_file(sfl_path: Path) -> dict[str, str]:
        """Parse an SFL/SFL2/SFL3/SFL4 file and return {name: path} for valid favorites."""
        favorites = {}
        with open(sfl_path, "rb") as f:
            plist_data = plistlib.load(f)

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
        bitmask = windll.kernel32.GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                root = f"{letter}:\\"
                if windll.kernel32.GetDriveTypeW(root) == DRIVE_FIXED:
                    drives.append(root)
            bitmask >>= 1
        return drives

    def panel_locations(self) -> QListWidget:
        locations = QListWidget()
        if MAC:
            self._finder_favorites = self.macos_finder_favorites()
            if self._finder_favorites:
                # Use Finder favorites as primary, add Home and mounts, deduplicate
                seen: set[str] = set()
                items: list[str] = ["Home"]
                seen.add("Home")
                for name in self._finder_favorites:
                    if name not in seen:
                        items.append(name)
                        seen.add(name)
                for name in self.macos_mount_points():
                    if name not in seen:
                        items.append(name)
                        seen.add(name)
            else:
                # Fallback to standard paths if Finder favorites unavailable
                items = [
                    "Home",
                    "Applications",
                    "Desktop",
                    "Documents",
                    "Downloads",
                    "Pictures",
                    "Music",
                    "Movies",
                    *self.macos_mount_points().keys(),
                ]
            locations.addItems(items)
        elif WINDOWS:
            locations.addItems(
                [
                    "Home",
                    "Desktop",
                    "Downloads",
                    "Documents",
                    "Pictures",
                    "Music",
                    "Videos",
                    *self.get_windows_fixed_drives(),
                    *self.get_windows_onedrive_paths().keys(),
                ]
            )
        elif LINUX:
            locations.addItems(["Home", "Desktop", "Documents", "Downloads"])

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

    def _set_item_bold(self, item, bold: bool) -> None:
        font = item.font()
        font.setBold(bold)
        item.setFont(font)

    def _on_item_hover(self, item) -> None:
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

    def eventFilter(self, a0, a1) -> bool:
        # Clear hover bold when mouse leaves the list viewport
        if (
            hasattr(self, "_locations_widget")
            and a0 is self._locations_widget.viewport()
            and a1.type() == a1.Type.Leave
        ):
            if self._hovered_item and not self._hovered_item.isSelected():
                self._set_item_bold(self._hovered_item, False)
            self._hovered_item = None
        return super().eventFilter(a0, a1)
