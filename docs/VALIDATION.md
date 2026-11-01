# Conversion and visual validation

## Prepare the tested tools

In a Command Prompt in the repository, activate `.venv` and run:

```bat
python -m pip install -e ".[dev]"
ac2rf2-tools
ac2rf2-check
pytest -q
```

The tooling command installs portable Blender 5.0.1 and the rFactor2 IO Group
R25.11.27 exporter under ignored `.tools/`. Existing Blender 5.2 installations
are untouched. Downloads have pinned SHA256 checksums; rerunning reuses verified
archives. The third-party binaries and converted game content are not committed.

`pytest` includes a real GMT test when the portable pair is present. It exports
generated opaque, blended, and cutout meshes and reads the actual binary output:
material colours, One/Zero versus SrcAlpha/InvSrcAlpha factors, colour key and
threshold, and a custom normal distinct from both the face normal and straight up.
The fixture suite can run without either game or Blender installed.

## Convert and inspect a stock track

```bat
ac2rf2-test ks_laguna_seca --restart-game --jobs 4
ac2rf2-verify "C:\Program Files (x86)\Steam\steamapps\common\rFactor 2\ModDev\Locations\ks_laguna_seca" out\ks_laguna_seca
```

The command launches Developer Mode after verification and installation. Select
the converted venue. See [workflow options](TESTING.md) for batch/reuse modes. Verification checks files and exported contracts; it cannot
prove the appearance in the renderer.

## Compare visuals before tuning

1. Fix the camera location, time, weather, renderer settings, and track layout.
2. Compare road detail near/far, foliage silhouettes and depth ordering, gravel
   transitions, shadows, and bright structures against AC with CSP.
3. Record screenshots and measurable output values in `NOTES.md`.
4. Investigate the remaining road band with a small road scene. Verify serialized
   mip/filter settings, then isolate detail colour, normal mapping, and specular
   response one at a time. Do not change texture density, contrast, and lighting
   together or treat passing file checks as a visual sign-off.

## Source format changes

See [format compatibility](FORMATS.md) for supported versions, empty-AI fallback,
validation rules, and the process for adding a new layout. Unsupported binary
versions and malformed present sources fail; unknown optional INI keys remain
compatible. Source-format tests run with `pytest -q` without either game.
