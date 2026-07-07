"""Refresh-aware OAuth2 auth handler for Alfresco Content Services.

The vendor :class:`alfresco.auth.OAuth2Auth`, when constructed via
:meth:`OAuth2Auth.from_token` (our re-hydration path), does **not** set
a ``grant_type`` — so its built-in ``fetch_token()`` fallback cannot
re-authenticate from scratch. That has two consequences:

1. The library's 401 retry path in ``alfresco.api.base._raw()`` calls
   ``auth.invalidate()`` **before** attempting to refresh. The default
   ``invalidate()`` wipes both the access **and** the refresh token, so
   the subsequent retry cannot possibly succeed with a re-hydrated auth.

2. When the refresh token itself is exhausted, the vendor's ``refresh()``
   falls back to ``fetch_token()`` which raises a bare ``RuntimeError``.
   That surfaces to the Drive engine as an unclassified error rather
   than an :class:`alfresco.exceptions.AuthenticationError`, so the
   ``invalidAuthentication`` signal (which prompts the user to re-login)
   never fires.

:class:`RefreshingOAuth2Auth` fixes both by overriding ``invalidate()``
and ``refresh()`` so that:

* ``invalidate()`` attempts a refresh first; on success the retry uses
  the new access token. On failure it wipes and raises so the vendor
  retry loop stops and the 401 propagates.
* ``refresh()`` translates a total refresh failure into
  :class:`AuthenticationError`, which the Drive engine already handles
  via its ``set_invalid_credentials()`` path.
"""

from logging import getLogger

from alfresco.auth import OAuth2Auth
from alfresco.exceptions import AuthenticationError

__all__ = ("RefreshingOAuth2Auth",)

log = getLogger(__name__)


class RefreshingOAuth2Auth(OAuth2Auth):
    """OAuth2Auth that refreshes on 401 and surfaces auth failures cleanly."""

    def invalidate(self) -> None:
        """Called by the API base on 401 — try refresh first, else fail loudly.

        Returning normally tells :meth:`alfresco.api.base._raw` to retry the
        request. Raising tells it to give up (the 401 will then propagate
        as :class:`AuthenticationError`).
        """
        if self._refresh_token:
            try:
                self.refresh()
                log.debug("OAuth2 access token refreshed after 401")
                return
            except Exception as exc:  # noqa: BLE001 — we re-raise below
                log.warning("OAuth2 refresh failed after 401: %s", exc)
        # No refresh token, or refresh failed — wipe and stop the retry loop.
        super().invalidate()
        raise AuthenticationError("OAuth2 refresh failed — re-authentication required")

    def refresh(self) -> str:
        """Refresh with a clean :class:`AuthenticationError` on total failure.

        The vendor implementation falls back to ``fetch_token()`` when the
        refresh token is exhausted, but ``fetch_token()`` requires a
        ``grant_type`` we cannot set from a re-hydrated auth. Translate the
        resulting ``RuntimeError`` into an ``AuthenticationError`` so the
        engine watcher's existing exception handler fires.
        """
        try:
            return super().refresh()
        except RuntimeError as exc:
            raise AuthenticationError(str(exc)) from exc
