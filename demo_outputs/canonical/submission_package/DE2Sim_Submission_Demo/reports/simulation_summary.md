# DE2Sim Phase 5A Simulation Summary

Simulation run ID: `simulation-run-737b9d34a81ba0b6`
ASOT title: DBbun-DE2Sim-DemoUAS-Geometry
Approved behavior: behavior-a7684a40e256a954

## Extracted ASOT Values
- battery_threshold: 20.0 percent
- battery_capacity: 4800.0 Wh
- max_speed: 25.0 m/s

## Demonstration Scenario Assumptions
- scenario_id: deterministic-demo-uAS-phase5a identifier (demonstration_assumption) - Stable deterministic demonstration scenario identifier.
- home_x_m: 0.0 m (demonstration_assumption) - Home position x coordinate for the demonstration scenario.
- home_y_m: 0.0 m (demonstration_assumption) - Home position y coordinate for the demonstration scenario.
- mission_waypoint_x_m: 36000.0 m (demonstration_assumption) - Mission waypoint x coordinate chosen to exercise return-to-base behavior while leaving landing reserve.
- mission_waypoint_y_m: 0.0 m (demonstration_assumption) - Mission waypoint y coordinate chosen to keep path interpretation simple.
- arrival_radius_m: 75.0 m (demonstration_assumption) - Arrival radius used for waypoint and home confirmation.
- initial_battery_percent: 100.0 percent (demonstration_assumption) - Initial state of charge for the demonstration run.
- nominal_power_draw_w: 1200.0 W (demonstration_assumption) - Low-fidelity constant power draw assumption.
- high_fidelity_idle_power_w: 1140.0 W (demonstration_assumption) - Idle power used by the demonstrative point-mass model.
- high_fidelity_speed_power_coefficient: 0.3 W/(m/s)^2 (demonstration_assumption) - Quadratic speed power coefficient for the demonstrative point-mass model.
- acceleration_limit_mps2: 2.0 m/s^2 (demonstration_assumption) - Acceleration limit used to smooth the high-fidelity velocity response.
- wind_x_mps: -2.0 m/s (demonstration_assumption) - Constant wind disturbance x component for the high-fidelity model.
- wind_y_mps: 0.5 m/s (demonstration_assumption) - Constant wind disturbance y component for the high-fidelity model.
- low_fidelity_time_step_s: 10.0 s (demonstration_assumption) - Fixed low-fidelity integration time step.
- high_fidelity_time_step_s: 2.0 s (demonstration_assumption) - Fixed high-fidelity integration time step.
- maximum_simulation_time_s: 20000.0 s (demonstration_assumption) - Deterministic safety limit for simulation termination.
- playback_seconds_per_simulation_second: 0.0025 s/s (demonstration_assumption) - Default viewer playback scale selected to show the complete demonstration mission in roughly 20 to 45 seconds.

## Low-Fidelity Result Summary
- landing_time_s: 12960.0
- minimum_battery_percent: 10.0
- battery_reserve_at_landing_percent: 10.0
- scenario_feasibility_status: pass

## High-Fidelity Result Summary
- landing_time_s: 13312.0
- minimum_battery_percent: 8.925479
- battery_reserve_at_landing_percent: 8.925479
- scenario_feasibility_status: pass

## Requirement Results
- low: low_battery_return=pass, maximum_speed=pass
- high: low_battery_return=pass, maximum_speed=pass

## Known Limitations
- The simulation engine produces deterministic low- and high-fidelity demonstrative point-mass results.
- High fidelity is a demonstrative point-mass model, not flight-certified aerodynamics.
- Scenario defaults are demonstration assumptions, not CAD, SysML, or authoritative engineering facts.
- The browser viewer plays back precomputed telemetry and does not recompute authoritative results.
- The browser viewer replays precomputed telemetry and is packaged as part of the integrated DE2Sim demonstration. No Godot export or flight-certified model is claimed.
