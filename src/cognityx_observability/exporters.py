"""Observation exporter protocol and built-in implementations."""

from __future__ import annotations

import importlib
import json
import logging
import re
from collections.abc import Mapping
from typing import Any, Protocol

from cognityx_observability.contracts import (
    ArtifactReference,
    MetricObservation,
    ObservationContext,
    ObservationEvent,
    ObservationResult,
)

_SECRET_PARTS = (
    "authorization",
    "credential",
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
)


class ObservationExporter(Protocol):
    """Small backend contract for one observation session."""

    backend: str

    def public_identity(self) -> Mapping[str, Any]: ...

    def start(self, context: ObservationContext) -> ObservationResult: ...

    def event(self, context: ObservationContext, event: ObservationEvent) -> None: ...

    def metric(
        self, context: ObservationContext, metric: MetricObservation
    ) -> None: ...

    def artifact(
        self,
        context: ObservationContext,
        artifact: ArtifactReference,
    ) -> None: ...

    def finish(
        self,
        context: ObservationContext,
        status: str,
        attributes: Mapping[str, Any],
    ) -> ObservationResult: ...

    def fail(
        self,
        context: ObservationContext,
        error: BaseException | str,
        attributes: Mapping[str, Any],
    ) -> ObservationResult: ...


class NoOpExporter:
    """Default exporter that performs no writes."""

    backend = "none"
    _result = ObservationResult(status="disabled", backend=backend)

    def public_identity(self) -> Mapping[str, Any]:
        return {"backend": self.backend}

    def start(self, context: ObservationContext) -> ObservationResult:
        del context
        return self._result

    def event(self, context: ObservationContext, event: ObservationEvent) -> None:
        del context, event

    def metric(self, context: ObservationContext, metric: MetricObservation) -> None:
        del context, metric

    def artifact(
        self,
        context: ObservationContext,
        artifact: ArtifactReference,
    ) -> None:
        del context, artifact

    def finish(
        self,
        context: ObservationContext,
        status: str,
        attributes: Mapping[str, Any],
    ) -> ObservationResult:
        del context, status, attributes
        return self._result

    def fail(
        self,
        context: ObservationContext,
        error: BaseException | str,
        attributes: Mapping[str, Any],
    ) -> ObservationResult:
        del context, error, attributes
        return self._result


class StructuredLoggingExporter:
    """Write one canonical JSON log record for every observation action."""

    backend = "structured_logging"

    def __init__(
        self,
        *,
        logger: logging.Logger | None = None,
        level: int = logging.INFO,
    ) -> None:
        self.logger = logger or logging.getLogger("cognityx.observability")
        self.level = level

    def public_identity(self) -> Mapping[str, Any]:
        return {
            "backend": self.backend,
            "logger": self.logger.name,
            "level": self.level,
        }

    def _write(
        self,
        kind: str,
        context: ObservationContext,
        payload: Mapping[str, Any],
    ) -> None:
        document = {
            "schema": "cognityx.observability.log/v1",
            "kind": kind,
            "context": {
                **context.public_identity(),
                "attributes": _safe_value(context.attributes),
            },
            "payload": _safe_value(payload),
        }
        self.logger.log(
            self.level,
            json.dumps(document, sort_keys=True, separators=(",", ":")),
        )

    def start(self, context: ObservationContext) -> ObservationResult:
        self._write("session_started", context, {})
        return ObservationResult(status="started", backend=self.backend)

    def event(self, context: ObservationContext, event: ObservationEvent) -> None:
        self._write(
            "event",
            context,
            {
                "name": event.name,
                "timestamp": event.timestamp,
                "attributes": dict(event.attributes),
            },
        )

    def metric(self, context: ObservationContext, metric: MetricObservation) -> None:
        self._write(
            "metric",
            context,
            {
                "name": metric.name,
                "value": metric.value,
                "step": metric.step,
                "attributes": dict(metric.attributes),
            },
        )

    def artifact(
        self,
        context: ObservationContext,
        artifact: ArtifactReference,
    ) -> None:
        self._write("artifact_reference", context, artifact.to_dict())

    def finish(
        self,
        context: ObservationContext,
        status: str,
        attributes: Mapping[str, Any],
    ) -> ObservationResult:
        self._write("session_finished", context, {"status": status, **attributes})
        return ObservationResult(status=status, backend=self.backend)

    def fail(
        self,
        context: ObservationContext,
        error: BaseException | str,
        attributes: Mapping[str, Any],
    ) -> ObservationResult:
        self._write(
            "session_failed",
            context,
            {
                "error_type": type(error).__name__,
                "error": str(error),
                **attributes,
            },
        )
        return ObservationResult(status="failed", backend=self.backend)


