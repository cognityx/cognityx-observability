"""Safe lifecycle wrapper over an observation exporter."""

from __future__ import annotations

import warnings
from collections.abc import Iterable, Mapping
from typing import Any

from cognityx_observability.contracts import (
    ArtifactReference,
    MetricObservation,
    ObservationContext,
    ObservationEvent,
    ObservationResult,
)
from cognityx_observability.exporters import ObservationExporter


class ObservationSession:
    """Record one operation while containing optional exporter failures."""

    def __init__(
        self,
        context: ObservationContext,
        exporter: ObservationExporter,
        *,
        failure_policy: str = "warn",
    ) -> None:
        if failure_policy not in {"warn", "error"}:
            raise ValueError("failure_policy must be warn or error")
        self.context = context
        self.exporter = exporter
        self.failure_policy = failure_policy
        self._disabled = False
        self._result = ObservationResult(
            status="not_started",
            backend=exporter.backend,
        )

    @property
    def result(self) -> ObservationResult:
        return self._result

    def public_identity(self) -> dict[str, Any]:
        return {
            "context": self.context.public_identity(),
            "exporter": dict(self.exporter.public_identity()),
            "failure_policy": self.failure_policy,
        }

    def _failed(self, exc: Exception) -> ObservationResult:
        if self.failure_policy == "error":
            raise exc
        warnings.warn(
            f"Observability export failed: {exc}",
            RuntimeWarning,
            stacklevel=3,
        )
        self._disabled = True
        self._result = ObservationResult(
            status="failed_warning",
            backend=self.exporter.backend,
            external_run_id=self._result.external_run_id,
            message=str(exc),
        )
        return self._result

    def start(self) -> ObservationResult:
        try:
            self._result = self.exporter.start(self.context)
        except Exception as exc:
            return self._failed(exc)
        if self._result.status in {"disabled", "already_tracked"}:
            self._disabled = True
        return self._result

    def event(
        self,
        name: str,
        *,
        attributes: Mapping[str, Any] | None = None,
        timestamp: str | None = None,
    ) -> None:
        if self._disabled:
            return
        event = (
            ObservationEvent(
                name=name, timestamp=timestamp, attributes=attributes or {}
            )
            if timestamp is not None
            else ObservationEvent(name=name, attributes=attributes or {})
        )
        try:
            self.exporter.event(self.context, event)
        except Exception as exc:
            self._failed(exc)

    def metric(
        self,
        name: str,
        value: float,
        *,
        step: int | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        if self._disabled:
            return
        metric = MetricObservation(
            name=name,
            value=value,
            step=step,
            attributes=attributes or {},
        )
        try:
            self.exporter.metric(self.context, metric)
        except Exception as exc:
            self._failed(exc)

    def metrics(
        self,
        values: Mapping[str, Any],
        *,
        step: int | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        for name, value in values.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                self.metric(
                    str(name),
                    float(value),
                    step=step,
                    attributes=attributes,
                )

    def artifact(self, artifact: ArtifactReference) -> None:
        if self._disabled:
            return
        try:
            self.exporter.artifact(self.context, artifact)
        except Exception as exc:
            self._failed(exc)

    def artifacts(self, artifacts: Iterable[ArtifactReference]) -> None:
        for artifact in artifacts:
            self.artifact(artifact)

    def finish(
        self,
        status: str = "completed",
        *,
        attributes: Mapping[str, Any] | None = None,
    ) -> ObservationResult:
        if self._disabled:
            return self._result
        try:
            self._result = self.exporter.finish(
                self.context,
                status,
                attributes or {},
            )
        except Exception as exc:
            return self._failed(exc)
        self._disabled = True
        return self._result

    def fail(
        self,
        error: BaseException | str,
        *,
        attributes: Mapping[str, Any] | None = None,
    ) -> ObservationResult:
        if self._disabled:
            return self._result
        try:
            self._result = self.exporter.fail(
                self.context,
                error,
                attributes or {},
            )
        except Exception as exc:
            return self._failed(exc)
        self._disabled = True
        return self._result
