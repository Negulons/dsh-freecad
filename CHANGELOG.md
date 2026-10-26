# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

## 0.2.1 — docs patch

### Fixed

- The two README screenshots used repo-relative paths, which npm renders as
  `https://www.npmjs.com/package/...` and therefore showed as broken images on
  the package page. They now use absolute `raw.githubusercontent.com` URLs, so
  the same Markdown works on GitHub and on npm.

## 0.2.0 — first public release

### Added

- **Settings page**: DSH → Settings → FreeCAD. It sets the `freecadcmd`
  executable path (volatile, so a save re-applies the plugin configuration
  immediately) and links to the official GitHub releases and the TUNA mirror.
  The value overrides the profile config, the `FREECAD_CMD` environment variable
  and the built-in `C:\Program Files\FreeCAD …` candidates, in that order.
- `NOTICE`, `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `.gitignore`.
- English README (`README.en.md`); documentation reorganised into
  `docs/{architecture,tools,drawing-engine,troubleshooting,development,limitations}.md`.

### Changed

- Plugin version `0.1.0` → `0.2.0`; the three tools and their parameters are
  unchanged from the last internal build.
- Installer consolidated into `scripts/install.mjs` (zero dependencies; falls back
  to copying into `node_modules` when `pnpm` is unavailable).
- Copyright holder named in `LICENSE`.

### Fixed

- **The plugin failed to activate** with `TypeError: Invalid effect`. `apply()`
  returned a value; cordis treats anything that is neither `undefined`/`null`
  nor a disposer function as an invalid effect, which aborted the whole entry —
  the tools never registered and the settings page never appeared.
- `freecad_status` now says where to configure the path ("set the FreeCAD path in
  DSH → Settings → FreeCAD") instead of only listing the default candidates.

### Known limitations

- Windows-first: `freecadcmd` discovery covers the standard Windows install
  locations. Linux and macOS work only when the path is configured by hand.
- Drawings carry overall width/height and a hole table. Feature dimensions
  (boss diameter, step heights, hole positions per view), sections, detail views,
  GD&T and surface finish symbols are not generated.
- The hole table lists at most 10 holes per sheet.
- Holes are detected from cylindrical faces only; slots, D-shaped holes and
  pockets do not appear in the table.
- No automated test suite yet.
