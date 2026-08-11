# Training, Inference and Evaluator tracking audit

The three components share these genuine mechanics:

- disabled-by-default NoOp behavior;
- optional MLflow tracking URI and experiment selection;
- parent-run attachment;
- compact scalar metrics;
- searchable Storage URI and checksum references without blob uploads;
- `warn` failure containment and opt-in strict `error` behavior;
- completion or failure after the domain operation has published its result.

Training additionally has a live multi-step lifecycle, evaluation-suite metric
names, and historical publication backfill with idempotency. Inference prepares
base, adapter and pair-specific tags and records each completed Storage
publication. Evaluator flattens role-separated summaries after its terminal
manifest is written. Those payload decisions remain in their components.

Observability therefore owns only the backend/session mechanics. Compatibility
wrappers in each component retain the existing public tracker/configuration
entry points while delegating export work here.
