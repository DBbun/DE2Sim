"""Low-fidelity deterministic UAS mission simulation."""

from __future__ import annotations

from de2sim.simulation.schema import SimulationASOTFacts

from ._engine import simulate


def run_low_fidelity(facts: SimulationASOTFacts, scenario: dict) -> dict:
    """Run the fixed-step low-fidelity point model."""
    return simulate(facts, scenario, "low")
