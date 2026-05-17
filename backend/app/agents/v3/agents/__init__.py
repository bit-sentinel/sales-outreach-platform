"""v3 collection agents — importing this package registers every agent."""

from app.agents.v3.agents import (  # noqa: F401
    identity, event_fit, pressure, synthesis, intelligence,
)
