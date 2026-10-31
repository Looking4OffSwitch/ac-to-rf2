# Work items

## Shorten README to a conventional GitHub quick start

- Keep the purpose, essential requirements, activated-venv setup, one conversion
  example, content-rights notice, and links to further documentation.
- Aim for approximately 100 lines or fewer and a useful first screen.
- Move the pipeline, troubleshooting, packaging walkthrough, performance history,
  and detailed limitations to focused `docs/` pages or `NOTES.md`.
- Preserve the protected-track guidance and verify all moved links and commands.

Requested 2026-10-31. Tracked here because GitHub Issues is disabled on the fork.

## Obtain a GMT exporter compatible with Blender 5.2

The vendor's Blender 5.0 distribution was checked on 2026-10-31. Its `.pyc`
magic is `a70d0d0a` (Python 3.11), while Blender 5.2.3 embeds Python 3.13.
An updated compiled distribution or source release is needed. The local
Blender 5.2 geometry smoke test passes; end-to-end GMT export and the material
adapter still need verification against that compatible exporter. Do not
claim visual defects or the near-car road band resolved until in-game checks
pass. The converter now diagnoses this dependency during setup.
