# Security Policy

## What this plugin does with your machine

`dsh-freecad` is a thin bridge between an AI agent and a **local FreeCAD
installation**. Three properties matter for security:

1. **It spawns a subprocess.** Every tool call runs
   `<FreeCAD>/bin/freecadcmd.exe` (or `freecadcmd`) with a JSON request written to
   a temporary file. The executable path comes from the DSH profile configuration
   or `FREECAD_CMD`, never from the model's tool arguments.
2. **It reads and writes CAD files.** The `input`/`output` paths are chosen by the
   agent. `freecad_edit_step` refuses to overwrite its input unless `overwrite:
   true` is passed, but it will happily write a new file anywhere the DSH process
   can write.
3. **It does not sandbox FreeCAD.** A malicious STEP/IGES/BREP file is parsed by
   FreeCAD itself; any vulnerability in FreeCAD's importers is out of this
   plugin's control. Treat unknown CAD files the way you treat unknown archives.

The plugin has no network access of its own and sends no telemetry.

## Supported versions

| Version | Supported |
| --- | --- |
| 0.2.x | yes |
| < 0.2 | no (pre-release, not published) |

## Reporting a vulnerability

Please use **GitHub Security Advisories** on this repository
("Security" tab → "Report a vulnerability"). Do not open a public issue for
anything that could let a crafted CAD file or a compromised FreeCAD installation
escape the intended behaviour.

Include:

- the plugin version (`freecad_status` prints it),
- FreeCAD version and OS,
- a minimal reproducing model if the issue is triggered by a file (a synthetic
  one is fine — please do not send customer data),
- the exact tool call arguments.

You can expect an initial response within 7 days. Fixes ship as a patch release
with a note in `CHANGELOG.md`; credit is given unless you ask otherwise.

## Scope

In scope: the plugin's own JavaScript, its Python worker layer, the temporary-file
handling, path validation, and the settings page.

Out of scope: vulnerabilities inside FreeCAD or its Python environment (report
those upstream), and anything that requires the attacker to already control the
DSH process or the configured FreeCAD executable.
