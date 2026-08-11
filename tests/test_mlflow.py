from __future__ import annotations

import pytest

from cognityx_observability import (
    ArtifactReference,
    MLflowExporter,
    ObservationContext,
    ObservationSession,
)


def test_real_mlflow_sqlite_parent_idempotency_metrics_events_and_references(
    tmp_path,
) -> None:
    mlflow = pytest.importorskip("mlflow")
    tracking_uri = f"sqlite:///{tmp_path / 'observability.db'}"
    experiment_name = "Observability integration"
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)
    with mlflow.start_run(run_name="parent") as parent:
        parent_run_id = parent.info.run_id

    context = ObservationContext(
        "evaluator",
        "evaluate_pair",
        context_id="ctx-1",
        run_id="run-1",
        correlation_id="correlation-1",
        parent_run_id=parent_run_id,
        idempotency_key="storage://evaluator/manifest.json",
        attributes={"experiment_id": "exp-1", "seed": 11},
    )
    first = ObservationSession(
        context,
        MLflowExporter(
            tracking_uri=tracking_uri,
            experiment_name=experiment_name,
            run_name="evaluator-run",
            mlflow_module=mlflow,
        ),
    )
    started = first.start()
    first.metric("grounded_correct_rate", 0.75)
    first.event("evaluation.completed", attributes={"records": 4})
    first.artifact(
        ArtifactReference(
            "evaluator_manifest",
            "storage://evaluator/manifest.json",
            checksum="sha256:abc",
            schema="cognityx.evaluator.run/v1",
            role="artifact",
        )
    )
    completed = first.finish()

    client = mlflow.tracking.MlflowClient(tracking_uri=tracking_uri)
    run = client.get_run(completed.external_run_id)
    assert started.status == "started"
    assert run.data.tags["mlflow.parentRunId"] == parent_run_id
    assert run.data.tags["cognityx.component"] == "evaluator"
    assert run.data.tags["cognityx.experiment_id"] == "exp-1"
    assert run.data.tags["cognityx.storage.evaluator_manifest.uri"].startswith(
        "storage://"
    )
    assert run.data.metrics["grounded_correct_rate"] == 0.75
    assert any(key.startswith("cognityx.event.") for key in run.data.tags)

    repeated = ObservationSession(
        context,
        MLflowExporter(
            tracking_uri=tracking_uri,
            experiment_name=experiment_name,
            mlflow_module=mlflow,
        ),
    ).start()
    assert repeated.status == "already_tracked"
    assert repeated.external_run_id == completed.external_run_id


def test_public_identity_does_not_expose_tracking_uri_or_arbitrary_secrets() -> None:
    exporter = MLflowExporter(
        tracking_uri="https://user:secret@example.invalid",
        experiment_name="safe",
        mlflow_module=object(),
    )
    session = ObservationSession(
        ObservationContext(
            "training",
            "optimize",
            attributes={"token": "secret"},
        ),
        exporter,
    )

    rendered = repr(session.public_identity())
    assert "user:secret" not in rendered
    assert "attributes" not in session.public_identity()["context"]


def test_mlflow_preserves_token_metrics_and_redacts_only_credentials(tmp_path) -> None:
    mlflow = pytest.importorskip("mlflow")
    tracking_uri = f"sqlite:///{tmp_path / 'credential-policy.db'}"
    experiment_name = "Credential policy"
    context = ObservationContext(
        "inference",
        "generate",
        idempotency_key="credential-policy-test",
        attributes={
            "tokenizer_revision": "tok-rev-1",
            "tokenizer_checksum": "sha256:tokenizer",
            "prompt_tokens": 21,
            "completion_tokens": 8,
            "token_budget": 512,
            "access_token": "do-not-log",
            "refresh_token": "do-not-log",
            "api_key": "do-not-log",
            "Authorization": "Bearer do-not-log",
            "password": "do-not-log",
            "private_key": "do-not-log",
            "nested": {
                "prompt_tokens": 21,
                "auth_token": "do-not-log",
            },
        },
    )
    session = ObservationSession(
        context,
        MLflowExporter(
            tracking_uri=tracking_uri,
            experiment_name=experiment_name,
            mlflow_module=mlflow,
        ),
    )

    started = session.start()
    session.metric("prompt_tokens", 21)
    completed = session.finish()

    run = mlflow.tracking.MlflowClient(tracking_uri=tracking_uri).get_run(
        completed.external_run_id
    )
    assert started.status == "started"
    assert run.data.tags["cognityx.tokenizer_revision"] == "tok-rev-1"
    assert run.data.tags["cognityx.tokenizer_checksum"] == "sha256:tokenizer"
    assert run.data.tags["cognityx.prompt_tokens"] == "21"
    assert run.data.tags["cognityx.completion_tokens"] == "8"
    assert run.data.tags["cognityx.token_budget"] == "512"
    assert run.data.metrics["prompt_tokens"] == 21
    assert all(
        credential not in run.data.tags
        for credential in (
            "cognityx.access_token",
            "cognityx.refresh_token",
            "cognityx.api_key",
            "cognityx.Authorization",
            "cognityx.password",
            "cognityx.private_key",
        )
    )
    assert "do-not-log" not in run.data.tags["cognityx.nested"]
    assert "[REDACTED]" in run.data.tags["cognityx.nested"]
