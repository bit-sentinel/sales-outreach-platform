"""Shared search result types used by provider tools."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SearchResult:
    title: str
    url: str
    content: str
    source: str
    score: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)