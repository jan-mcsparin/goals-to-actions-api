from typing import Literal

from app.schemas import ApiModel

Intensity = Literal["easingOff", "normal", "goingHard"]

# The database spells two-word values in snake_case, JSON in camelCase.
INTENSITY_IN_DATABASE: dict[Intensity, str] = {
    "easingOff": "easing_off",
    "normal": "normal",
    "goingHard": "going_hard",
}
INTENSITY_IN_JSON: dict[str, Intensity] = {
    stored: sent for sent, stored in INTENSITY_IN_DATABASE.items()
}


class Settings(ApiModel):
    """The person's one setting. It sets the cap the week read marks each day against
    (ADR-013); nothing resets it or suggests changing it."""

    intensity: Intensity

    @classmethod
    def from_stored(cls, intensity: str) -> Settings:
        return cls(intensity=INTENSITY_IN_JSON[intensity])


class IntensityChoice(ApiModel):
    intensity: Intensity
