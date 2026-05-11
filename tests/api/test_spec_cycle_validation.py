"""API test: POST /v1/specs with a cyclic causal graph must return 422 (item 3.3)."""

from __future__ import annotations

_CYCLIC_YAML = """\
domain:
  name: test_cycle_domain
  description: Cycle detection test spec
  version: "1.0.0"

variables:
  decisions:
    - name: price
      description: Price per unit
      unit: EUR
      bounds:
        min: 10
        max: 50
        steps: 10
      default: 30.0
  intermediate: []
  targets: []

causal_relationships:
  - from: price
    to: demand
    type: causal
    description: price drives demand
  - from: demand
    to: price
    type: causal
    description: demand drives price back (cycle!)

constraints: []
simulation:
  monte_carlo_runs: 100
  noise_std: 0.05
optimization:
  target: profit
  method: grid_search
  decision_variables: [price]
  fixed_variables: {}
business_parameters: {}
"""


def test_create_spec_with_cycle_returns_422(client) -> None:
    response = client.post(
        "/v1/specs",
        json={"yaml_content": _CYCLIC_YAML, "description": "cyclic spec"},
    )
    assert response.status_code == 422
    detail = response.json().get("detail", "")
    assert "cycle" in detail.lower()
