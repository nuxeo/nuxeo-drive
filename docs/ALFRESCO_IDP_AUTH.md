# Nuxeo Drive vs Alfresco: IdP-Only Authorization Differences

## Scope

This note summarizes the differences between authorizing Nuxeo Drive against:

- a **native Nuxeo server** using an external identity provider (IdP), and
- an **Alfresco repository** through the `AlfrescoRemote` adapter, also using an external IdP.

The focus is on **desktop-client authorization** after the user authenticates with the IdP.

---

## Executive Summary

**Nuxeo + IdP** is a native fit for Nuxeo Drive.

**Alfresco + IdP** is feasible, but only if the adapter can convert IdP authentication into credentials accepted by:

- Alfresco Public REST API (`/public/alfresco/versions/1`)
- Alfresco Sync Service (`/private/alfresco/versions/1`), if delta synchronization is enabled

In practice, the main difference is:

- with **Nuxeo**, the client already understands the server-side auth model it is talking to;
- with **Alfresco**, the adapter must bridge the IdP result into an Alfresco-compatible API session or token.

---

## High-Level Comparison

| Area | Nuxeo + IdP | Alfresco + IdP |
|---|---|---|
| Desktop client support | Native Nuxeo Drive behavior | Adapter-driven, not native |
| Post-login auth model | Nuxeo-native token/session model already expected by Drive | Must be translated into ACS-compatible token/session |
| API target after login | Nuxeo endpoints only | Alfresco Public REST + possibly Sync Service |
| Browser SSO reuse | Usually aligned with Drive expectations | Often insufficient by itself for API calls |
| Extra integration work | Low | Medium to High |
| Production risk | Lower | Higher, especially around token lifecycle and delta sync |

---

## What Happens in the Nuxeo Case

Typical Nuxeo Drive authorization with an external IdP works like this:

1. User starts account binding from the client.
2. Drive opens a browser-based authentication flow.
3. User authenticates against the IdP.
4. Nuxeo converts that authenticated identity into a session/token model understood by Drive.
5. Drive continues using Nuxeo-native APIs with Nuxeo-native authorization semantics.

### Why this is simpler

Because Nuxeo Drive was designed for Nuxeo, the client already expects:

- Nuxeo-style endpoint discovery
- Nuxeo-style auth/session handling
- Nuxeo-specific remote operations
- Nuxeo server configuration responses

So the IdP is mostly an **authentication front door**, while Drive still talks to Nuxeo in a form it already supports.

---

## What Happens in the Alfresco Case

With Alfresco, the user may also authenticate through the same IdP, but the desktop client must still obtain authorization that works for Alfresco APIs.

That means the adapter must ensure that one of the following is true:

1. **Alfresco accepts the IdP bearer token directly**
2. **The IdP login can be exchanged for an Alfresco session/ticket**
3. **A trusted reverse proxy provides a reusable authenticated API session**

If none of these is true, successful browser login does **not** guarantee that Drive can call Alfresco APIs.

### Why this is harder

Nuxeo Drive does not natively speak Alfresco auth semantics.

The adapter therefore has to solve:

- token/session capture after IdP login
- token storage in the desktop client
- token refresh
- propagation of auth headers to every ACS API call
- compatibility with both content APIs and Sync Service APIs

---

## The Main Architectural Difference

### Nuxeo

The chain is effectively:

`IdP -> Nuxeo auth bridge -> Nuxeo Drive-compatible session/token -> Nuxeo APIs`

### Alfresco

The chain becomes:

`IdP -> custom adapter auth bridge -> Alfresco-compatible session/token -> Alfresco REST APIs (+ Sync Service)`

That extra "custom adapter auth bridge" is the core difference.

---

## Why Browser SSO Alone Is Not Enough for Alfresco

In browser-based SSO, the user may appear fully logged in to Alfresco, but the desktop client still needs a transportable auth mechanism for HTTP requests.

Examples of what the client needs:

- `Authorization: Bearer <token>`
- a reusable ACS session/ticket
- cookies that remain valid for API requests initiated by the desktop process

If browser SSO only establishes a browser-local session, Drive cannot automatically reuse it.

---

## Impact on Nuxeo Drive Integration Work

For the current Alfresco adapter, IdP-only support affects at least these layers:

### 1. Account binding / UI flow

The client must support:

- browser-based sign-in
- callback/token capture
- user feedback for expired or invalid sessions

### 2. `AlfrescoClient`

The low-level HTTP client must consistently send:

- bearer token headers, or
- ACS ticket/session credentials

for all repository calls.

### 3. `AlfrescoRemote`

The adapter must support:

- token refresh and replacement
- failure handling for 401/403
- possibly different auth rules between Public REST and Sync Service

### 4. Delta sync integration

If Sync Service is used, the same identity must also authorize:

- subscription creation
- sync start
- sync polling
- sync cancellation

This is stricter than simply listing or uploading files.

---

## Feasibility Assessment for IdP-Only Alfresco Auth

## Feasible when

- Alfresco accepts **OIDC/OAuth2 bearer tokens** directly for API access, or
- the deployment exposes a documented **token exchange** from IdP auth to ACS API session/ticket, or
- both Public REST and Sync Service are fronted by the same trusted auth gateway.

## Risky when

- only browser-based SSO is available
- the client cannot obtain an API-usable token
- Public REST and Sync Service do not accept the same auth mechanism
- tokens are short-lived and there is no refresh path available to the client

## Not production-ready when

- the user can log in through the browser but the adapter cannot reuse that identity for API calls
- Sync Service requires a different auth path than repository CRUD operations

---

## Recommended Target Architecture

For the Alfresco adapter, the cleanest IdP-only model is:

1. Use **OIDC/OAuth2 browser login**
2. Capture an **access token** and, if possible, a **refresh token**
3. Store the token set securely in the desktop client
4. Send `Authorization: Bearer ...` from `AlfrescoClient`
5. Verify that the same token works for:
   - `/public/alfresco/versions/1/...`
   - `/private/alfresco/versions/1/...`
6. Refresh tokens automatically before expiry

This gives the closest user experience to native Nuxeo-style sign-in while remaining compatible with ACS APIs.

---

## Practical Conclusion

### Nuxeo + IdP

- mostly a native and expected deployment shape for Nuxeo Drive
- lower adaptation cost
- fewer moving parts in the desktop client

### Alfresco + IdP

- feasible, but not automatic
- requires explicit auth-bridge logic in the adapter
- must validate end-to-end authorization for both content CRUD and Sync Service

**Bottom line:**

IdP-only authorization is substantially easier with native Nuxeo than with Alfresco-through-adapter, because in the Alfresco case the desktop client must actively bridge the IdP outcome into ACS-compatible API credentials.

---

## Recommended Next Steps

1. Confirm which IdP protocol the Alfresco deployment uses:
   - OIDC / OAuth2
   - SAML
   - reverse-proxy SSO
2. Confirm whether ACS Public REST accepts bearer tokens directly.
3. Confirm whether Sync Service accepts the same auth headers.
4. Add adapter-level token refresh support if token expiry is short.
5. Add explicit UI messaging for:
   - expired session
   - re-login required
   - sync service unauthorized
