"""High-fidelity demonstrative point-mass UAS mission simulation."""

from __future__ import annotations

from de2sim.simulation.schema import SimulationASOTFacts

from ._engine import simulate


def run_high_fidelity(facts: SimulationASOTFacts, scenario: dict) -> dict:
    """Run the deterministic higher-fidelity point-mass model."""
    return simulate(facts, scenario, "high")