class MLflowExporter:
    """Index compact observations and Storage references without copying blobs."""

    backend = "mlflow"

    def __init__(
        self,
        *,
        experiment_name: str,
        tracking_uri: str | None = None,
        run_name: str | None = None,
        mlflow_module: Any | None = None,
    ) -> None:
        if not experiment_name.strip():
            raise ValueError("experiment_name must be non-empty")
        if mlflow_module is None:
            try:
                selected = importlib.import_module("mlflow")
            except ImportError as exc:
                raise RuntimeError(
                    "MLflow export requires cognityx-observability[mlflow]"
                ) from exc
        else:
            selected = mlflow_module
        self.mlflow = selected
        self.experiment_name = experiment_name
        self.tracking_uri = tracking_uri
        self.run_name = run_name
        self._active = False
        self._already_tracked = False
        self._external_run_id: str | None = None
        self._event_index = 0

    def public_identity(self) -> Mapping[str, Any]:
        return {
            "backend": self.backend,
            "experiment_name": self.experiment_name,
            "run_name": self.run_name,
        }

    def _client(self) -> Any | None:
        client_type = getattr(
            getattr(self.mlflow, "tracking", None), "MlflowClient", None
        )
        if client_type is None:
            return None
        try:
            return client_type(tracking_uri=self.tracking_uri)
        except TypeError:
            return client_type()

    def _existing_run(self, idempotency_key: str | None) -> str | None:
        if not idempotency_key:
            return None
        client = self._client()
        if client is None:
            return None
        experiment = client.get_experiment_by_name(self.experiment_name)
        if experiment is None:
            return None
        escaped = idempotency_key.replace("'", "\\'")
        runs = client.search_runs(
            [experiment.experiment_id],
            filter_string=(f"tags.`cognityx.idempotency_key` = '{escaped}'"),
            max_results=1,
        )
        return str(runs[0].info.run_id) if runs else None

    def start(self, context: ObservationContext) -> ObservationResult:
        if self._active:
            raise RuntimeError("observation run is already active")
        if self.tracking_uri:
            self.mlflow.set_tracking_uri(self.tracking_uri)
        self.mlflow.set_experiment(self.experiment_name)
        existing = self._existing_run(context.idempotency_key)
        if existing:
            self._already_tracked = True
            self._external_run_id = existing
            return ObservationResult(
                status="already_tracked",
                backend=self.backend,
                external_run_id=existing,
            )
        tags = _context_tags(context)
        active = self.mlflow.start_run(
            run_name=self.run_name or f"{context.component}-{context.operation}",
            tags=tags,
        )
        self._external_run_id = str(getattr(active.info, "run_id"))
        self._active = True
        return ObservationResult(
            status="started",
            backend=self.backend,
            external_run_id=self._external_run_id,
        )

    def event(self, context: ObservationContext, event: ObservationEvent) -> None:
        del context
        if not self._active:
            return
        self._event_index += 1
        name = _segment(event.name)
        value = json.dumps(
            {
                "timestamp": event.timestamp,
                "attributes": _safe_value(event.attributes),
            },
            sort_keys=True,
            separators=(",", ":"),
        )[:5000]
        self.mlflow.set_tag(f"cognityx.event.{self._event_index}.{name}", value)

    def metric(self, context: ObservationContext, metric: MetricObservation) -> None:
        del context
        if not self._active:
            return
        if metric.step is None:
            self.mlflow.log_metric(metric.name, metric.value)
        else:
            self.mlflow.log_metric(metric.name, metric.value, step=metric.step)

    def artifact(
        self,
        context: ObservationContext,
        artifact: ArtifactReference,
    ) -> None:
        del context
        if not self._active:
            return
        name = _segment(artifact.name)
        tags = {f"cognityx.storage.{name}.uri": artifact.uri[:5000]}
        if artifact.checksum:
            tags[f"cognityx.storage.{name}.checksum"] = artifact.checksum
        if artifact.schema:
            tags[f"cognityx.storage.{name}.schema"] = artifact.schema
        if artifact.role:
            tags[f"cognityx.storage.{name}.role"] = artifact.role
        self.mlflow.set_tags(tags)

    def finish(
        self,
        context: ObservationContext,
        status: str,
        attributes: Mapping[str, Any],
    ) -> ObservationResult:
        del context
        if self._already_tracked:
            return ObservationResult(
                status="already_tracked",
                backend=self.backend,
                external_run_id=self._external_run_id,
            )
        if not self._active:
            raise RuntimeError("no active observation run to finish")
        self.mlflow.set_tags(
            {
                "cognityx.status": status,
                **_attribute_tags("cognityx.final", attributes),
            }
        )
        mlflow_status = (
            "FINISHED"
            if status in {"completed", "finished", "success"}
            else status.upper()
        )
        self.mlflow.end_run(status=mlflow_status)
        self._active = False
        return ObservationResult(
            status="completed" if mlflow_status == "FINISHED" else status,
            backend=self.backend,
            external_run_id=self._external_run_id,
        )

    def fail(
        self,
        context: ObservationContext,
        error: BaseException | str,
        attributes: Mapping[str, Any],
    ) -> ObservationResult:
        del context
        if self._already_tracked:
            return ObservationResult(
                status="already_tracked",
                backend=self.backend,
                external_run_id=self._external_run_id,
            )
        if not self._active:
            return ObservationResult(
                status="not_started",
                backend=self.backend,
                external_run_id=self._external_run_id,
            )
        self.mlflow.set_tags(
            {
                "cognityx.failure.error_type": type(error).__name__,
                "cognityx.failure.error": str(error)[:5000],
                **_attribute_tags("cognityx.failure", attributes),
            }
        )
        self.mlflow.end_run(status="FAILED")
        self._active = False
        return ObservationResult(
            status="failed",
            backend=self.backend,
            external_run_id=self._external_run_id,
        )


