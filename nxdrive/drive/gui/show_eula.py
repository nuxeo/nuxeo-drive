"""
Open End User License Agreement dialog box
"""

from logging import getLogger

from PySide6.QtGui import QKeyEvent

from nxdrive.drive.translator import Translator
from nxdrive.drive.utils import find_resource

from ..qt.imports import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    Qt,
    QTextDocument,
    QTextEdit,
    QTextOption,
    QVBoxLayout,
)

log = getLogger(__name__)


class EULA_Dialog(QDialog):
    """Custom EULA Dialog with overriden closeEvent"""

    def __init__(self, f: Qt.WindowType | None = None):
        if not f:
            super().__init__()
        else:
            super().__init__(f=f)

    def closeEvent(self, event) -> None:
        """Overriding close event of QDialog and ignoring it"""

        event.ignore()

    def keyPressEvent(self, arg__1: QKeyEvent) -> None:
        if arg__1.key() == Qt.Key.Key_Escape:
            arg__1.ignore()
            return
        return super().keyPressEvent(arg__1)


class EULA_Scroller(QScrollArea):
    """Fetch a scrollable area with EULA text"""

    def __init__(self, server_type: str):
        super().__init__()

        self.setWidgetResizable(True)

        eula_text = QTextEdit()
        license_doc = fetch_license(server_type)

        if not license_doc:
            raise Exception("License doc not found")

        eula_text.setDocument(license_doc)  # type: ignore
        eula_text.setReadOnly(True)
        eula_text.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        eula_text.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.setWidget(eula_text)


class EULA(QApplication):

    def __init__(self, server_type: str = "Nuxeo") -> None:
        super().__init__([])

        self.server_type = server_type.upper()
        self._init_translator()

        # Needed to stop EULA Application from closing
        # until the Open Source Attribution notice is shown
        self.setQuitOnLastWindowClosed(False)

        dialog = EULA_Dialog(
            f=Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )

        dialog.setWindowTitle(Translator.get("EULA_WINDOW_TITLE"))
        dialog.setMinimumSize(700, 500)

        try:
            self.eula_scroller = EULA_Scroller(self.server_type)
        except Exception as e:
            log.error(e)
            self.exit(1)

        main_layout = QVBoxLayout()

        button_accept = QPushButton()
        button_accept.setText(Translator.get("BUTTON_ACCEPT"))
        button_accept.clicked.connect(self.accept_eula)
        button_reject = QPushButton()
        button_reject.setText(Translator.get("BUTTON_REJECT"))
        button_reject.clicked.connect(self.reject_eula)
        button_layout = QHBoxLayout()
        button_layout.addWidget(button_accept, alignment=Qt.AlignmentFlag.AlignHCenter)
        button_layout.addWidget(button_reject, alignment=Qt.AlignmentFlag.AlignHCenter)

        main_layout.addWidget(self.eula_scroller)
        main_layout.addLayout(button_layout)

        dialog.setLayout(main_layout)

        self.eula_dialog = dialog

        self.eula_dialog.show()

    def accept_eula(self) -> None:
        """Called on EULA Accept"""

        from .show_open_source_attribution import Open_Source_Attribution

        self.eula_dialog.accept()
        try:
            attribution_notice = Open_Source_Attribution(self.server_type)
            attribution_notice.exec()
        except Exception as e:
            log.warning(f"Cannot launch open source attribution notice : {e}")
        finally:
            self.eula_dialog.deleteLater()
            self.eula_scroller.deleteLater()
            self.removeTranslator(self.translator_singleton)
            self.exit(0)

    def _init_translator(self) -> None:
        """Initialize a translator singleton"""

        import locale

        locale.setlocale(locale.LC_ALL, "")
        locale_info = locale.getlocale()
        user_lang = (
            locale_info[0].split("_")[0]
            if locale_info and locale_info[0]
            else "English"
        )
        lang_code = (
            locale.normalize(user_lang)[:2].lower()
            if locale.normalize(user_lang)
            else "en"
        )
        Translator(find_resource("i18n"), lang=lang_code)
        self.translator_singleton = Translator.singleton
        self.installTranslator(self.translator_singleton)

    def reject_eula(self) -> None:
        """Called on EULA Reject"""
        self.eula_dialog.deleteLater()
        self.eula_scroller.deleteLater()
        self.removeTranslator(self.translator_singleton)
        self.exit(1)


def fetch_license(server_type: str) -> QTextDocument | None:
    """Fetch the corresponding license text"""

    from ..utils import find_resource

    file_path = find_resource("LICENSES", file=f"{server_type}_EULA.txt")
    content = None
    try:
        with open(file_path, mode="r") as f:
            content = QTextDocument(f.read().strip())
    except Exception as e:
        log.error(f"Unable to read {server_type}_EULA.txt : {e}")
    finally:
        return content


def get_eula_application(server_type: str = "Nuxeo") -> QApplication:
    return EULA(server_type)


# Needed by api.show_eula_dialog
def get_eula_dialog(server_type: str = "Nuxeo") -> QDialog:
    """Generate a simple dialog box with EULA text"""

    dialog = EULA_Dialog(
        f=Qt.WindowType.CustomizeWindowHint
        | Qt.WindowType.WindowTitleHint
        | Qt.WindowType.WindowMinimizeButtonHint
        | Qt.WindowType.WindowMaximizeButtonHint
        | Qt.WindowType.WindowCloseButtonHint
    )
    scroller = EULA_Scroller(server_type)

    ok_button = QPushButton()
    ok_button.setText(Translator.get("BUTTON_OK"))
    ok_button.setFixedWidth(70)
    ok_button.clicked.connect(dialog.accept)

    button_layout = QHBoxLayout()
    button_layout.addWidget(ok_button, alignment=Qt.AlignmentFlag.AlignHCenter)

    layout = QVBoxLayout()
    layout.addWidget(scroller)
    layout.addLayout(button_layout)

    dialog.setLayout(layout)
    dialog.setMinimumSize(500, 500)

    return dialog
