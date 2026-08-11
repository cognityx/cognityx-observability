from __future__ import annotations

import pytest
from cognityx_resource import ExecutionContext, ResourceContext

from cognityx_observability import (
    ArtifactReference,
    MetricObservation,
    ObservationContext,
)


def test_resource_execution_context_is_reused_without_research_identity_leak() -> None:
    resource = ResourceContext(
        tenant_id="tenant",
        project_id="project",
        workspace_id="workspace",
        principal_id="researcher",
    )
    execution = ExecutionContext.create(
        resource,
        run_id="run-1",
        correlation_id="correlation-1",
    )
    observation = ObservationContext.from_execution_context(
        execution,
        component="training",
        operation="optimize",
        attributes={"experiment_id": "exp-1", "seed": 11},
    )

    assert observation.context_id == resource.context_id
    assert observation.run_id == "run-1"
    assert observation.correlation_id == "correlation-1"
    assert observation.attributes["experiment_id"] == "exp-1"
    assert "experiment_id" not in resource.scopes


def test_public_values_validate_required_and_scalar_fields() -> None:
    assert ArtifactReference("manifest", "storage://manifest").to_dict() == {
        "name": "manifest",
        "uri": "storage://manifest",
    }
    assert MetricObservation("loss", 0.5, step=2).value == 0.5
    with pytest.raises(ValueError, match="finite"):
        MetricObservation("loss", float("nan"))
    with pytest.raises(ValueError, match="component"):
        ObservationContext("", "run")
