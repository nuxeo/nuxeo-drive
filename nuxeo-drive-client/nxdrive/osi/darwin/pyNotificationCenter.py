# coding: utf-8
""" Python integration with Mountain Lion's notification center. """

import objc

NSUserNotification = objc.lookUpClass('NSUserNotification')
NSUserNotificationCenter = objc.lookUpClass('NSUserNotificationCenter')
NSObject = objc.lookUpClass('NSObject')


class NotificationDelegator(NSObject):

    def __init__(self):
        self._manager = None

    def userNotificationCenter_didActivateNotification_(self, center, notification):
        info = notification.userInfo()
        if "uuid" not in info or self._manager is None:
            return
        notifications = self._manager.notification_service.get_notifications()
        if info['uuid'] not in notifications or (info['uuid'] in notifications and
                                                 notifications[info['uuid']].is_discard_on_trigger()):
            center.removeDeliveredNotification_(notification)
        self._manager.notification_service.trigger_notification(info["uuid"])

    def userNotificationCenter_shouldPresentNotification_(self, center, notification):
        return True


def setup_delegator(delegator=None):
    center = NSUserNotificationCenter.defaultUserNotificationCenter()
    if delegator is not None and center is not None:
        center.setDelegate_(delegator)


def notify(title, subtitle, info_text, delay=0, sound=False, user_info=None):
    """ Python method to show a desktop notification on Mountain Lion. Where:
        title: Title of notification
        subtitle: Subtitle of notification
        info_text: Informative text of notification
        delay: Delay (in seconds) before showing the notification
        sound: Play the default notification sound
        userInfo: a dictionary that can be used to handle clicks in your
                  app's applicationDidFinishLaunching:aNotification method
    """
    if user_info is None:
        user_info = {}
    notification = NSUserNotification.alloc().init()
    notification.setTitle_(title)
    notification.setSubtitle_(subtitle)
    notification.setInformativeText_(info_text)
    notification.setUserInfo_(user_info)
    if sound:
        notification.setSoundName_('NSUserNotificationDefaultSoundName')
    center = NSUserNotificationCenter.defaultUserNotificationCenter()
    if center is not None:
        center.deliverNotification_(notification)
