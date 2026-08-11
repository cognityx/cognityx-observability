# Cognityx Observability

`cognityx-observability` records what happened while another Cognityx component
did its work. It provides one small session for events, scalar measurements,
and references to artifacts that remain owned by their producing component.

Its place in the application is:

```text
Resource governance and execution identity
                 ↓
Training / Inference / Evaluator / Jobs / Experiments
                 ↓ observations about what happened
          Cognityx Observability
          ├── structured JSON logs
          ├── optional MLflow index
          └── future exporter protocol

Scientific artifacts ── authoritative bytes ──> Cognityx Storage
```

Observability does not own models, adapters, predictions, evaluation scores,
hypotheses, treatments, or authentication decisions. Cognityx Storage remains
the authoritative evidence store. MLflow is a searchable secondary index and
receives compact metrics and Storage references, not copied artifact blobs.

```python
from cognityx_observability import (
    ArtifactReference,
    ObservationContext,
    ObservabilityConfig,
    build_session,
)

context = ObservationContext(
    component="training",
    operation="optimize",
    run_id="run-1",
    correlation_id="correlation-1",
)
session = build_session(context, ObservabilityConfig())
session.start()
session.metric("train_loss", 0.25, step=10)
session.artifact(ArtifactReference("manifest", "storage://run/manifest.json"))
session.finish()
```

## Development

```bash
uv sync --locked --all-extras --dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run mkdocs build --strict
uv build
```
