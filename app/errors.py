"""What a rules module raises when a request can't be carried out. `main.py` turns each into
its response, so rules modules need nothing from FastAPI."""


class NotAllowed(Exception):
    """The rules don't allow this change. Sent as 409 with this message."""
