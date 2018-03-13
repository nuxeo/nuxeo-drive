# coding: utf-8
from PyQt4.QtCore import Qt, pyqtSlot

from .dialog import WebDialog, WebDriveApi


class WebModalApi(WebDriveApi):
    @pyqtSlot(str)
    def result(self, button_id):
        self.dialog.set_result(button_id)

    def _json_default(self, obj):
        if isinstance(obj, WebModalButton):
            return self._export_button(obj)
        return super(WebModalApi, self)._json_default(obj)

    @staticmethod
    def _export_button(obj):
        return {
            'uid': obj.uid,
            'label': obj._label,
            'style': obj._style,
        }

    @pyqtSlot(result=str)
    def get_message(self):
        return self.dialog.get_message()

    @pyqtSlot(result=str)
    def get_buttons(self):
        res = []
        for button in self.dialog.get_buttons().itervalues():
            res.append(button)
        return self._json(res)


class WebModalButton(object):
    # for style see bootstrap
    def __init__(self, uid, label, style="default"):
        self.uid = uid
        self._label = label
        self._style = style


class WebModal(WebDialog):

    def __init__(self, application, message, page="modal.html", title="Nuxeo Drive", api=None, buttons=None):
        if api is None:
            api = WebModalApi(application)
        super(WebModal, self).__init__(application, page=page, title=title, api=api)
        self.setSizeGripEnabled(False)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        self._buttons = dict()
        self._message = message
        self._result = ""
        if buttons is not None:
            for button in buttons:
                self._buttons[button.uid] = button

    def get_message(self):
        return self._message

    def get_buttons(self):
        return self._buttons

    def set_result(self, res):
        self._result = res
        self.accept()

    def get_result(self):
        return self._result

    def add_button(self, uid, label, style="default"):
        self._buttons[uid] = WebModalButton(uid, label, style)

    def exec_(self):
        super(WebModal, self).exec_()
        return self.get_result()
