# DE2Sim Behavior Generation

Phase 4A creates behavior proposals for human review only. It does not generate
simulation code, Godot assets, executable scripts, or automatically approved
behaviors.

Run:

```text
python -m de2sim.cli.challenge_pipeline --engineering-package package.zip --output out --propose-behaviors
```

Outputs:

- `behavior_prompt.json`
- `behavior_proposals.json`
- `behavior_review.html`
- `behavior_generation_report.json`

The prompt includes relevant ASOT components, requirements, parameters with
units, explicit physical models, existing source-derived behaviors, provenance
references, JSON response instructions, and constraints against unsupported
values. It does not include unrelated source files or credentials.

The default `offline` provider is deterministic and labels candidates with
`generated_by = "offline_template"`. These candidates are demonstration
templates assembled from explicit ASOT evidence and are not generative-AI
output.

Optional `openai` and `anthropic` adapters read credentials only from
`OPENAI_API_KEY` and `ANTHROPIC_API_KEY`. If credentials or optional packages
are unavailable, the CLI reports a controlled error.
