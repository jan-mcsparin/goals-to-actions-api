import os
from uuid import UUID

# The only place the product name appears in code, as in the front end's config.ts.
APP_NAME = "Goals to Actions"

# Defaults to the local Postgres in compose.yaml.
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://gta:gta@localhost:5432/gta_dev")

# The founder's account: the one user before sign-in, created by the users migration with
# this id and keeping every row made then. Tests act as this user.
FIXED_USER_ID = UUID("00000000-0000-4000-8000-000000000001")

# The app's own origin: a write from anywhere else is refused (ADR-012). Defaults to the front
# end's dev server; hosted, `https://goals-to-actions.jan-mcsparin.me`.
APP_ORIGIN = os.environ.get("APP_ORIGIN", "http://localhost:5173")

# The name passkeys are bound to (ADR-012). Passkeys work on `localhost` or HTTPS on a real
# name; hosted, `goals-to-actions.jan-mcsparin.me`. A passkey made for one works nowhere else.
PASSKEY_RP_ID = os.environ.get("PASSKEY_RP_ID", "localhost")
