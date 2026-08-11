"""Provider-neutral public observation values."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any

from cognityx_resource import ExecutionContext, ResourceContext


def _attributes(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(
        isinstance(key, str) and key.strip() for key in value
    ):
        raise ValueError("attributes must be a mapping with non-empty string keys")
    return MappingProxyType(dict(value))


def _required(value: str, name: str) -> str:
    selected = str(value).strip()
    if not selected:
        raise ValueError(f"{name} must be a non-empty string")
    return selected


@dataclass(frozen=True, slots=True)
class ObservationContext:
    """Identity and attributes shared by one observed operation."""

    component: str
    operation: str
    context_id: str | None = None
    run_id: str | None = None
    correlation_id: str | None = None
    parent_run_id: str | None = None
    idempotency_key: str | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "component", _required(self.component, "component"))
        object.__setattr__(self, "operation", _required(self.operation, "operation"))
        object.__setattr__(self, "attributes", _attributes(self.attributes))

    @classmethod
    def from_execution_context(
        cls,
        execution: ExecutionContext,
        *,
        component: str,
        operation: str,
        parent_run_id: str | None = None,
        idempotency_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> ObservationContext:
        """Reuse Resource execution identity without changing its ownership."""
        return cls(
            component=component,
            operation=operation,
            context_id=execution.context_id,
            run_id=execution.run_id,
            correlation_id=execution.correlation_id,
            parent_run_id=parent_run_id,
            idempotency_key=idempotency_key,
            attributes=attributes or {},
        )

    @classmethod
    def from_resource_context(
        cls,
        resource: ResourceContext,
        *,
        component: str,
        operation: str,
        run_id: str | None = None,
        correlation_id: str | None = None,
        parent_run_id: str | None = None,
        idempotency_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> ObservationContext:
        """Ask Resource to create execution identity, then build an observation."""
        execution = ExecutionContext.create(
            resource,
            run_id=run_id,
            correlation_id=correlation_id,
        )
        return cls.from_execution_context(
            execution,
            component=component,
            operation=operation,
            parent_run_id=parent_run_id,
            idempotency_key=idempotency_key,
            attributes=attributes,
        )

    def public_identity(self) -> dict[str, Any]:
        """Return stable non-secret identity fields without arbitrary attributes."""
        return {
            key: value
            for key, value in {
                "component": self.component,
                "operation": self.operation,
                "context_id": self.context_id,
                "run_id": self.run_id,
                "correlation_id": self.correlation_id,
                "parent_run_id": self.parent_run_id,
                "idempotency_key": self.idempotency_key,
            }.items()
            if value is not None
        }


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    """A searchable pointer to an artifact stored by its owning component."""

    name: str
    uri: str
    checksum: str | None = None
    schema: str | None = None
    role: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _required(self.name, "name"))
        object.__setattr__(self, "uri", _required(self.uri, "uri"))

    def to_dict(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in {
                "name": self.name,
                "uri": self.uri,
                "checksum": self.checksum,
                "schema": self.schema,
                "role": self.role,
            }.items()
            if value is not None
        }


@dataclass(frozen=True, slots=True)
class ObservationEvent:
    """One timestamped fact reported by an observed operation."""

    name: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _required(self.name, "name"))
        object.__setattr__(self, "timestamp", _required(self.timestamp, "timestamp"))
        object.__setattr__(self, "attributes", _attributes(self.attributes))


@dataclass(frozen=True, slots=True)
class MetricObservation:
    """One compact scalar metric with optional ordering and attributes."""

    name: str
    value: float
    step: int | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _required(self.name, "name"))
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise ValueError("metric value must be a numeric scalar")
        selected = float(self.value)
        if not math.isfinite(selected):
            raise ValueError("metric value must be finite")
        object.__setattr__(self, "value", selected)
        if self.step is not None and self.step < 0:
            raise ValueError("metric step must be non-negative")
        object.__setattr__(self, "attributes", _attributes(self.attributes))


@dataclass(frozen=True, slots=True)
class ObservationResult:
    """Non-authoritative status returned by an observation exporter."""

    status: str
    backend: str
    external_run_id: str | None = None
    message: str | None = None