def _context_tags(context: ObservationContext) -> dict[str, str]:
    tags = {
        "cognityx.component": context.component,
        "cognityx.operation": context.operation,
        "cognityx.context_id": context.context_id,
        "cognityx.run_id": context.run_id,
        "cognityx.correlation_id": context.correlation_id,
        "cognityx.idempotency_key": context.idempotency_key,
        "cognityx.artifacts_authority": "cognityx-storage",
    }
    if context.parent_run_id:
        tags["mlflow.parentRunId"] = context.parent_run_id
    selected = {key: str(value) for key, value in tags.items() if value is not None}
    selected.update(_attribute_tags("cognityx", context.attributes))
    return selected


def _attribute_tags(prefix: str, values: Mapping[str, Any]) -> dict[str, str]:
    tags: dict[str, str] = {}
    for key, value in values.items():
        if _secret_key(key):
            continue
        name = key if key.startswith("cognityx.") else f"{prefix}.{key}"
        safe = _safe_value(value)
        if isinstance(safe, (dict, list, tuple)):
            tags[name] = json.dumps(safe, sort_keys=True, default=str)[:5000]
        elif safe is not None:
            tags[name] = str(safe)[:5000]
    return tags


def _secret_key(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return any(part in lowered for part in _SECRET_PARTS)


def _safe_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _secret_key(str(key)) else _safe_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_safe_value(item) for item in value]
    return value


def _segment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("_.")[:120] or "item"
