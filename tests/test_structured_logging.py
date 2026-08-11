from __future__ import annotations

import json
import logging

from cognityx_observability import (
    ObservationContext,
    ObservationSession,
    StructuredLoggingExporter,
)


def test_structured_logging_carries_correlation_and_redacts_secrets(caplog) -> None:
    logger = logging.getLogger("cognityx.test.observability")
    session = ObservationSession(
        ObservationContext(
            "auth",
            "audit",
            context_id="ctx-1",
            run_id="run-1",
            correlation_id="correlation-1",
            attributes={"api_token": "do-not-log", "tenant": "tenant-1"},
        ),
        StructuredLoggingExporter(logger=logger),
    )

    with caplog.at_level(logging.INFO, logger=logger.name):
        session.start()
        session.event(
            "authorization.denied",
            attributes={"password": "secret", "resource": "document-1"},
        )
        session.finish()

    documents = [json.loads(record.message) for record in caplog.records]
    event = next(item for item in documents if item["kind"] == "event")
    assert event["context"]["correlation_id"] == "correlation-1"
    assert event["context"]["attributes"]["api_token"] == "[REDACTED]"
    assert event["payload"]["attributes"]["password"] == "[REDACTED]"
    assert event["payload"]["attributes"]["resource"] == "document-1"
