# Authentication — SCOUT

SCOUT supports two authentication methods that can be used independently or together:

- **Local login** — traditional username + password, validated against Django's auth backend
- **OIDC / OAuth 2.0** — federated login via one or more external identity providers (e.g. Authentik, Okta, Google)

---

## Table of Contents

1. [Local Login](#local-login)
2. [OIDC / OAuth 2.0](#oidc--oauth-20)
   - [How the flow works](#how-the-flow-works)
   - [Required claims](#required-claims)
   - [User provisioning](#user-provisioning)
   - [Configuring a provider](#configuring-a-provider)
3. [Admin UI — managing auth settings](#admin-ui--managing-auth-settings)
4. [Disabling local login](#disabling-local-login)
   - [Auto-redirect behaviour](#auto-redirect-behaviour)
   - [Lockout prevention via environment override](#lockout-prevention-via-environment-override)
5. [Environment variables](#environment-variables)
6. [URL reference](#url-reference)

---

## Local Login

Local login uses Django's standard `ModelBackend`. Users authenticate with a **username** and **password** stored in the `auth_user` table.

- Passwords are hashed with Django's default hasher (PBKDF2).
- Local login is **enabled by default** and can be turned off in the admin UI once at least one OIDC provider is active (see [Disabling local login](#disabling-local-login)).
- The login form is rendered at `/login/`.

---

## OIDC / OAuth 2.0

SCOUT implements the **Authorization Code flow with PKCE** (RFC 7636) on top of OpenID Connect. Any standards-compliant IdP — Authentik, Okta, Keycloak, Auth0, Google Workspace, etc. — can be used.

Multiple providers can be configured simultaneously. Each is stored as an `OIDCProvider` row in the database and managed through the admin panel.

### How the flow works

```
Browser                   SCOUT                             Identity Provider
  |                           |                                    |
  |  GET /login/              |                                    |
  |-------------------------->|                                    |
  |                           |                                    |
  |  Click "Sign in with X"  |                                    |
  |-------------------------->|                                    |
  |                           | Generate state + PKCE verifier     |
  |                           | Store in session                   |
  |                           | Build authorization URL            |
  |<--------------------------| 302 → IdP /authorize               |
  |                                                                |
  |  User authenticates at IdP                                     |
  |---------------------------------------------------------------->
  |                                                                |
  |  IdP redirects back: /oidc/<id>/callback/?code=…              |
  |<----------------------------------------------------------------
  |                                                                |
  |             Validate state & provider_id from session          |
  |                           |                                    |
  |                           | POST token_endpoint (code + PKCE)  |
  |                           |----------------------------------->|
  |                           |  { access_token, id_token }       |
  |                           |<-----------------------------------|
  |                           |                                    |
  |                           | Verify id_token JWT (RS256/HS256)  |
  |                           | GET user_endpoint (userinfo)       |
  |                           |----------------------------------->|
  |                           |  { email, sub, preferred_username, |
  |                           |    cap:site_scout, cap:admin_scout }|
  |                           |<-----------------------------------|
  |                           |                                    |
  |                           | Check cap:site_scout == true       |
  |                           | Find or create User                |
  |                           | Sync is_staff from cap:admin_scout |
  |                           | Login user                         |
  |<--------------------------| 302 → /                            |
```

**Security measures applied during the flow:**

| Check | Detail |
|---|---|
| PKCE (S256) | `code_verifier` stored in session; `code_challenge` sent to IdP |
| State parameter | Random 128-bit token; validated on callback to prevent CSRF |
| Provider ID binding | Session stores `oidc_provider_id`; callback must match |
| JWT signature | Verified against JWKS (RS256) or client secret (HS256) |
| Audience claim | `aud` must equal the configured `client_id` |
| Capability gate | `cap:site_scout` must be `true`; users without it are rejected |

### Required claims

SCOUT expects the following claims in either the **ID token** or the **userinfo endpoint** response (userinfo takes precedence):

| Claim | Required | Purpose |
|---|---|---|
| `email` | Recommended | Primary key for matching existing users |
| `sub` | Recommended | Fallback user identifier (used if no email match) |
| `preferred_username` | Optional | Sets the username on first login |
| `name` | Optional | Fallback display name |
| `cap:site_scout` | **Required** | Must be `true` to grant access |
| `cap:admin_scout` | Optional | `true` → `is_staff = True` (admin access) |

> `cap:site_scout` and `cap:admin_scout` are custom claims. Configure your IdP to include them in the token. In Authentik, these can be set via a **Property Mapping** on the OAuth2/OIDC provider.

**Admin status is synced on every login.** If `cap:admin_scout` changes in the IdP, the user's `is_staff` flag in SCOUT is updated automatically on their next login.

### User provisioning

SCOUT creates local `auth_user` accounts automatically on first OIDC login. The lookup/creation logic runs in this order:

1. Look up an existing user by **email** (case-insensitive)
2. If not found, look up by username `oidc_<sub>` (sub-based fallback)
3. If not found, look up by **preferred_username** (case-insensitive)
4. If still not found, create a new user with:
   - Username derived from `preferred_username` → `email` prefix → `oidc_<sub>` (de-duplicated with a numeric suffix if needed)
   - Email from claims
   - `is_staff` from `cap:admin_scout`
   - Unusable password set (OIDC-only user)
   - No environment access by default (admin assigns via Users page)

### Configuring a provider

Providers are managed in **Admin → General Settings → Identity Providers (OIDC)**.

Required fields:

| Field | Description | Example |
|---|---|---|
| Display Name | Shown on the login button | `Authentik` |
| Client ID | Application client ID from the IdP | `scout` |
| Client Secret | Application client secret | `abc123…` |
| Authorization Endpoint | IdP's `/authorize` URL | `https://auth.example.com/application/o/authorize/` |
| Token Endpoint | IdP's `/token` URL | `https://auth.example.com/application/o/token/` |
| Userinfo Endpoint | IdP's `/userinfo` URL | `https://auth.example.com/application/o/userinfo/` |
| JWKS Endpoint | IdP's public key set URL | `https://auth.example.com/application/o/scout/jwks/` |
| Signing Algorithm | `RS256` (asymmetric, recommended) or `HS256` | `RS256` |
| Enabled | Whether the provider appears on the login page | checked |

The **redirect URI** to register in your IdP is:
```
https://<your-domain>/oidc/<provider-id>/callback/
```
The numeric `provider-id` is shown in the provider table and in the Callback URL column after saving.

---

## Admin UI — managing auth settings

The **Admin → General Settings** page includes an **Identity Providers (OIDC)** section that handles both OIDC provider management and the local login toggle.

- **Add / Edit / Delete** OIDC providers via the table and modal form.
- **Enable / Disable** individual providers with the "Enabled" checkbox in the edit modal.
- **Local Login toggle** — a switch at the bottom of the Identity Providers card. See next section.

---

## Disabling local login

The **Local Login** toggle (General Settings → Identity Providers → Local Login) disables the username/password form on the login page.

**Prerequisites before disabling:**
- At least one OIDC provider must be **enabled**. If no providers are active, the toggle cannot be turned off.

When local login is disabled:
- The username/password form is hidden from `/login/`
- OIDC provider buttons are shown full-width with no "Or sign in with" separator
- POSTing credentials to the login endpoint is rejected

> Disabling local login does not delete or deactivate local user accounts. It only removes the login UI. Re-enabling the toggle immediately restores access.

### Auto-redirect behaviour

When local login is **disabled** and exactly **one** OIDC provider is configured and enabled, SCOUT skips the login page entirely and redirects the browser directly to that provider's authorization endpoint. Users see no intermediate page.

If local login is disabled and **multiple** providers are configured, the login page still renders — but shows only the provider buttons (no username/password form).

### Lockout prevention via environment override

If you accidentally disable local login and your IdP is unavailable, you would be locked out. To prevent this, set the following environment variable:

```
ALLOW_LOCAL_LOGIN=1
```

When set, local login is **always available** regardless of the database setting. The toggle in the admin UI is shown as greyed out with a note: *"Forced on via ALLOW_LOCAL_LOGIN environment variable"*.

This variable can be set in `.env` or passed directly as a container/system environment variable. It defaults to `0` (no override; follow DB setting).

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `ALLOW_LOCAL_LOGIN` | `0` | Set to `1` to force local login on, overriding the admin UI toggle |

All other authentication configuration (OIDC providers, local login toggle) is stored in the database and managed through the admin panel.

---

## URL reference

| URL | View | Notes |
|---|---|---|
| `/login/` | `login_view` | Login page; POST for local auth |
| `/logout/` | `logout_view` | Clears session, redirects to login |
| `/settings/` | `settings_view` | Change profile, password, timezone |
| `/oidc/<id>/login/` | `oidc_login` | Initiates OIDC flow for provider `<id>` |
| `/oidc/<id>/callback/` | `oidc_callback` | OIDC redirect URI; validates and completes login |
| `/admin-config/oidc/` | `api_oidc_list` | GET — list all providers (admin only) |
| `/admin-config/oidc/create/` | `api_oidc_create` | POST — create a provider (admin only) |
| `/admin-config/oidc/<id>/update/` | `api_oidc_update` | POST — update a provider (admin only) |
| `/admin-config/oidc/<id>/delete/` | `api_oidc_delete` | POST — delete a provider (admin only) |
| `/admin-config/oidc/local-login/` | `api_toggle_local_login` | POST `{enabled: bool}` — toggle local login (admin only) |
