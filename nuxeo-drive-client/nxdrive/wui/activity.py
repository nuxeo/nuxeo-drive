# coding: utf-8
from nxdrive.wui.dialog import WebDialog
from nxdrive.wui.translator import Translator


class WebActivityDialog(WebDialog):
    def __init__(self, application):
        super(WebActivityDialog, self).__init__(
            application,
            'activity.html',
            title=Translator.get('ACTIVITY_WINDOW_TITLE'),
        )
