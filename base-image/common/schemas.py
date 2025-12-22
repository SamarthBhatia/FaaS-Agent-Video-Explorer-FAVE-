"""Pydantic models shared across FAVE functions."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ArtifactRef(BaseModel):
    type: str
    uri: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StageMetrics(BaseModel):
    duration_ms: int
    memory_limit_mb: int
    cold_start: bool = False
    cost_unit: Optional[float] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class StagePayload(BaseModel):
    request_id: str
    stage: str
    input_uri: str
    output_hint: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    fanout: Dict[str, Any] = Field(default_factory=dict)


class StageResult(BaseModel):
    request_id: str
    stage: str
    outputs: List[ArtifactRef] = Field(default_factory=list)
    metrics: StageMetrics
    status: str = "success"
    message: Optional[str] = None


class OrchestratorRequest(BaseModel):
    video_uri: str
    query: Optional[str] = None
    profile: str = "default"
    metadata: Dict[str, Any] = Field(default_factory=dict)
