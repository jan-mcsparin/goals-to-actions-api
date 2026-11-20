# Spec: Sign-in

Status: draft 2026-11-13; the method was settled on 2026-11-16 by [ADR-012](../../docs/adr/0012-sign-in-with-a-passkey.md); finalised 2026-11-20 with its plan ([`../tasks/plan.md`](../tasks/plan.md)), which has the contract and the decisions. Issue: [#14](https://github.com/jan-mcsparin/goals-to-actions-api/issues/14). Module `sign-in` in the [map](README.md). Depends on `database-foundation`; built last, and before the API is first reachable from outside ([ADR-011](../../docs/adr/0011-hosting-on-aws.md)).

## Objective

Replace the one fixed user with a person who has proved who they are, so the API can be put somewhere reachable from a phone without being open to anyone with the address. The data model has had an owner on every row from the start, so this changes who the current user is, not how anything is stored.

Sign-in is a passkey, and staying signed in is a session: a row in Postgres and a random token in a host-only cookie (ADR-012).

References: [ADR-012](../../docs/adr/0012-sign-in-with-a-passkey.md), [ADR-011](../../docs/adr/0011-hosting-on-aws.md), [ADR-010](../../docs/adr/0010-week-document-and-replayed-queue.md), [`data-model.md`](../../docs/data-model.md#users), [`product-rules.md`](../../docs/product-rules.md#out-of-scope-for-the-prototype).

## Scope

**In:**

- **The current-user dependency** reads who is signed in instead of returning the fixed user. The fixed user becomes the founder's account, keeping its id and all its rows.
- **Tables** for passkeys, sessions, one-time codes and the challenge of a sign-in under way. Everything sign-in remembers is in Postgres; the API holds nothing between requests.
- **The passkey steps:** starting and finishing a registration, starting and finishing a sign-in. The checks are done by a maintained WebAuthn library, never by our own code.
- **The one-time code:** a command, run inside AWS, makes a code for a user: long, random, used once, gone in ten minutes. A route takes the code and lets that device add a passkey. It is the first sign-in, a new device, and the way back in.
- **Adding a user:** the same command can make a new user and print their first code, so a few invited testers can use the app (ADR-012, revisited 2026-11-19). A new user starts at Normal intensity with no weeks opened; the first request that needs the day opens their week.
- **The session:**
  - the database keeps only a hash of the token;
  - the cookie is `__Host-`, `HttpOnly`, `Secure` and `SameSite=Lax`;
  - it lasts 90 days from its last use, and last use is recorded at most once a day, in a small write of its own;
  - signing out ends it on the server.
- **Who gets in:**
  - every route but `health` and the sign-in routes themselves answers 401 without a session;
  - a write that doesn't come from the app's own origin is refused with a 403.
- **What the phone's queue can rely on** (ADR-010): a 401 or a 403 is never a refusal of the change. The phone keeps the change and sends it after signing in.

**Out (later):**

- A sign-up page and open sign-up, and the safety principles required before anyone the founder doesn't know uses the app.
- Row-level security in Postgres (ADR-007, revisited 2026-11-19: when there is open sign-up).
- Deleting an account, exporting data.
- A password, a sign-in link by email, a provider, or a hosted auth service (ADR-012 says why).

## Testing strategy

As shared, plus:

- every route in the OpenAPI schema but `health` and the sign-in routes refuses a request with no session;
- a second user created in a test can't read or change the first's rows through any route, which is the test the owner-in-every-query rule has been waiting for. With invited testers this is a requirement, not a nicety: it runs over every route in the OpenAPI schema, and fails for a route without a case;
- "add a user" makes a user who can sign in with the code it prints, and whose first week opens on their first request;
- a session is used, expires after 90 days unused, and ends at sign-out; last use is written once in a day of many requests;
- a code works once, not twice, and not after ten minutes;
- a write from another origin is refused, and a read is not;
- tests make a session row directly. They don't act out a passkey.

## Boundaries

As shared. **Ask first:** every dependency here (the WebAuthn library brings `cryptography` with it); any third-party service. **Never:** a home-made password hash, token format or signature check; a secret in the repo; a session readable by page scripts; a token stored unhashed; a call out to the internet.

## Success criteria

- [x] An ADR records the method and why (ADR-012).
- [x] No route but `health` and the sign-in routes answers without a session (`tests/test_signed_out.py`).
- [x] The founder's existing data is theirs after the change: the fixed user is their account, keeping its id.
- [x] A passkey can be added with a one-time code, and signs in (the library's check stood in for in tests; to try for real against `localhost`, then hosted).
- [x] A second user can be added with one command, signs in, and sees only their own rows (`tests/test_invited_tester.py`, `tests/test_other_user.py`).
- [ ] The installed app stays signed in across restarts. Can only be tried once hosted, with the front end's sign-in screens.
- [x] The four checks pass.

## Open questions

None. Settled when the plan was written (2026-11-20):

1. **The audit trigger:** passkeys and codes carry it; sessions and challenges don't, so the log collects no token hashes and no row each day a session is used.
2. **The origin check reads `Origin`,** which browsers send on every write. A write without it, or from anywhere but `APP_ORIGIN`, is a 403. CloudFront must pass the header on: for hosting.
3. **Owners and shared columns:** passkeys, codes and sessions have them all; a session ends by its deleted time. A challenge has `id`, `created_at` and a `user_id` only when adding a passkey, and is deleted when used.

Settled 2026-11-16: the method (ADR-012), and that sign-in is built before the API is hosted, with no temporary shared secret (ADR-011).

Settled 2026-11-19 (Jan): a few invited testers he knows, added by command; no sign-up page. The safety principles wait for people he doesn't know, or for the app suggesting more (`product-rules.md`).
