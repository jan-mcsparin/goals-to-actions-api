# Tasks: Sign-in (#14)

Plan: [`plan.md`](plan.md). Spec: [`../specs/sign-in.md`](../specs/sign-in.md).

Every task: write the tests first, run the four checks (`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest`), then one commit. A task that adds a route also runs `uv run python -m app.openapi`.

# PR: `sign-in` (closes #14)

### Task 1: Add the WebAuthn library

**Description:** `uv add "webauthn>=3.0.1"` (asked for and agreed in the plan's approval).

**Acceptance criteria:**
- [x] It and `cryptography` install on Python 3.15 and import; `uv.lock` is committed.

**Verify:** `uv run python -c "import webauthn"`, then the four checks.

**Dependencies:** none.

### Task 2: A session, and 401 without one

**Description:** The `sessions` table (unaudited) and its queries; `current_user_id` reads the `__Host-session` cookie; every protected router lists it as a dependency. Last use recorded at most once a day, with the cookie sent again. The `client` fixture signs in as the fixed user by making a session row, uses `https://testserver` and sends `Origin`.

**Acceptance criteria:**
- [x] Every route in the schema but `health` and `/api/sign-in/*` is a 401 with no session; the test reads the schema, so a new route is covered (`tests/test_signed_out.py`). An unknown token, an ended session and one unused for 90 days are a 401 (`tests/test_sessions.py`).
- [x] A session is used; last use is written once in a day of many requests, and again the next day with a fresh cookie.
- [x] The database holds only the token's hash (SHA-256 in hex: the generated models can't hold `bytea`); the existing suite passes, with one test that jumps the clock past 90 days kept signed in.

**Verify:** `uv run pytest tests/test_signed_out.py tests/test_sessions.py`, then the four checks.

**Dependencies:** none.

### Task 3: Refuse a write from another origin

**Description:** A write (`POST`, `PUT`, `PATCH`, `DELETE`) whose `Origin` isn't `APP_ORIGIN`, or that has none, is a 403. Reads aren't checked.

**Acceptance criteria:**
- [x] A write from a sibling subdomain, and one with no `Origin`, is a 403 and changes nothing; the same write from the app's origin lands.
- [x] A read from another origin is answered.

**Verify:** `uv run pytest tests/test_origin.py`, then the four checks.

**Dependencies:** 2.

### Task 4: Sign out

**Description:** `signOut`, `POST /api/sign-in/sign-out`: ends the session on the server and clears the cookie. Signing out with no session is a 204 too. A case in `test_repeats.py`.

**Acceptance criteria:**
- [x] After signing out, the same cookie gets a 401.
- [x] Sent twice, the same answer.

**Verify:** `uv run pytest tests/test_sessions.py tests/test_repeats.py`, then the four checks.

**Dependencies:** 2, 3.

## Checkpoint: after tasks 1–4
- [x] The four checks pass; every route is closed without a session.

### Task 5: One-time codes and the command

**Description:** The `sign_in_codes` table (audited) and its queries; `app/sign_in/codes.py` makes a code and keeps its hash; `python -m app.sign_in.command add-user` and `code <user-id>`.

**Acceptance criteria:**
- [x] `add-user` makes a user at Normal intensity with no weeks opened, and prints their id and a code; `code` prints a code for an existing user and refuses an unknown one.
- [x] A code is 20 Crockford base-32 characters in groups of four; the table holds its hash and an expiry ten minutes on.

**Verify:** `uv run pytest tests/test_sign_in_codes.py`, then the four checks.

**Dependencies:** none.

### Task 6: Add a passkey with a code

**Description:** The `sign_in_challenges` and `passkeys` tables; `redeemCode` and `addPasskey`. Redeeming spends the code and returns registration options and a challenge; adding verifies the credential with the library, keeps the passkey and starts a session.

**Acceptance criteria:**
- [x] A code works once, not twice, and not after ten minutes; a wrong one is a 401. Case, dashes and spaces don't matter.
- [x] A credential the library rejects, or an expired or used challenge, is a 401 and keeps nothing; one it accepts keeps the passkey and sets the cookie, which then reads the user's rows.
- [x] The options ask for a discoverable passkey and user verification, for the configured relying party.

**Verify:** `uv run pytest tests/test_add_passkey.py`, then the four checks.

**Dependencies:** 2, 5.

### Task 7: Sign in with a passkey

**Description:** `startSignIn` and `finishSignIn`. Start makes a challenge with no user; finish finds the passkey by its credential id, verifies with the library, records the new sign count and starts a session.

**Acceptance criteria:**
- [x] An unknown credential, a rejected one, a deleted passkey and an expired or used challenge are a 401.
- [x] An accepted one sets the cookie for the passkey's owner and updates the sign count.

**Verify:** `uv run pytest tests/test_sign_in.py`, then the four checks.

**Dependencies:** 6.

### Task 8: A second user can't reach the first's rows

**Description:** `tests/test_other_user.py`: for every operation in the schema, arrange the first user's rows (reusing `test_repeats.py`'s cases), send the request as a second user, and check the first user's rows are unchanged and no id of theirs comes back. Fix what it finds. Also sends each device-made create again as the second user with the first's id. It found nothing to fix.

**Acceptance criteria:**
- [x] Every operation has a case; the test fails for one without.
- [x] No answer is a 500.

**Verify:** `uv run pytest tests/test_other_user.py`, then the four checks.

**Dependencies:** 2.

### Task 9: An invited tester, end to end

**Description:** One test: `add-user`, redeem its code, add a passkey (library stood in), then a request that needs the day opens the new user's first week, and they see only their own rows.

**Acceptance criteria:**
- [ ] The new user's week opens on their first request, at Normal intensity.

**Verify:** `uv run pytest tests/test_invited_tester.py`, then the four checks.

**Dependencies:** 5, 6.

## Checkpoint: after tasks 5–9
- [ ] The four checks pass; the spec's success criteria that tests can show are met.

### Task 10: Docs

**Description:** `data-model.md` gains the four tables; `specs/sign-in.md` finalised (open questions settled); ADR-012's "to confirm" notes the `Origin` header; `specs/README.md` decision 2 updated; the README says how to add a user and make a code, and that sign-in routes are one-shot; `CLAUDE.md`'s structure lists `app/sign_in/`.

**Acceptance criteria:**
- [ ] Every doc describes what was built.

**Verify:** read through; the four checks.

**Dependencies:** 1–9.

### Task 11: Security review before merge

**Description:** A security review of the `sign-in` branch against `main`, by the security-auditor agent, before the PR merges and before the API is first hosted (#8). It reviews how the pieces fit, not the algorithms (the library checks the signatures): the cookie's flags and expiry, the `Origin` check, a code and a challenge working once with no race between two requests, every route answering 401 without a session, and no user reaching another's rows. Each finding is fixed with a test, or recorded in the PR with why it can wait for open sign-up.

**Acceptance criteria:**
- [ ] The review has been run, and its findings are listed in the PR.
- [ ] Every finding to be fixed before hosting is fixed, with a test; the rest are noted as left for open sign-up.

**Verify:** the four checks after the fixes.

**Dependencies:** 1–10.

# PR in the front end: regenerated types

### Task 12: Regenerate the front end's types

**Description:** On a branch in `web-frontend/`, regenerate the API types from `openapi.json`; the mock client compiles. No screens change.

**Acceptance criteria:**
- [ ] Types regenerated; the front end's typecheck, lint and tests pass.

**Verify:** the front end's own checks (`nvm use` first).

**Dependencies:** 11.
