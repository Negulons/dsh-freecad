#!/usr/bin/env node
// Host-side unit tests. No FreeCAD required: everything here is schema and
// argument handling, which is exactly where an LLM-facing tool breaks quietly.

import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { _internal, apply } from '../index.js'

const { timeoutOf, runWorker, TIMEOUT_MS, MAX_TIMEOUT_MS } = _internal

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

// --- what DSH does with tool.timeoutMs ----------------------------------------
// dsh-base mounts @deepseek-ai/dsh-tool-call-timeout-policy, which aborts
// exec.signal at the tool's *declared* timeoutMs and reports a timeout.  A
// declared 5 minutes silently capped every per-call timeoutMs at 5 minutes.
const tools = new Map()
await apply({ tools: { register: (tool) => tools.set(tool.name, tool) } }, {})
for (const name of ['freecad_inspect_step', 'freecad_edit_step', 'freecad_step_to_drawing', 'freecad_measure']) {
  const tool = tools.get(name)
  assert.ok(tool.timeoutMs > MAX_TIMEOUT_MS, `${name}: declared timeout must sit above the per-call ceiling`)
  assert.ok(tool.parameters.properties.timeoutMs, `${name}: timeoutMs must be a declared parameter`)
}

// --- the rendered text is all the model sees ---------------------------------
{
  const edges = Array.from({ length: 50 }, (_, i) => ({
    index: i + 1, curve: 'Line', length: 10, start: [0, 0, 0], end: [10, 0, 0], mid: [5, 0, 0],
  }))
  const faces = Array.from({ length: 7 }, (_, i) => ({
    index: i + 1, surface: i === 2 ? 'Cylinder' : 'Plane', area: 100, centerOfMass: [i, 0, 0],
    ...(i === 2 ? { radius: 4.5, axis: [0, 0, 1], concave: true } : {}),
  }))
  const text = tools.get('freecad_inspect_step').output.render({}, {
    file: { name: 'p.step' }, objectCount: 1,
    shape: { bbox: { size: [1, 1, 1] }, volume: 1, solids: 1, faces: 7 },
    holes: [], curvedFeatures: [],
    detail: { edges, edgesTotal: 260, nextEdgeOffset: 50, faces, facesTotal: 7, nextFaceOffset: null },
  })[0].text
  for (let i = 1; i <= 50; i++) assert.match(text, new RegExp(`^  #${i} `, 'm'), `edge #${i} must be listed`)
  for (let i = 1; i <= 7; i++) assert.match(text, new RegExp(`^  F${i} `, 'm'), `face F${i} must be listed`)
  assert.match(text, /F3 Cylinder .*Ø9\.00/, 'cylinder faces carry their diameter')
  assert.match(text, /边还有更多：下一页 offset=50/)
  const multi = tools.get('freecad_inspect_step').output.render({}, {
    file: { name: 'a.step' }, objectCount: 2, shape: { bbox: { size: [1, 1, 1] } }, holes: [],
    objects: [
      { label: 'Base_Plate', typeId: 'Part::Feature', stats: { volume: 12500 }, bbox: { size: [50, 50, 5] } },
      { label: 'Locating_Pin', typeId: 'Part::Feature', stats: { volume: 565.487 }, bbox: { size: [6, 6, 20] } },
    ],
  })[0].text
  assert.match(multi, /Base_Plate .*体积 12500\.00/, 'part names must reach the model')
  assert.match(multi, /Locating_Pin/)
  assert.doesNotMatch(text, /面还有更多/, 'no face page hint when every face is shown')
}
{
  const text = tools.get('freecad_edit_step').output.render({}, {
    output: 'x.step', before: { volume: 2 }, after: { volume: 1, solids: 1, valid: true }, holes: [],
    operations: [{ index: 1, type: 'fillet', volumeAfter: 1, valid: true,
      edges: [{ index: 7, curve: 'Line', length: 100, mid: [50, 30, 12] }] }],
    warnings: ['The input holds 2 parts'],
  })[0].text
  assert.match(text, /命中边 #7 Line L=100\.00 中点\(50\.0,30\.0,12\.0\)/, 'edit must echo the edges it hit')
  assert.match(text, /⚠ The input holds 2 parts/, 'edit must surface warnings')
}
{
  const text = tools.get('freecad_measure').output.render({}, {
    count: 2, resolved: 2,
    measurements: [
      { index: 1, kind: 'angle', value: 135, sharedVertex: true },
      { index: 2, kind: 'angle', value: 45, normalAngle: 135 },
    ],
  })[0].text
  assert.match(text, /#1 夹角 135\.000°（共顶点/)
  assert.match(text, /#2 两平面夹角 45\.000° \| 外法线夹角 135\.000°/)
}

// --- cancellation and timeout reach the child process ------------------------
// A stand-in for a slow FreeCAD: Node preloads a script that blocks for 60 s,
// then would fail on the .py worker.  If abort or the timer did not kill it,
// these calls would take a minute.
{
  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-freecad-test-'))
  const hang = path.join(scratch, 'hang.cjs')
  fs.writeFileSync(hang, 'Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 60000)\n')
  process.env.FREECAD_USER_HOME = path.join(scratch, 'home') // keep portableEnv() out of the node install
  const savedOptions = process.env.NODE_OPTIONS
  process.env.NODE_OPTIONS = `--require ${JSON.stringify(hang)}`
  const fake = { cmd: process.execPath }
  try {
    const controller = new AbortController()
    const started = Date.now()
    setTimeout(() => controller.abort(), 300)
    await assert.rejects(runWorker({ action: 'inspect' }, fake, controller.signal, 60_000), /aborted/)
    assert.ok(Date.now() - started < 10_000, `abort must stop the worker promptly (${Date.now() - started} ms)`)

    const pre = new AbortController()
    pre.abort()
    await assert.rejects(runWorker({ action: 'inspect' }, fake, pre.signal, 60_000), /aborted/)

    const t0 = Date.now()
    await assert.rejects(runWorker({ action: 'inspect' }, fake, undefined, 500), /timed out after 1s/)
    assert.ok(Date.now() - t0 < 10_000, 'the per-call timer must kill the worker')

    // execute() must forward DSH's exec.signal (it used to pass undefined).
    // Path resolution only accepts a file named freecadcmd, so stand node in
    // under that name.
    const named = path.join(scratch, process.platform === 'win32' ? 'freecadcmd.exe' : 'freecadcmd')
    try { fs.linkSync(process.execPath, named) } catch { fs.copyFileSync(process.execPath, named) }
    fs.chmodSync(named, 0o755)
    process.env.FREECAD_CMD = named
    const live = new Map()
    await apply({ tools: { register: (tool) => live.set(tool.name, tool) } }, {})
    const viaTool = new AbortController()
    const t1 = Date.now()
    setTimeout(() => viaTool.abort(), 300)
    await assert.rejects(
      live.get('freecad_inspect_step').execute({ input: hang }, { signal: viaTool.signal }),
      /aborted/,
    )
    assert.ok(Date.now() - t1 < 10_000, 'tool.execute must honour exec.signal')
  } finally {
    if (savedOptions === undefined) delete process.env.NODE_OPTIONS
    else process.env.NODE_OPTIONS = savedOptions
    delete process.env.FREECAD_CMD
    delete process.env.FREECAD_USER_HOME
    fs.rmSync(scratch, { recursive: true, force: true })
  }
}

console.log(`ok ${names.length} tools · timeout default ${TIMEOUT_MS}ms · ceiling ${MAX_TIMEOUT_MS}ms · render/abort/timeout checks passed`)
