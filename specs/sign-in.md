# Spec: Sign-in

Status: draft 2026-11-13; the method was settled on 2026-11-16 by [ADR-012](../../docs/adr/0012-sign-in-with-a-passkey.md). Finalised when its plan is written. Issue: [#14](https://github.com/jan-mcsparin/goals-to-actions-api/issues/14). Module `sign-in` in the [map](README.md). Depends on `database-foundation`; built last, and before the API is first reachable from outside ([ADR-011](../../docs/adr/0011-hosting-on-aws.md)).

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

- Sign-up for other people, and the safety principles required before anyone else uses the app.
- Row-level security in Postgres (ADR-007: when there is a second user).
- Deleting an account, exporting data.
- A password, a sign-in link by email, a provider, or a hosted auth service (ADR-012 says why).

## Testing strategy

As shared, plus:

- every route in the OpenAPI schema but `health` and the sign-in routes refuses a request with no session;
- a second user created in a test can't read or change the first's rows through any route, which is the test the owner-in-every-query rule has been waiting for;
- a session is used, expires after 90 days unused, and ends at sign-out; last use is written once in a day of many requests;
- a code works once, not twice, and not after ten minutes;
- a write from another origin is refused, and a read is not;
- tests make a session row directly. They don't act out a passkey.

## Boundaries

As shared. **Ask first:** every dependency here (the WebAuthn library brings `cryptography` with it); any third-party service. **Never:** a home-made password hash, token format or signature check; a secret in the repo; a session readable by page scripts; a token stored unhashed; a call out to the internet.

## Success criteria

- [x] An ADR records the method and why (ADR-012).
- [ ] No route but `health` and the sign-in routes answers without a session.
- [ ] The founder's existing data is theirs after the change.
- [ ] A passkey can be added with a one-time code, and signs in.
- [ ] The installed app stays signed in across restarts.
- [ ] The four checks pass.

## Open questions

1. **Do the sign-in tables carry the audit trigger** like every other table (shared decision 3)? The audit log shouldn't collect token hashes or be written on every daily touch of a session. I'd audit passkeys and codes, and leave sessions and challenges out.
2. **Which header the origin check reads** (`Origin` or `Sec-Fetch-Site`), and that CloudFront passes it through. ADR-012 lists it to confirm when built.
3. **Do the sign-in tables have `user_id` as their owner and the other shared columns?** A challenge exists before anyone is signed in.

Settled 2026-11-16: the method (ADR-012), and that sign-in is built before the API is hosted, with no temporary shared secret (ADR-011).
