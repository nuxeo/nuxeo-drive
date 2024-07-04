"""Notification class for Tasks Management Feature"""

from nxdrive.translator import Translator

from ..notification import Notification


class DisplayPendingTask(Notification):
    """Display a notification for pending tasks"""

    def __init__(
        self,
        engine_uid: str,
        remote_ref: str,
        remote_path: str,
        notification_title: str,
        /,
    ) -> None:
        values = [remote_path]
        super().__init__(
            uid=notification_title,
            title=(" ".join(notification_title.split("_"))).title(),
            description=Translator.get(notification_title, values=values),
            level=Notification.LEVEL_INFO,
            flags=(
                Notification.FLAG_PERSISTENT
                | Notification.FLAG_BUBBLE
                | Notification.FLAG_ACTIONABLE
                | Notification.FLAG_DISCARD_ON_TRIGGER
                | Notification.FLAG_REMOVE_ON_DISCARD
            ),
            action="display_pending_task",
            action_args=(
                engine_uid,
                remote_ref,
                remote_path,
            ),
        )
