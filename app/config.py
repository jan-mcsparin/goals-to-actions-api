import os
from uuid import UUID

# The only place the product name appears in code, as in the front end's config.ts.
APP_NAME = "Goals to Actions"

# Defaults to the local Postgres in compose.yaml.
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://gta:gta@localhost:5432/gta_dev")

# The one user until sign-in, created by the users migration with this id.
FIXED_USER_ID = UUID("00000000-0000-4000-8000-000000000001")
