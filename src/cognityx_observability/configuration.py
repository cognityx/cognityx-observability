"""Validated configuration and composition helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from cognityx_observability.contracts import ObservationContext
from cognityx_observability.exporters import (
    MLflowExporter,
    NoOpExporter,
    ObservationExporter,
    StructuredLoggingExporter,
)
from cognityx_observability.session import ObservationSession


@dataclass(frozen=True, slots=True)
class ObservabilityConfig:
    """Backend-neutral settings with Storage remaining authoritative."""

    backend: str = "none"
    tracking_uri: str | None = None
    experiment_name: str = "cognityx"
    run_name: str | None = None
    failure_policy: str = "warn"
    logger_name: str = "cognityx.observability"
    log_level: int = logging.INFO

    def __post_init__(self) -> None:
        if self.backend not in {"none", "mlflow", "structured_logging"}:
            raise ValueError("backend must be none, mlflow, or structured_logging")
        if self.failure_policy not in {"warn", "error"}:
            raise ValueError("failure_policy must be warn or error")
        if self.backend == "mlflow" and not self.experiment_name.strip():
            raise ValueError("MLflow requires experiment_name")

    def public_identity(self) -> dict[str, Any]:
        """Return safe configuration identity without a possibly credentialed URI."""
        return {
            "backend": self.backend,
            "experiment_name": self.experiment_name,
            "run_name": self.run_name,
            "failure_policy": self.failure_policy,
            "logger_name": self.logger_name,
            "log_level": self.log_level,
        }


def build_exporter(
    config: ObservabilityConfig,
    *,
    mlflow_module: Any | None = None,
    logger: logging.Logger | None = None,
) -> ObservationExporter:
    if config.backend == "mlflow":
        return MLflowExporter(
            experiment_name=config.experiment_name,
            tracking_uri=config.tracking_uri,
            run_name=config.run_name,
            mlflow_module=mlflow_module,
        )
    if config.backend == "structured_logging":
        return StructuredLoggingExporter(
            logger=logger or logging.getLogger(config.logger_name),
            level=config.log_level,
        )
    return NoOpExporter()


def build_session(
    context: ObservationContext,
    config: ObservabilityConfig | None = None,
    *,
    mlflow_module: Any | None = None,
    logger: logging.Logger | None = None,
) -> ObservationSession:
    selected = config or ObservabilityConfig()
    return ObservationSession(
        context,
        build_exporter(selected, mlflow_module=mlflow_module, logger=logger),
        failure_policy=selected.failure_policy,
    )
