import subprocess

from gi.repository import Nautilus, GObject


class ExampleMenuProvider(GObject.GObject, Nautilus.MenuProvider):

    def __init__(self):
        pass

    def get_file_items(self, window, files):
        main_item = Nautilus.MenuItem(name='Nautilus::nuxe_drive',
                                      label='Nuxeo Drive',
                                      tip='Nuxeo Drive')
        submenu = Nautilus.Menu()
        submenu_item = Nautilus.MenuItem(name='Nautilus::metadata_edit',
                                         label='Edit metadata',
                                         tip='Edit metadata')
        submenu.append_item(submenu_item)
        submenu_item.connect("activate", self.menu_activate_cb, files)
        main_item.set_submenu(submenu)
        return main_item,

    def menu_activate_cb(self, menu, files):
        """Called when the user selects the menu."""
        self.drive_exec(['metadata', '--file', "http://localhost:8080/nuxeo"])

    def drive_exec(self, cmds):
        # add the ndrive command !
        cmds.insert(0, "ndrive")
        # print "Executing ndrive command: " + str(cmds)
        p = subprocess.Popen(cmds, stdout=subprocess.PIPE)
        result, _ = p.communicate()
        # print "Result = " + result
        return eval(result)
