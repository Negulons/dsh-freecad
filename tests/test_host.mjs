#!/usr/bin/env node
// Host-side unit tests. No FreeCAD required: everything here is schema and
// argument handling, which is exactly where an LLM-facing tool breaks quietly.

import assert from 'node:assert/strict'
import { _internal, apply } from '../index.js'

const { timeoutOf, TIMEOUT_MS, MAX_TIMEOUT_MS } = _internal

// --- per-call timeout -------------------------------------------------------
assert.equal(timeoutOf(undefined), TIMEOUT_MS, 'no args -> default timeout')
assert.equal(timeoutOf({}), TIMEOUT_MS, 'missing timeoutMs -> default')
assert.equal(timeoutOf({ timeoutMs: 600000 }), 600000, 'explicit timeout kept')
assert.equal(timeoutOf({ timeoutMs: 60 * 60_000 }), MAX_TIMEOUT_MS, 'clamped to the ceiling')
assert.equal(timeoutOf({ timeoutMs: 1 }), 1, 'small positive values pass through')
assert.equal(timeoutOf({ timeoutMs: -5 }), TIMEOUT_MS, 'negative falls back to default')
assert.equal(timeoutOf({ timeoutMs: 'nope' }), TIMEOUT_MS, 'non-numeric falls back')

// --- tool registry ----------------------------------------------------------
const status = await apply(undefined, {})
const names = status.tools.map((tool) => tool.name)
for (const expected of [
  'freecad_inspect_step',
  'freecad_edit_step',
  'freecad_step_to_drawing',
  'freecad_measure',
  'freecad_status',
]) {
  assert.ok(names.includes(expected), `tool ${expected} must be registered`)
}
assert.equal(new Set(names).size, names.length, 'tool names must be unique')

console.log(`ok ${names.length} tools · timeout default ${TIMEOUT_MS}ms · ceiling ${MAX_TIMEOUT_MS}ms`)
