# Public contracts

- `ObservationContext` names a component and operation and can carry Resource
  execution IDs, an optional parent run, an idempotency key, and attributes.
- `ObservationEvent` is a timestamped fact with attributes.
- `MetricObservation` is a finite scalar value with an optional step.
- `ArtifactReference` points to an artifact owned elsewhere.
- `ObservationResult` reports non-authoritative export status.
- `ObservationExporter` is the backend protocol.
- `ObservationSession` provides the safe lifecycle.

The built-in exporters are `NoOpExporter`, `MLflowExporter`, and
`StructuredLoggingExporter`. Future OpenTelemetry, Prometheus-compatible, or
log-search exporters can implement the same protocol without changing domain
components.
