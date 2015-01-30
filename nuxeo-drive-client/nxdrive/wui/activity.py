'''
Created on 28 janv. 2015

@author: Remi Cattiau
'''
from nxdrive.wui.dialog import WebDialog

class WebActivityDialog(WebDialog):
    def __init__(self, application):
        super(WebActivityDialog, self).__init__(application, "activity.html", title="Nuxeo Drive - Status")
