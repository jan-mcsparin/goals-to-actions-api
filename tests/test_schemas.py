from app.schemas import ApiModel


class Example(ApiModel):
    planned_day: str


def test_json_field_names_are_camel_case() -> None:
    assert Example(planned_day="2026-11-17").model_dump(by_alias=True) == {
        "plannedDay": "2026-11-17"
    }


def test_camel_case_json_is_accepted() -> None:
    assert Example.model_validate({"plannedDay": "2026-11-17"}).planned_day == "2026-11-17"
