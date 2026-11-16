"""Writes the API's schema to `openapi.json`, the committed copy of the contract. The front
end generates its types from that file, and its diff shows every contract change in review.

    uv run python -m app.openapi
"""

import json
from pathlib import Path

from app.main import app

OPENAPI_FILE = Path(__file__).parent.parent / "openapi.json"


def schema_text() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    OPENAPI_FILE.write_text(schema_text())
    print(f"Wrote {OPENAPI_FILE.name}")
