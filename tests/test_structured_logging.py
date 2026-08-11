from __future__ import annotations

import json
import logging

from cognityx_observability import (
    ObservationContext,
    ObservationSession,
    StructuredLoggingExporter,
)


def test_structured_logging_carries_correlation_and_redacts_credentials(caplog) -> None:
    logger = logging.getLogger("cognityx.test.observability")
    session = ObservationSession(
        ObservationContext(
            "auth",
            "audit",
            context_id="ctx-1",
            run_id="run-1",
            correlation_id="correlation-1",
            attributes={
                "api_key": "do-not-log",
                "api_token": "do-not-log",
                "tenant": "tenant-1",
                "reproducibility": {
                    "tokenizer_revision": "tok-rev-1",
                    "tokenizer_checksum": "sha256:tokenizer",
                    "prompt_tokens": 21,
                    "completion_tokens": 8,
                    "token_budget": 512,
                    "access_token": "do-not-log",
                    "refresh_token": "do-not-log",
                },
            },
        ),
        StructuredLoggingExporter(logger=logger),
    )

    with caplog.at_level(logging.INFO, logger=logger.name):
        session.start()
        session.event(
            "authorization.denied",
            attributes={
                "Authorization": "Bearer do-not-log",
                "password": "do-not-log",
                "private_key": "do-not-log",
                "resource": "document-1",
            },
        )
        session.finish()

    documents = [json.loads(record.message) for record in caplog.records]
    event = next(item for item in documents if item["kind"] == "event")
    assert event["context"]["correlation_id"] == "correlation-1"
    context = event["context"]["attributes"]
    assert context["api_key"] == "[REDACTED]"
    assert context["api_token"] == "[REDACTED]"
    assert context["reproducibility"] == {
        "tokenizer_revision": "tok-rev-1",
        "tokenizer_checksum": "sha256:tokenizer",
        "prompt_tokens": 21,
        "completion_tokens": 8,
        "token_budget": 512,
        "access_token": "[REDACTED]",
        "refresh_token": "[REDACTED]",
    }
    assert event["payload"]["attributes"]["Authorization"] == "[REDACTED]"
    assert event["payload"]["attributes"]["password"] == "[REDACTED]"
    assert event["payload"]["attributes"]["private_key"] == "[REDACTED]"
    assert event["payload"]["attributes"]["resource"] == "document-1"
