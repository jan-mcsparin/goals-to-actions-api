# Spec: Sign-in

Status: draft 2026-11-13, and blocked on a decision: ADR-003 left sign-in open. It needs its own ADR before this spec can be finalised. Issue: [#14](https://github.com/jan-mcsparin/goals-to-actions-api/issues/14). Module `sign-in` in the [map](README.md). Depends on `database-foundation`; built last.

## Objective

Replace the one fixed user with a person who has proved who they are, so the API can be put somewhere reachable from a phone without being open to anyone with the address. The data model has had an owner on every row from the start, so this changes who the current user is, not how anything is stored.

References: [ADR-003](../../docs/adr/0003-fastapi-postgres.md), [`data-model.md`](../../docs/data-model.md#users), [`product-rules.md`](../../docs/product-rules.md#out-of-scope-for-the-prototype).

## Scope

**In (whatever the method):**

- The current-user dependency reads who is signed in instead of returning the fixed user. Without proof, every route but `health` answers 401.
- The fields the method needs on `users`, or a table beside it.
- The fixed user becomes the founder's account, keeping its id and all its rows.
- The session survives iOS closing the installed app, so opening Today doesn't mean signing in again.
- The offline queue and sign-in: what the phone does with queued writes when its session has ended.

**Out (later):**

- Sign-up for other people, and the safety principles required before anyone else uses the app.
- Row-level security in Postgres (ADR-007: when there is a second user).
- Deleting an account, exporting data.

## Testing strategy

As shared, plus: every route in the OpenAPI schema refuses a request with no session; a second user created in a test can't read or change the first's rows through any route, which is the test the owner-in-every-query rule has been waiting for.

## Boundaries

As shared. **Ask first:** every dependency here; any third-party service. **Never:** a home-made password hash or token format; a secret in the repo; a session readable by page scripts if a cookie can do the job.

## Success criteria

- [ ] An ADR records the method and why.
- [ ] No route but `health` answers without a session.
- [ ] The founder's existing data is theirs after the change.
- [ ] The installed app stays signed in across restarts.
- [ ] The four checks pass.

## Open questions

1. **The method.** For one person on their own devices the candidates are a passkey, a sign-in link by email, a provider (Apple, Google), or a hosted auth service. This is the ADR, and it is tied to the hosting choice, which is also open.
2. **Does this have to be last?** If the API is hosted before every other slice is done, something must stand in front of it sooner, even a single shared secret.
