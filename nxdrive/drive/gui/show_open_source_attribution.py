#
# © 2012-2026 Hyland.
# All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
#

"""
Create Open Source Attribution Notice dialog box
"""

from logging import getLogger

from nxdrive.drive.translator import Translator

from ..qt.imports import (
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


class Open_Source_Attribution(QDialog):

    def __init__(self, server_type: str):
        super().__init__()

        self.server_type = server_type.upper()

        self.setWindowTitle(Translator.get("OPEN_SOURCE_ATTRIBUTION"))

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        text_content = QTextEdit()
        text_document = self.fetch_document_text()
        if text_document:
            text_content.setDocument(text_document)
        text_content.setReadOnly(True)
        text_content.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        text_content.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        scroll_area.setWidget(text_content)

        ok_button = QPushButton()
        ok_button.setText(Translator.get("BUTTON_OK"))
        ok_button.setFixedWidth(70)
        ok_button.clicked.connect(self.accept)

        button_layout = QHBoxLayout()
        button_layout.addWidget(ok_button, alignment=Qt.AlignmentFlag.AlignHCenter)

        layout = QVBoxLayout()
        layout.addWidget(scroll_area)
        layout.addLayout(button_layout)

        self.setLayout(layout)
        self.setMinimumSize(500, 500)

        self.show()

    def fetch_document_text(self) -> QTextDocument | None:
        """Fetch the attribution text"""

        from ..utils import find_resource

        file_path = find_resource(
            "LICENSES", file=f"{self.server_type}_OPEN_SOURCE_ATTRIBUTION.txt"
        )
        content = None
        try:
            with open(file_path, mode="r", encoding="utf-8") as f:
                content = QTextDocument(f.read().strip())
        except Exception as e:
            log.error(
                f"Unable to read {self.server_type}_OPEN_SOURCE_ATTRIBUTION.txt : {e}"
            )
        finally:
            return content


def get_open_source_attribution_console_message(server_type: str = "Nuxeo") -> None:
    """Prints the open source attribution text in console"""

    from ..utils import find_resource

    file_path = find_resource(
        "LICENSES", file=f"{server_type}_OPEN_SOURCE_ATTRIBUTION.txt"
    )
    content = None
    try:
        with open(file_path, mode="r", encoding="utf-8") as f:
            content = f.read().strip()
    except Exception as e:
        log.error(f"Unable to read {server_type}_OPEN_SOURCE_ATTRIBUTION.txt : {e}")
        return

    if content:
        print(content)
        print()  # Just a new line break
        print("Enter any key to proceed:")
        input()
    else:
        # If content is empty, we just log a warning
        # This notice is not mandatory, so it should not block execution
        log.warning("No content in Open Source Attribution text")
