"""What routes ask for, spelled once."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends

from app.database import Database, get_database
from app.sign_in.session import current_user_id

CurrentDatabase = Annotated[Database, Depends(get_database)]
CurrentUserId = Annotated[UUID, Depends(current_user_id)]
