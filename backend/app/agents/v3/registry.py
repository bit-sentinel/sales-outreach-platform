"""Stage-indexed registry. Concrete agents self-register via @register_agent."""
from __future__ import annotations

from typing import Type

from app.agents.v3.base import BaseIntelligenceAgent

_REGISTRY: dict[str, list[Type[BaseIntelligenceAgent]]] = {}


def register_agent(cls: Type[BaseIntelligenceAgent]) -> Type[BaseIntelligenceAgent]:
    """Class decorator — registers a concrete agent under its declared stage."""
    if not getattr(cls, "stage", None):
        raise ValueError(f"{cls.__name__} must declare `stage`")
    _REGISTRY.setdefault(cls.stage, []).append(cls)
    return cls


def agents_for_stage(stage: str) -> list[Type[BaseIntelligenceAgent]]:
    return list(_REGISTRY.get(stage, []))
