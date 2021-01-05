""" Python integration macOS notification center. """
from typing import TYPE_CHECKING, Dict

from CoreServices import (
    NSBundle,
    NSMutableDictionary,
    NSObject,
    NSUserNotification,
    NSUserNotificationCenter,
)

from ...constants import BUNDLE_IDENTIFIER

if TYPE_CHECKING:
    from ...manager import Manager  # noqa

__all__ = ("NotificationDelegator", "notify", "setup_delegator")


class NotificationDelegator(NSObject):

    manager: "Manager"

    def __init__(self) -> None:
        info_dict = NSBundle.mainBundle().infoDictionary()
        if "CFBundleIdentifier" not in info_dict:
            info_dict["CFBundleIdentifier"] = BUNDLE_IDENTIFIER

    def userNotificationCenter_didActivateNotification_(
        self, center: NSUserNotificationCenter, notification: NSMutableDictionary, /
    ) -> None:
        info = notification.userInfo()
        if info and "uuid" not in info:
            return
        notifications = self.manager.notification_service.get_notifications()
        if (
            info["uuid"] not in notifications
            or notifications[info["uuid"]].is_discard_on_trigger()
        ):
            center.removeDeliveredNotification_(notification)
        self.manager.notification_service.trigger_notification(info["uuid"])

    def userNotificationCenter_shouldPresentNotification_(
        self, center: object, notification: object, /
    ) -> bool:
        return True


def setup_delegator(delegator: NotificationDelegator = None, /) -> None:
    center = NSUserNotificationCenter.defaultUserNotificationCenter()
    if delegator is not None and center is not None:
        center.setDelegate_(delegator)


def notify(
    title: str,
    subtitle: str,
    info_text: str,
    /,
    *,
    delay: int = 0,
    sound: bool = False,
    user_info: Dict[str, str] = None,
) -> None:
    """Python method to show a desktop notification on Mountain Lion. Where:
    title: Title of notification
    subtitle: Subtitle of notification
    info_text: Informative text of notification
    delay: Delay (in seconds) before showing the notification
    sound: Play the default notification sound
    userInfo: a dictionary that can be used to handle clicks in your
              app's applicationDidFinishLaunching:aNotification method
    """
    notification = NSUserNotification.alloc().init()
    notification.setTitle_(title)
    notification.setSubtitle_(subtitle)
    notification.setInformativeText_(info_text)
    user_info = user_info or {}
    notification.setUserInfo_(user_info)
    if sound:
        notification.setSoundName_("NSUserNotificationDefaultSoundName")
    center = NSUserNotificationCenter.defaultUserNotificationCenter()
    if center is not None:
        center.deliverNotification_(notification)
