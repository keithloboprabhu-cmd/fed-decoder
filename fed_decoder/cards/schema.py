"""Decoder card schema. The LLM fills the prose fields; `decision` numbers,
tone quotes, and impact numbers are checked against code-computed values."""
from __future__ import annotations

from pydantic import BaseModel, Field


class Decision(BaseModel):
    direction: str = Field(description="One of: hike, cut, hold")
    change_bps: int = Field(description="Size of the move in basis points; negative for cuts, 0 for hold")
    target_low: float = Field(description="Lower bound of the target range in percent (equal to upper before Dec 2008)")
    target_high: float = Field(description="Upper bound of the target range in percent")
    votes_for: int | None = Field(description="Number of votes for the action; null if the statement does not report votes")
    votes_against: int | None = Field(description="Number of dissents; null if not reported")
    dissenters: list[str] = Field(description="Full names of dissenting voters, as written in the statement")
    summary: str = Field(description="One plain-English sentence describing the decision")


class ChangeItem(BaseModel):
    quote: str = Field(description="Verbatim new (or removed) wording from the statement")
    explanation: str = Field(description="Plain-English meaning of the change, one or two sentences")


class ToneQuote(BaseModel):
    quote: str = Field(description="Verbatim sentence from the statement")
    direction: str = Field(description="hawkish or dovish")


class Bullet(BaseModel):
    topic: str = Field(description="Short label, e.g. Borrowers, Savers, Workers, Inflation, Jobs, Growth, Markets, Dollar")
    text: str = Field(description="One plain sentence. Use only numbers present in the context")


class Citation(BaseModel):
    source: str = Field(description="'statement' or a data series ID such as DGS10")
    detail: str = Field(description="The quote or the data value cited")


class CardLLM(BaseModel):
    """What the model produces."""

    decision: Decision
    changes: list[ChangeItem]
    tone_score: float = Field(description="-2 (very dovish) to +2 (very hawkish)")
    tone_quotes: list[ToneQuote]
    for_you: list[Bullet]
    for_country: list[Bullet]
    whats_next: str = Field(description="Two sentences on what the statement signals about upcoming meetings")
    confidence: str = Field(description="high, medium, or low")
    citations: list[Citation]


class Card(CardLLM):
    """Stored card: the model output plus provenance and validation status."""

    meeting_date: str
    provider: str  # gemini | groq | rules
    model: str
    validated: bool
    validation_notes: list[str] = []
    inputs_version: str = "v2-with-diff"
