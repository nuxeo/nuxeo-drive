"""
Create Open Source Attribution Notice dialog box
"""

from logging import getLogger

from ..qt.imports import (
    QDialog,
    QPushButton,
    QScrollArea,
    QSizePolicy,
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

        self.setWindowTitle("OPEN SOURCE ATTRIBUTION NOTICE")

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
        ok_button.setText("OK")
        ok_button.clicked.connect(self.accept)

        layout = QVBoxLayout()
        layout.addWidget(scroll_area)
        layout.addWidget(ok_button)

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
            with open(file_path, mode="r") as f:
                content = QTextDocument(f.read().strip())
        except Exception as e:
            log.error(
                f"Unable to read {self.server_type}_OPEN_SOURCE_ATTRIBUTION.txt : {e}"
            )
        finally:
            return content
