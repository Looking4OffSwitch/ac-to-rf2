# Work items

## Completed: shorten README to a conventional GitHub quick start

- Keep the purpose, essential requirements, activated-venv setup, one conversion
  example, content-rights notice, and links to further documentation.
- Aim for approximately 100 lines or fewer and a useful first screen.
- Move the pipeline, troubleshooting, packaging walkthrough, performance history,
  and detailed limitations to focused `docs/` pages or `NOTES.md`.
- Preserve the protected-track guidance and verify all moved links and commands.

Completed 2026-11-01 during the package-layout migration. The short root README
links to `docs/USAGE.md`, which preserves the full previous guide. Requested
2026-10-31; tracked here because GitHub Issues is disabled on the fork.

## Obtain a GMT exporter compatible with Blender 5.2

The rFactor2 IO Group's Blender 5.0 distribution was checked on 2026-10-31. Its `.pyc`
magic is `a70d0d0a` (Python 3.11), while Blender 5.2.3 embeds Python 3.13.
An updated compiled distribution or source release is needed for 5.2 export.
The working conversion route now uses portable Blender 5.0.1 with the matching
community add-on R25.11.27, prepared by ac2rf2-tools. Real GMT regression tests
verify material colours, blend factors, alpha testing, and authored normals.
The separate Blender 5.2 geometry smoke test also passes. Do not
claim visual defects or the near-car road band resolved until in-game checks
pass. The converter now diagnoses this dependency during setup.


## Manually isolate Developer Mode loading crash and bundled vehicle audio

The AIW type/connection defects from the 2026-11-01 report are corrected and
Laguna is reinstalled. The native onFatalError 11 still needs manual validation;
no game was launched during the repair. With the same stock Skip Barber,
compare bundled Joesville and converted Laguna with zero AI, then add AI and
exercise pit entry/exit. Preserve the new trace and compare warning/fatal lines.

The readable bundled Vehicles/SkipBarber sound archive lacks four samples named
by skipbarber_snd.json. The separate Sounds/SkipBarber archive reports Unknown
MAS key in the official MAS utility; this is not proof of corruption. Do not
replace archives or invent silent samples. Confirm the supported SDK/vehicle
configuration with Studio 397 if Steam verification/update leaves the mismatch.
Measured filenames, counts, trace timings and AIW hashes are in docs/NOTES.md.


2026-11-02 update: four validated, reversible loose WAV aliases are installed
for the missing Skip Barber references. Original SDK JSON/MAS hashes are
unchanged. The generic helper and receipt removal procedure are in docs/AUDIO.md.
The newer trace has no missing-pit-box/reset warnings, but ends during session
restart without a new fatal record/dump. Native crash cause and the audio
workaround's actual game loading remain open pending the zero-AI comparison.


## Loading failures resolved; follow-up native driving validation (2026-11-03)

The manual-isolation item above is superseded for the reproduced loading
failures: computer-use testing established Joesville as a working control,
proved the AIW backward-branch loop, then identified the discarded TDF LOOSE
effects. With both generic fixes, Laguna loads into live practice and the
cockpit with nine AI. See the measured evidence in NOTES.md.

- Correct the grid-based garage spawn that immediately triggers an Exiting
  Pits Under Red penalty. Validate proper pit/garage geometry and connections
  before changing spawn positions.
- Exercise a complete lap, timing, pit entry/exit and AI driving.
- Investigate the broken fence/wire rendering visible in the successful
  cockpit test against the AC/CSP reference.


## AIW branch validation on Silverstone GP and Drift (2026-11-03)

A full launcher-cleanup regression conversion of `ks_silverstone::gp` stops
in the AIW stage: `branch scoring walk loops forever at waypoint 1084
(branch 989)`. The original committed converter at `297f5ab` reproduces
the identical error when its AIW stage reads the same source track. Drift
also fails at waypoint 218 (branch 149), reproduced with the baseline AIW
stage against the original source. This
predates the launcher changes; the failed build was not installed.
Investigate generic pit/location branch connections against the native
reference before changing the generator or validator. Measurements and
local evidence paths are in NOTES.md.


## Bound GMT texture-name verification to actual texture fields (2026-11-03)

A full Highlands Drift conversion exports geometry but staged verification
reports missing Kr.DdS and L.DDs. The old committed verifier reproduces the
error on the same generated files. Neither matched run ends in NUL; both
come from the whole-file filename regex, suggesting binary-data false
positives. Measure native texture-field boundaries and replace arbitrary
byte scanning while preserving detection of genuinely missing textures.
Exact GMT filenames/offsets and baseline evidence are in NOTES.md.
