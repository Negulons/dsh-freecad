#!/usr/bin/env node
// End-to-end smoke test through the host layer (not the raw worker).
//
//   FREECAD_CMD="D:/.../bin/freecadcmd.exe" node tests/call_tool.mjs
//
// Skipped silently when no FreeCADCmd is available: CI has no FreeCAD, and a
// missing CAD install is not a test failure.

import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'
import { apply } from '../index.js'

const here = path.dirname(fileURLToPath(import.meta.url))
const sample = path.join(here, '..', 'examples', 'demo_bracket.step')

const tools = new Map()
const ctx = {
  tools: { register: (tool) => tools.set(tool.name, tool) },
  effect: (fn) => { const dispose = fn(); return dispose },
}

// With a real context, apply() mounts the tools and returns nothing (the
// status object belongs to the self-test path), so ask the status tool instead.
await apply(ctx, {})
if (!tools.has('freecad_measure')) throw new Error('freecad_measure was not registered')
const status = await tools.get('freecad_status').execute({})
if (!status.exists) {
  console.log(`skip: FreeCADCmd not found (${status.freecadCmd})`)
  process.exit(0)
}

const measure = tools.get('freecad_measure')
const value = await measure.execute({
  input: sample,
  items: [
    { kind: 'radius', a: { face: 12 } },
    { kind: 'distance', a: { face: 3 }, b: { face: 5 } },
    { kind: 'distance', a: { point: [-38, -21, 12] }, b: { point: [38, 21, 12] } },
    { kind: 'radius', a: { edge: 1 } },
  ],
})

const [block] = measure.output.render({}, value)
console.log(block.text)
if (!value.timing || typeof value.timing.elapsedMs !== 'number') {
  throw new Error('timing metadata missing from the tool result')
}
const resolved = value.measurements.filter((m) => !m.error)
if (resolved.length !== 3) {
  throw new Error(`expected 3 resolved measurements, got ${resolved.length}`)
}
const thickness = resolved.find((m) => m.planeOffset != null)
if (!thickness) throw new Error('planeOffset missing for the face-to-face measurement')
console.log(`ok elapsed ${value.timing.elapsedMs}ms · phases ${value.timing.phases.length}`)
