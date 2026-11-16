"""What routes ask for, spelled once."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends

from app.database import Database, current_user_id, get_database

CurrentDatabase = Annotated[Database, Depends(get_database)]
CurrentUserId = Annotated[UUID, Depends(current_user_id)]
