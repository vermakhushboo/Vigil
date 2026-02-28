"""Vigil — Pydantic models for incidents."""
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class IncidentStatus(str, Enum):
    RECEIVED = "received"
    INVESTIGATING = "investigating"
    CALLING = "calling"
    IN_CALL = "in_call"
    RESOLVED = "resolved"


class IncidentFindings(BaseModel):
    root_cause: Optional[str] = None
    started_at: Optional[str] = None
    last_commit: Optional[str] = None
    runbook_match: Optional[str] = None
    past_similar: Optional[str] = None
    is_recurring: bool = False
    recurrence_count: int = 0


class Incident(BaseModel):
    id: str
    title: str
    severity: str  # critical, warning, info
    service: str
    raw_alert: Optional[dict] = None
    status: IncidentStatus = IncidentStatus.RECEIVED
    findings: Optional[IncidentFindings] = None
    briefing_script: Optional[str] = None
    call_transcript: List[dict] = Field(default_factory=list)
    resolution: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
