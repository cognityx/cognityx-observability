# Cognityx Observability

Cognityx services create valuable results and also need a consistent record of
what happened while creating them. This repository provides that record. The
record is called observability: structured events, scalar measurements, and
links to authoritative artifacts.

```text
Cognityx Resource creates governance and execution identity
                         ↓
Domain component performs work and publishes to Storage
                         ↓
Observability exports compact events, metrics and Storage links
```

The default exporter does nothing, so adopting the package does not require an
external service. Optional MLflow and structured JSON logging exporters use the
same session lifecycle. See [architecture](architecture.md), [contracts](contracts.md),
and the [tracking migration audit](migration-audit.md).
