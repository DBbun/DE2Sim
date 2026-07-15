# DE2Sim Supported Inputs

This document describes the inputs supported by DE2Sim Phase 1B structured
artifact parsing. Phase 1B is conservative and dependency-free. It does not
claim complete SysML v2 support, PDF parsing, XLSX parsing, binary CAD parsing,
simulation generation, Godot export, packaging, or deployment.

## Phase 1B Parsed Formats

Requirements:

- CSV with common aliases such as `id`, `requirement_id`, `req_id`, `title`,
  `name`, `text`, `requirement`, `description`, `verification_method`,
  `verification`, and `priority`
- JSON as a top-level list, `{"requirements": [...]}`, or a single requirement
  object
- TXT and Markdown as one requirement per nonempty line, or headings followed by
  requirement text
- A simple YAML subset containing scalar mappings or simple lists

Parameters:

- CSV with common parameter columns such as `id`, `parameter_id`, `param_id`,
  `name`, `parameter`, `param`, `value`, `default`, `nominal`, `unit`, `units`,
  `min`, `minimum`, `max`, `maximum`, and `description`
- JSON as a top-level mapping, list, or `{"parameters": [...]}`
- TXT and Markdown assignment lines such as `mass = 12`
- A simple YAML subset containing scalar mappings or simple lists

SysML v2:

- Textual `.sysml` files using a narrow line-oriented subset:
  - `package`
  - `part def`
  - `part`
  - `attribute def`
  - `attribute`
  - `port def`
  - `port`
  - `requirement def`
  - `requirement`
  - `action def`
  - `action`
  - `connect`
  - `satisfy`
  - `verify`
- `.sysml.json` files with top-level lists, `{"elements": [...]}`,
  `{"relationships": [...]}`, or objects containing explicit fields such as
  `kind`, `type`, `id`, `name`, `owner`, `source`, `target`, `value`, `unit`,
  and `description`

Physical models:

- TXT and Markdown lines with explicit equations such as `name = expression`,
  `equation: expression`, or `formula: expression`
- JSON objects or lists containing explicit `equation` or `formula` fields
- A simple YAML subset containing explicit equation/formula fields

## Deferred Formats

The following formats are listed in `deferred_files` rather than parsed in
Phase 1B:

- PDF
- DOCX
- XLSX
- Geometry files such as GLB, GLTF, OBJ, and STL
- Unsupported binary or unknown formats

Geometry files remain references only with `parser_status` set to
`referenced_not_parsed`.

## YAML Subset

The YAML reader intentionally supports only safe, dependency-free structures:

- scalar `key: value` mappings
- simple lists introduced by `-`
- no anchors
- no aliases
- no custom tags
- no arbitrary object construction

YAML outside this subset produces controlled warnings and no source content is
executed.
