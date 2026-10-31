# Source format compatibility

The converter supports KN5 versions **5 and 6**, AC racing-line version **7**,
and the current INI layouts consumed by the model, surface, and camera readers.
Unknown binary versions fail rather than being interpreted as the nearest known
layout. Errors identify the source file, format/version, record context, and byte
offset. INI field errors identify the file, section, and key.

## Binary validation

- The model reader and both texture passes share KN5 header/texture-table code.
  Texture-only passes validate that prefix; a model load validates the complete
  file before its data can be converted.
- Reads and skips must fit in the file. Counts must fit the remaining bytes at
  the minimum record size. Model nesting is limited to 256 parent levels.
- KN5 validates node types, boolean and material modes, material/vertex indices,
  triangle counts, finite positions/normals/UVs and consumed material values,
  and unambiguous texture/property/sampler names. Geometry validation also runs
  when geometry is left lazily decoded. No trailing KN5 bytes are accepted.
- Both racing-line consumers share one reader. It validates the 20-byte points,
  matching extra count and complete 72-byte extra records, and the optional
  spatial grid's nested count/length structure. Trailing bytes are rejected.
  Unused extra values and grid references are bounded, not interpreted or
  checked against invented semantic rules.
- Missing AI, a complete empty version-7 file, and the exact 12-byte empty
  version-3 stub `(3, 0, 0)` permit generated-line fallback. Present empty AI
  emits a warning. Zero-length, truncated, and other unsupported files fail.

Strings use strict UTF-8; INI files also accept a UTF-8 BOM. Unsupported text
encodings produce an error instead of silently changing names. Texture
extraction rejects output filenames containing path separators or drive syntax.

## Text and rendering compatibility

Unknown INI sections and keys are allowed. Recognized model sections require
`FILE` and a real source file; placement values must be finite and contain one
to three components (short headings are padded with zero). Recognized surface
sections require `KEY`; supplied friction must be finite and nonnegative and
flags must be `0` or `1`. Existing defaults for absent optional surface fields
remain. Camera sections require three-component `POSITION` and `FORWARD`,
finite numeric settings, and nonzero forward/up vectors.

An unrecognized source shader emits a warning and uses the existing generic
material approximation. Known names do not guarantee matching AC/CSP rendering.
This policy does not constitute complete validation of every CSP extension,
every image codec, or future formats that preserve a version number while
changing meaning.

## Adding support

Do not widen a version comparison or skip unexplained bytes. Obtain format
documentation or an upstream reader, measure representative real files, add an
explicit layout with regression fixtures, and compare decoded values and output
with a supported baseline. Document legitimate extensions and their validation
rules before accepting them. Keep game assets out of fixtures and commits.

Run `pytest -q` in the activated environment. Format regressions use generated
fixtures, including every byte truncation of representative KN5 and AI records.
Stock-file measurements and remaining visual limitations are in `NOTES.md`.
