# Implementation Plan: Sign-in (#14)

Spec: [`../specs/sign-in.md`](../specs/sign-in.md). Tasks: [`todo.md`](todo.md). (The plan for #13 is in git history.)

## Overview

Replace the fixed user with a person who has proved who they are: a passkey to sign in, a session row and a `__Host-` cookie to stay signed in, a one-time code made by a command to add a passkey, and the same command adding an invited tester (ADR-012). Every route but `health` and the sign-in routes answers 401 without a session, and a write from another origin is a 403.

Twelve tasks. **One PR** in the API, `sign-in` (closes #14), branched from `invited-testers` (#42, the spec change), and one small PR in the front end for the regenerated types. The sign-in screens, the 401 handling in the queue and signing out on the phone are front-end work with their own issues.

## The contract

New, none queueable (ADR-010). All under `/api/sign-in`, all open without a session, all writes (so all checked for origin).

| Operation | Route | Body | Returns |
| --- | --- | --- | --- |
| `redeemCode` | `POST /api/sign-in/code` | `{"code": "ABCD-EFGH-..."}` | `PasskeyOptions`: `{"challengeId", "options"}`, the browser's registration options as JSON |
| `addPasskey` | `POST /api/sign-in/passkeys` | `{"challengeId", "credential"}` | 204, and the session cookie |
| `startSignIn` | `POST /api/sign-in/start` | none | `PasskeyOptions`, the sign-in options |
| `finishSignIn` | `POST /api/sign-in/finish` | `{"challengeId", "credential"}` | 204, and the session cookie |
| `signOut` | `POST /api/sign-in/sign-out` | none | 204, and the cookie cleared |

`credential` is the browser's `PublicKeyCredential` as JSON, passed whole to the library; in the schema it's an object. A code that's wrong, used or expired, a challenge that's used or expired, and a passkey the library rejects are all a 401 with one detail, "That didn't work", so nothing tells a guesser which part was wrong.

## Architecture decisions

- **The session is read by `current_user_id`** in `app/database.py` (moved to `app/sign_in/session.py`), which every route already asks for. No session, an ended one, or one unused for 90 days is a 401. Each protected router also lists it in `dependencies=`, so the 401 comes before a 422 for a missing header or body.
- **Last use:** when the session was last recorded more than a day ago, the dependency records now, in its own small write, and sends the cookie again with a fresh 90-day `Max-Age`, so the browser's copy lasts as long as the server's.
- **The cookie** is `__Host-session`: `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, no `Domain`. The token is `secrets.token_urlsafe(32)`; the database keeps its SHA-256. A hash of a random 256-bit token needs no salt or slow hash, and is the standard library's, not ours.
- **The origin check reads `Origin`.** Browsers send it on every `POST`, `PUT`, `PATCH` and `DELETE`, same-origin included. A write whose `Origin` isn't `APP_ORIGIN` exactly, or that has none, is a 403. Reads aren't checked. CloudFront must pass `Origin` on (its origin request policy), noted for hosting. This settles open question 2.
- **Settings, read from the environment** in `app/config.py`: `APP_ORIGIN` (default `http://localhost:5173`, the dev server) and `PASSKEY_RP_ID` (default `localhost`; hosted, `goals-to-actions.jan-mcsparin.me`).
- **Passkeys:** discoverable (resident key required), user verification required, no attestation. Sign-in starts with no user named; the passkey says whose it is. The checks are `webauthn` 3.0.1's `verify_registration_response` and `verify_authentication_response`.
- **A code** is 20 characters from the Crockford base-32 alphabet (100 random bits), printed in five groups of four. Case, dashes and spaces are ignored when typed. Stored as its SHA-256; spent when redeemed, so a failed registration needs a new code. It lasts ten minutes. A challenge lasts five.
- **Tables** (open questions 1 and 3):

  | Table | Owner | Shared columns | Audited |
  | --- | --- | --- | --- |
  | `passkeys`: credential id (unique), public key, sign count, transports | `user_id` | all | yes: nothing secret in it |
  | `sign_in_codes`: code hash, expires at, used at | `user_id` | all | yes: who was given a code and when; the hash of a spent ten-minute code is no use to anyone |
  | `sessions`: token hash, last used at; ended is `deleted_at` | `user_id` | all | no: no token hashes in the log, and no audit row on every daily touch |
  | `sign_in_challenges`: challenge, kind (`add_passkey`, `sign_in`), expires at; deleted when used | `user_id` only for `add_passkey` (empty before anyone is known) | `id`, `created_at` | no |

  The server makes these ids (nothing here is created offline). Sign-in writes with no user yet (starting a sign-in) run audited as no one: they touch only unaudited tables.
- **The command** is `uv run python -m app.sign_in.command`: `add-user` makes a user (Normal intensity, no weeks opened) and prints their id and first code; `code <user-id>` prints a new code. Hosted, it is run inside AWS (ADR-011); how is hosting's to settle.
- **Tests make a session row directly.** The `client` fixture signs in as the fixed user that way, sends `Origin: APP_ORIGIN`, and uses `https://testserver` so the `Secure` cookie is sent. Every existing test keeps working unchanged. The passkey routes are tested for refusal through the real library; their success paths replace the library's two verify functions with stand-ins that return a result, since tests don't act out a passkey (spec).
- **Two tests over the whole schema,** each failing for an operation without a case: every route but `health` and the sign-in routes is a 401 with no session (`tests/test_signed_out.py`); and for every operation, a second user acting on the first user's rows leaves them unchanged and gets back none of their ids (`tests/test_other_user.py`, reusing `test_repeats.py`'s cases and snapshot).
- **The repeat test leaves out `redeemCode`, `addPasskey`, `startSignIn` and `finishSignIn`** by name: a code and a challenge work once on purpose. `signOut` is in it.
- **Dependency:** `webauthn>=3.0.1` (3.0.1 locked), which brings `cryptography`, `cbor2`, `pyOpenSSL`, `pyasn1` and `pyasn1-modules`. Asked for in the approval.

## Dependency graph

```
1 dependency
2 sessions + 401 ──┬── 3 origin check ── 4 sign out
                  ├── 8 second user can't reach the first's rows
5 codes + command ┴── 6 add a passkey ── 7 sign in with a passkey
                                     └── 9 add-user end to end
10 docs ── 11 security review ── 12 front-end types
```

## Task list

See [`todo.md`](todo.md).

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Moving every test to a signed-in client breaks many at once | Med | Task 2 changes only the fixture's defaults; the full suite runs before its commit |
| A route resolves its body or `X-Time-Zone` before the session, so a signed-out request gets a 422 | Med | Router-level dependency; the schema-wide 401 test sends no header and no body |
| The second-user test finds a create that answers 500 or touches another user's row when given their id | High (it's the point) | Fix in the task, each with its own test; stop and ask if a fix changes the contract |
| Safari doesn't keep a `Secure` cookie on `http://localhost` | Low | Local sign-in tested in Chrome; the installed app is tested against the hosted API (ADR-012) |
| `webauthn` or `cryptography` won't install on Python 3.15 | Med | Task 1 installs and imports it first, before anything is built on it |
