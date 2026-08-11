# Architecture and ownership

`ObservationSession` is the shared lifecycle. An exporter receives start,
event, metric, artifact-reference, finish and failure calls. The session applies
the configured `warn` or `error` failure policy.

Cognityx Resource owns stable tenant, project, workspace and principal context,
plus execution `run_id` and `correlation_id`. Observability reuses those values;
it does not copy or redefine Resource context.

Experiment, hypothesis, research-question, treatment and seed values may appear
as ordinary observation attributes. They do not become Resource governance
identity, and Observability does not interpret their scientific meaning.

Cognityx Storage remains authoritative. An `ArtifactReference` is only a URI,
checksum, schema and role used for search and correlation. Exporters do not
upload the referenced bytes.
