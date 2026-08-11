from pydantic import BaseModel, Field


class ParamsIn(BaseModel):
    hfa: float = Field(ge=0, le=300)
    k: float = Field(gt=0, le=100)
    revert: float = Field(ge=0, le=1)
    mov_base: float = Field(gt=0, le=10)
    blend_weight: float = Field(ge=0, le=1)


class PickIn(BaseModel):
    # The team is checked against the actual matchup by the endpoint; the pattern here only
    # keeps obvious junk out of the database.
    team: str = Field(min_length=2, max_length=4, pattern=r"^[A-Z]{2,4}$")
    # A week has never had more than 16 games, so a confidence rank above that is a typo.
    confidence: int | None = Field(default=None, ge=1, le=16)
