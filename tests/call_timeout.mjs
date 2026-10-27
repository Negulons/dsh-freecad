// Verify the timeout path reports phases instead of a bare "timed out".
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { apply } from '../index.js'

const here = path.dirname(fileURLToPath(import.meta.url))
const sample = path.join(here, '..', 'examples', 'demo_bracket.step')
const tools = new Map()
await apply({ tools: { register: (t) => tools.set(t.name, t) } }, {})
const status = await tools.get('freecad_status').execute({})
if (!status.exists) {
  console.log('skip: FreeCADCmd not found')
  process.exit(0)
}
try {
  await tools.get('freecad_measure').execute({
    input: sample,
    timeoutMs: 1,
    items: [{ kind: 'radius', a: { face: 12 } }],
  })
  throw new Error('expected a timeout')
} catch (error) {
  if (!/timed out/.test(error.message)) throw error
  console.log('timeout message:\n' + error.message)
}
