from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import Connection, Engine, create_engine, text

from app.config import DATABASE_URL, FIXED_USER_ID

# Read by the audit trigger. `true` makes each setting last for this transaction only.
SET_AUDIT_CONTEXT = text(
    "select set_config('app.user_id', :user_id, true), set_config('app.action', :action, true)"
)
SET_READ_ONLY = text("set transaction read only")


class Database:
    """Where application code gets its connections.

    Normally it's bound to the engine. Tests bind it to one connection inside a transaction
    they roll back; then each transaction() is a savepoint, and each read() a read-only
    savepoint that's rolled back.
    """

    def __init__(self, bind: Engine | Connection) -> None:
        self._bind = bind

    @contextmanager
    def transaction(self, user_id: UUID, action: str) -> Iterator[Connection]:
        """The only way application code writes: one transaction, audited as this user doing
        this action ("skip task", "pause goal")."""
        with self._begin() as connection:
            connection.execute(SET_AUDIT_CONTEXT, {"user_id": str(user_id), "action": action})
            yield connection

    @contextmanager
    def read(self) -> Iterator[Connection]:
        """A connection for reads. Postgres refuses any write made through it."""
        if isinstance(self._bind, Connection):
            # A read-only savepoint, always rolled back: that's what puts read-write back.
            savepoint = self._bind.begin_nested()
            try:
                self._bind.execute(SET_READ_ONLY)
                yield self._bind
            finally:
                savepoint.rollback()
            return
        with self._bind.connect() as connection:
            yield connection.execution_options(postgresql_readonly=True)

    @contextmanager
    def _begin(self) -> Iterator[Connection]:
        if isinstance(self._bind, Connection):
            with self._bind.begin_nested():
                yield self._bind
            return
        with self._bind.begin() as connection:
            yield connection


engine = create_engine(DATABASE_URL)
database = Database(engine)


def get_database() -> Database:
    """The dependency routes get the database from. Tests override it."""
    return database


def current_user_id() -> UUID:
    """The dependency routes get the user from. Every request is the fixed user until
    sign-in replaces this."""
    return FIXED_USER_ID
