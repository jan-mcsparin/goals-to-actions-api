from fastapi import APIRouter

from app.db import users
from app.dependencies import CurrentDatabase, CurrentUserId
from app.settings import rules
from app.settings.models import INTENSITY_IN_DATABASE, IntensityChoice, Settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def get_settings(database: CurrentDatabase, user_id: CurrentUserId) -> Settings:
    with database.read() as connection:
        owner = users.Querier(connection).get_user(id=user_id)
    assert owner is not None
    return Settings.from_stored(owner.intensity)


@router.put("/intensity")
def set_intensity(
    body: IntensityChoice, database: CurrentDatabase, user_id: CurrentUserId
) -> Settings:
    with database.transaction(user_id, "set intensity") as connection:
        stored = rules.set_intensity(connection, user_id, INTENSITY_IN_DATABASE[body.intensity])
    return Settings.from_stored(stored)
