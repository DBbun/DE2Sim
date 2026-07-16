# DE2Sim Simulation Model

Phase 5A builds deterministic UAS mission simulations from an approved ASOT.
It requires the approved `Low Battery Return-to-Base` behavior, the
source-derived `ReturnToBase` action, numeric `battery_threshold`,
`battery_capacity`, and `max_speed` parameters, linked requirements, and the
transition sequence:

```text
preflight -> mission_flight -> return_to_base -> landed
```

The return-to-base guard is the symbolic ASOT guard:

```text
battery_state <= battery_threshold
```

Scenario values are explicit inputs with value, unit, source classification,
and explanation. Default values are deterministic demonstration assumptions and
are not claimed to come from CAD, SysML, or authoritative engineering data.
The default waypoint distance and high-fidelity power assumptions are selected
so both fidelities reach the waypoint, loiter until the ASOT battery threshold
is crossed, invoke source-derived `ReturnToBase`, return home, and land with
positive battery reserve.

Low fidelity is a fixed two-dimensional kinematic point model: instant heading
changes, constant commanded speed capped by ASOT `max_speed`, no wind, no
acceleration dynamics, and fixed nominal power draw.

High fidelity is a demonstrative point-mass model: velocity state,
acceleration limit, constant wind disturbance, idle power, and speed-dependent
power draw. It is not flight-certified aerodynamics.

The battery update is fixed simulation logic based on:

```text
remaining_energy = battery_capacity - power_draw * time
```

No ASOT source equations are parsed or evaluated.

If usable battery energy reaches zero before landing, the simulation terminates
without inventing a new ASOT-approved state. The final telemetry row has zero
commanded speed and zero ground speed, emits `battery_depleted`, sets
`mission_completed = false`, uses terminal reason
`battery_depleted_before_landing`, and marks scenario feasibility as `fail`.
Requirement evaluation remains separate: a requirement can pass while a
demonstration scenario is infeasible.
