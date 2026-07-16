# DE2Sim Behavior Approval

Phase 4A approval is explicit and human-controlled. The review page downloads a
decisions JSON file; it never modifies `asot.json` directly.

Run:

```text
python -m de2sim.cli.challenge_pipeline --output out --apply-behavior-decisions out/behavior_decisions.json
```

Outputs:

- `behavior_decisions.json`
- `asot_with_approved_behaviors.json`
- `behavior_approval_report.json`

Safeguards:

- every decision must reference an existing proposal ID
- duplicate and unknown proposal IDs are rejected
- only `approved` proposals enter the new ASOT
- rejected and needs-revision proposals remain report-only
- existing source-derived behaviors are preserved
- provider, model, prompt hash, source references, and approval decision metadata
  are retained
- ASOT validation is re-run after approved behaviors are added
- the original `asot.json` is never modified in place
