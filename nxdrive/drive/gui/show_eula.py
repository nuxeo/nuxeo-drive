"""
Open End User License Agreement dialog box
"""

from logging import getLogger

from PySide6.QtGui import QKeyEvent

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

    def __init__(self, f: Qt.WindowType):
        super().__init__(f=f)

    def closeEvent(self, event) -> None:
        """Overriding close event of QDialog and ignoring it"""

        event.ignore()

    def keyPressEvent(self, arg__1: QKeyEvent) -> None:
        if arg__1.key() == Qt.Key.Key_Escape:
            arg__1.ignore()
            return
        return super().keyPressEvent(arg__1)


class EULA(QApplication):

    def __init__(self, server_type: str = "Nuxeo") -> None:
        super().__init__([])

        self.server_type = server_type.upper()

        # Needed to stop EULA Application from closing
        # until the Open Source Attribution notice is shown
        self.setQuitOnLastWindowClosed(False)

        dialog = EULA_Dialog(
            f=Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        dialog.setWindowTitle("End User License Agreement")
        dialog.setMinimumSize(700, 500)

        main_layout = QVBoxLayout()

        eula_scroller = QScrollArea()
        eula_scroller.setWidgetResizable(True)

        eula_text = QTextEdit()
        license_doc = self.fetch_license()

        if not license_doc:
            self.exit(1)

        eula_text.setDocument(license_doc)  # type: ignore
        eula_text.setReadOnly(True)
        eula_text.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        eula_text.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        eula_scroller.setWidget(eula_text)

        button_accept = QPushButton()
        button_accept.setText("Accept")
        button_accept.clicked.connect(self.accept_eula)
        button_reject = QPushButton()
        button_reject.setText("Reject")
        button_reject.clicked.connect(self.reject_eula)
        button_layout = QHBoxLayout()
        button_layout.addWidget(button_accept, alignment=Qt.AlignmentFlag.AlignHCenter)
        button_layout.addWidget(button_reject, alignment=Qt.AlignmentFlag.AlignHCenter)

        main_layout.addWidget(eula_scroller)
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
            self.exit(0)

    def fetch_license(self) -> QTextDocument | None:
        """Fetch the corresponding license text"""

        from ..utils import find_resource

        file_path = find_resource("LICENSES", file=f"{self.server_type}_EULA.txt")
        content = None
        try:
            with open(file_path, mode="r") as f:
                content = QTextDocument(f.read().strip())
        except Exception as e:
            log.error(f"Unable to read {self.server_type}_EULA.txt : {e}")
        finally:
            return content

    def reject_eula(self) -> None:
        """Called on EULA Reject"""
        self.exit(1)


def get_eula_application(server_type: str = "Nuxeo") -> QApplication:
    return EULA(server_type)
