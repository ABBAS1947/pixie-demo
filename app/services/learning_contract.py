"""Validated task contracts shared by Chat Learn and Review. No model grading."""
from app.services.numeric_verification import parse_numeric
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class TaskContent(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    title: str = Field(min_length=1, max_length=160)
    instruction: str = Field(min_length=1, max_length=4000)
    question: str = Field(min_length=1, max_length=2000)
    response_kind: Literal['numeric', 'selection', 'external']
    options: list[str] = Field(default_factory=list, max_length=20)
    answer: str = Field(min_length=1, max_length=500)
    explanation: str = Field(min_length=1, max_length=2000)
    hint: str = Field(min_length=1, max_length=2000)
    family: str = Field(min_length=1, max_length=160)
    language: str = Field(min_length=2, max_length=20)
    assessed_construct: str = Field(min_length=1, max_length=500)
    approval: str = Field(min_length=1, max_length=500)
    purpose: Literal['practice', 'independent', 'delayed']
    minimum_delay_seconds: int | None = Field(default=None, ge=1, le=31536000)

    @model_validator(mode='after')
    def valid_key(self):
        if self.purpose=='delayed' and self.minimum_delay_seconds is None:
            raise ValueError('Delayed item requires a reviewed minimum delay')
        if self.response_kind == 'selection':
            if len(self.options)<2 or len(set(self.options)) != len(self.options) or self.answer not in self.options:
                raise ValueError('Selection key/options inconsistent')
        elif self.response_kind == 'numeric':
            if parse_numeric(self.answer) is None: raise ValueError('Invalid or nonfinite numeric key')
        return self

    def presentation(self):
        return self.model_dump(exclude={'answer','explanation','hint','approval'})

def grade(content: TaskContent, response: str) -> str:
    if content.response_kind=='external': return 'unassessable'
    if content.response_kind=='selection':
        if response not in content.options: return 'unassessable'
        return 'correct' if response==content.answer else 'incorrect'
    value=parse_numeric(response)
    if value is None:return 'unassessable'
    return 'correct' if value==parse_numeric(content.answer) else 'incorrect'
