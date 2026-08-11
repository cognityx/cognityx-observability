from __future__ import annotations

from collections.abc import Mapping

import pytest

from cognityx_observability import (
    ArtifactReference,
    NoOpExporter,
    ObservationContext,
    ObservationResult,
    ObservationSession,
)


def test_noop_session_is_disabled_and_safe() -> None:
    session = ObservationSession(
        ObservationContext("jobs", "replay"),
        NoOpExporter(),
    )

    assert session.start().status == "disabled"
    session.event("job.timeout")
    session.metric("jobs", 1)
    session.artifact(ArtifactReference("result", "storage://result"))
    assert session.finish().status == "disabled"


class RecordingExporter:
    backend = "recording"

    def __init__(self, *, broken: bool = False) -> None:
        self.broken = broken
        self.calls: list[tuple] = []

    def public_identity(self) -> Mapping[str, object]:
        return {"backend": self.backend}

    def start(self, context):
        self.calls.append(("start", context))
        return ObservationResult("started", self.backend, "external-1")

    def event(self, context, event):
        if self.broken:
            raise RuntimeError("offline")
        self.calls.append(("event", event))

    def metric(self, context, metric):
        self.calls.append(("metric", metric))

    def artifact(self, context, artifact):
        self.calls.append(("artifact", artifact))

    def finish(self, context, status, attributes):
        self.calls.append(("finish", status, dict(attributes)))
        return ObservationResult("completed", self.backend, "external-1")

    def fail(self, context, error, attributes):
        self.calls.append(("fail", str(error), dict(attributes)))
        return ObservationResult("failed", self.backend, "external-1")


def test_generic_lifecycle_records_events_metrics_artifacts_and_finish() -> None:
    exporter = RecordingExporter()
    session = ObservationSession(
        ObservationContext("training", "optimize"),
        exporter,
    )

    session.start()
    session.event("training.completed", attributes={"steps": 4})
    session.metrics({"loss": 0.2, "ignored": "text"}, step=4)
    session.artifacts([ArtifactReference("manifest", "storage://manifest")])
    result = session.finish(attributes={"storage_authoritative": True})

    assert result.status == "completed"
    assert [call[0] for call in exporter.calls] == [
        "start",
        "event",
        "metric",
        "artifact",
        "finish",
    ]


def test_warn_disables_export_and_error_policy_raises() -> None:
    warn = ObservationSession(
        ObservationContext("inference", "pair"),
        RecordingExporter(broken=True),
        failure_policy="warn",
    )
    warn.start()
    with pytest.warns(RuntimeWarning, match="Observability export failed"):
        warn.event("inference.adapter.loaded")
    assert warn.result.status == "failed_warning"
    assert warn.finish().status == "failed_warning"

    strict = ObservationSession(
        ObservationContext("inference", "pair"),
        RecordingExporter(broken=True),
        failure_policy="error",
    )
    strict.start()
    with pytest.raises(RuntimeError, match="offline"):
        strict.event("inference.adapter.loaded")
