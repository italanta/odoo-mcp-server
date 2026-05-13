# AGENTS.md

Repository working notes for future coding agents.

## Non-negotiables

- Keep this project local-first. Do not introduce hosted relay requirements.
- Do not weaken write safety or approval boundaries.
- Respect transport compatibility:
  - Odoo 18 and below uses `xmlrpc`
  - Odoo 19 and above uses `json2`

## Commenting standard

- Add clear, intentional comments in all newly added non-trivial code.
- Prefer short comments that explain *why* a block exists, not obvious syntax.
- Keep comments especially strong in:
  - `src/mcp/odoo/connection/`
  - automation scripts under `scripts/`
  - safety and write governance paths

## Docs and install UX

- Keep setup docs practical and copy-paste friendly for macOS and Windows.
- When changing install flow, update docs in the same change set.
- Keep multi-client guidance aligned with generated artifacts in `dist/client-configs/`.

## Validation checklist before finishing

- Run focused tests for changed behavior.
- Regenerate client config snippets if manifest or generation logic changed.
- Check changed files for lint/syntax/errors.
