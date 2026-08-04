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
from typing import Any, Callable, Dict, Optional

from alfresco.auth import OAuth2Auth
from alfresco.exceptions import AuthenticationError

__all__ = ("RefreshingOAuth2Auth",)

log = getLogger(__name__)

# Type alias: called after every successful token mutation
# (initial fetch OR refresh) with a fully-populated dict suitable for
# storing back into the DAO via ``Engine._save_token``.
TokenRefreshCallback = Callable[[Dict[str, Any]], None]


class RefreshingOAuth2Auth(OAuth2Auth):
    """OAuth2Auth that refreshes on 401 and surfaces auth failures cleanly.

    In addition to the parent class behavior, this subclass:

    * Overrides ``_EXPIRY_SKEW`` to refresh 60 seconds before token
      expiry (vendor default is 30s) so slow requests / clock drift
      cannot race the refresh path.
    * Overrides ``_token_request`` to fire an optional callback with
      the freshly-minted token state, so the caller (the Drive engine)
      can persist rotated ``refresh_token`` / ``access_token`` /
      ``expires_at`` values back to the DAO. Without this hook, Keycloak
      refresh-token rotation invalidates the on-disk token immediately
      after the first in-memory refresh, causing the next process
      restart (or auth-object rebuild) to fail with the "grant_type not
      configured" ``RuntimeError``.
    """

    # Override vendor default (30). See class docstring.
    _EXPIRY_SKEW = 60

    # Populated post-construction by ``from_token(..., on_refresh=...)``.
    # Kept as a class-level default so subclass ``__init__`` does not have
    # to mirror the vendor's kwargs.
    _on_refresh: Optional[TokenRefreshCallback] = None

    # -- factory -------------------------------------------------------------

    @classmethod
    def from_token(
        cls,
        access_token: str,
        *,
        on_refresh: Optional[TokenRefreshCallback] = None,
        **kwargs: Any,
    ) -> "RefreshingOAuth2Auth":
        """Same as :meth:`OAuth2Auth.from_token`, but attaches a callback.

        The vendor ``from_token`` builds an instance via ``cls(...)`` with
        a fixed kwarg surface. Rather than re-implement it (and risk
        drifting from the vendor's validation), we delegate then attach
        the callback post-construction.
        """
        inst = super().from_token(access_token, **kwargs)
        # ``super().from_token`` returns ``cls(...)`` (see vendor
        # OAuth2Auth.from_token classmethod), so ``inst`` is guaranteed
        # to be a ``RefreshingOAuth2Auth`` instance.
        inst._on_refresh = on_refresh
        return inst

    # -- persistence hook ----------------------------------------------------

    def _token_request(self, data: dict) -> str:
        """Vendor writes all token mutations through this method.

        We chain to super() (which mutates ``self._access_token``,
        ``self._refresh_token`` and ``self._expires_at``) and then
        publish the new state via the persistence callback if any.
        Runs under ``self._lock`` (held by ``_ensure_token``); keep the
        callback body cheap and swallow any exception so a DAO write
        failure never masquerades as an auth failure.
        """
        access_token = super()._token_request(data)
        callback = self._on_refresh
        if callback is not None:
            try:
                snapshot: Dict[str, Any] = {
                    "access_token": self._access_token,
                    "refresh_token": self._refresh_token,
                    # Persist ``expires_at`` (absolute POSIX ts) rather
                    # than ``expires_in`` — matches what the initial
                    # login persists via ``get_token_dict()``.
                    "expires_at": self._expires_at,
                    "token_url": self.token_url,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                }
                callback(snapshot)
            except Exception:  # noqa: BLE001 — never bubble persistence errors
                log.warning("Could not persist refreshed OAuth2 token", exc_info=True)
        return access_token

    # -- vendor-behavior overrides ------------------------------------------

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
