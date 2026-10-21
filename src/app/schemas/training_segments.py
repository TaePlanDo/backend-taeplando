"""Request and response models for the fixed training-segment catalog."""

from pydantic import BaseModel


class TrainingSegmentResponse(BaseModel):
    """One fixed training-segment dictionary entry."""

    id: int
    code: str
    name: str
