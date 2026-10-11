# Content Pipeline (`content/`)

Manages the authoring, deterministic validation, review, and publishing of FLN teaching move cards and error rules.

## Directory Structure
- `sources/`: State FLN modules, UP teacher guides, NIPUN guidance docs (HUMAN INPUT).
- `moves/`: Versioned move cards stored as validated YAML files.
- `personas/`: Child persona specifications (grade, temperament, voice, initial misconceptions).
- `rules/`: Deterministic misconception bug rules written in Python with 100% test coverage.
- `schemas/`: JSON Schemas defining the structure of moves, personas, and rules.
- `pipeline/`: Automated validation engine and publishing scripts.
- `tests/`: Unit tests for moves, rules, and validators.
