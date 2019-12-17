# coding: utf-8
"""
The Direct Transfer feature.

What: threaded runner.
"""
from threading import Thread
from typing import Any, Optional


class Runner(Thread):
    """Simple runner used for every single upload.
    Any exception will be forwarded to the caller via the .error attribute.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Simple init to declare .error that is used to communicate eventual exceptions to the caller."""
        super().__init__(*args, **kwargs)
        self.error: Optional[Exception] = None

    def run(self) -> None:
        """Catch any error and store it inside the .error attribute instead of throwing it."""
        try:
            super().run()
        except Exception as exc:
            self.error = exc
