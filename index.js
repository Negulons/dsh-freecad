// dsh-freecad — host half of the FreeCAD DSH plugin.
//
// Registers tools that drive the locally installed FreeCADCmd:
//   freecad_inspect_step     read a STEP/STP file and report geometry + holes
//   freecad_edit_step        transform / cut / fuse / fillet and export STEP
//   freecad_step_to_drawing  HLR orthographic views + SVG/DXF/PDF/PNG
//   freecad_measure          distance / angle / diameter without touching the file
//   freecad_status           check the configured FreeCADCmd installation
//
// The heavy CAD work happens in dsh/fc_worker.py under FreeCADCmd.  The Node
// layer only validates arguments, writes a UTF-8 request, and reads the UTF-8
// result file.  Extra command-line arguments are avoided because FreeCADCmd
// treats them as CAD files to open.
//
// The FreeCAD executable is resolved in this order:
//   1. the value saved in DSH → Settings → FreeCAD (`freecadPath`, a volatile
//      config field rendered by the browser half in lib/client.js) — either
//      freecadcmd.exe itself or a FreeCAD install directory;
//   2. `config.freecadPath` in cordis.patch.yml (legacy spelling: `config.freecadCmd`);
//   3. the FREECAD_CMD environment variable;
//   4. the usual Windows install locations, then `freecadcmd` on PATH.
import { spawn } from 'node:child_process'
import fs from 'node:fs/promises'
import fsSync from 'node:fs'
import { createRequire } from 'node:module'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

export const name = 'freecad'
export const inject = ['tools']

// The settings page (lib/client.js) edits one volatile field of this plugin's
// configuration.  Declaring the field here is what makes the Host serve the
// namespace to the browser half; the value arrives in `apply()` as a reference
// (`config.freecadPath.get()`).  Schemastery is resolved from the DSH profile
// the plugin is installed into, so a bare source checkout without
// node_modules simply registers no settings page instead of failing to load.
const Schema = (() => {
  try {
    return createRequire(import.meta.url)('@deepseek-ai/schemastery')
  } catch {
    return undefined
  }
})()

/** Volatile settings fields; a deployment without the schema keeps working. */
export const Config = Schema
  ? Schema.object({
      freecadPath: Schema.string().default('').volatile(),
    })
  : undefined

const __dirname = path.dirname(fileURLToPath(import.meta.url))
// Installed plugins are copied into the DSH profile without their node_modules,
// so the worker chain is resolved against the checkout directory when present:
// the workspace copy this workspace is (`C:\…\DSH-FreeCAD Open-Source`) or the
// source install (`…/profiles/<name>/plugins/dsh-freecad` in the same Drive
// layout is not portable) — the DSH desktop profile copy is the fallback.
const WORKER_DIRS = [
  path.join(__dirname, 'dsh'),
  path.join(process.env.USERPROFILE ?? os.homedir(), '.dsh', 'profiles', 'desktop', 'plugins', 'dsh-freecad', 'dsh'),
]
const WORKER = (() => {
  for (const dir of WORKER_DIRS) {
    const candidate = path.join(dir, 'fc_worker.py')
    if (fsSync.existsSync(candidate)) return candidate
  }
  return path.join(__dirname, 'dsh', 'fc_worker.py')
})()
const TIMEOUT_MS = 5 * 60_000
const MAX_TIMEOUT_MS = 30 * 60_000
// The `timeoutMs` property of a registered tool is not advisory: DSH's
// tool-call-timeout-policy (mounted by dsh-base) arms exec.signal with it and
// turns the call into "tool call timed out" when it fires.  Declaring the
// 5-minute default there capped every per-call `timeoutMs` argument at 5
// minutes -- a 10-minute drawing kept running and wrote its files, yet the
// model was told it timed out.  So the tool declares the ceiling and the
// per-call timer in runWorker enforces the requested (or default) budget.
const TOOL_TIMEOUT_CEILING_MS = MAX_TIMEOUT_MS + 30_000

/** Default face/edge page size of freecad_inspect_step (all rows are rendered). */
const DETAIL_PAGE = 50

const fmt1 = (p) => p.map((x) => Number(x).toFixed(1)).join(',')

/**
 * Per-call timeout. Big assemblies legitimately take longer than five minutes;
 * without this the model had no way to trade waiting against failing.
 */
function timeoutOf(args) {
  const raw = Number(args?.timeoutMs)
  if (!Number.isFinite(raw) || raw <= 0) return TIMEOUT_MS
  return Math.min(Math.round(raw), MAX_TIMEOUT_MS)
}

function timeoutParam() {
  return {
    type: 'integer',
    minimum: 1000,
    maximum: MAX_TIMEOUT_MS,
    description: `本次调用的超时毫秒数，默认 ${TIMEOUT_MS}，最大 ${MAX_TIMEOUT_MS}`,
  }
}

/** Volatile config field edited by the settings page (lib/client.js). */
const PATH_KEY = 'freecadPath'

/** FreeCAD releases probed by the version field of the settings card. */
const KNOWN_FREECAD_DIRS = [
  'C:\\Program Files\\FreeCAD 1.1\\bin\\freecadcmd.exe',
  'C:\\Program Files\\FreeCAD 1.0\\bin\\freecadcmd.exe',
  'C:\\Program Files\\FreeCAD\\bin\\freecadcmd.exe',
]

function isExecutableFile(value) {
  try {
    return fsSync.statSync(value).isFile()
  } catch {
    return false
  }
}

/**
 * Turn one user-supplied value into the freecadcmd executable path the user
 * meant (it is not required to exist).
 *
 * Accepts the executable itself, a FreeCAD install directory (where
 * bin/freecadcmd.exe lives), or the `bin` directory.  Quotes, %VARS% and
 * forward slashes are tolerated.  A bare command name (`freecadcmd`) stays
 * as-is so a PATH lookup still works.
 * @param value - the raw string.
 * @returns the executable path, or undefined for an empty value.
 */
function freecadCmdFrom(value) {
  if (typeof value !== 'string') return undefined
  const raw = value.trim().replace(/^["'`]+|["'`]+$/g, '')
  if (!raw) return undefined
  const expanded = raw.replace(/%([^%]+)%/g, (match, key) => process.env[key] ?? match)
  const trimmed = expanded.replace(/[\\/]+$/, '')
  if (!trimmed.includes('/') && !trimmed.includes('\\')) return trimmed
  if (/freecadcmd(\.exe)?$/i.test(trimmed)) return trimmed
  // a `bin` directory that does not contain freecadcmd yet (e.g. typo) is
  // still a bin directory: point at the executable inside it
  if (/(^|[\\/])bin$/i.test(trimmed)) return path.join(trimmed, 'freecadcmd.exe')
  return path.join(trimmed, 'bin', 'freecadcmd.exe')
}

/** Locate `freecadcmd` through PATH without spawning a shell. */
function freecadFromPath() {
  const dirs = (process.env.PATH ?? '').split(path.delimiter).filter(Boolean)
  const names = process.platform === 'win32'
    ? (process.env.PATHEXT ?? '.EXE').split(';').filter(Boolean).map((ext) => `freecadcmd${ext.toLowerCase()}`)
    : ['freecadcmd']
  for (const dir of dirs) {
    for (const name of names) {
      const candidate = path.join(dir, name)
      if (isExecutableFile(candidate)) return candidate
    }
  }
  return undefined
}

/**
 * Build the resolution chain, most specific first.
 * @param settings - the path saved on the Plugins page (see PATH_KEY), if any.
 * @param config - the cordis config of this plugin.
 * @returns the candidate entries.
 */
function freecadCandidates(settings, config = {}) {
  return [
    { source: 'plugins-page', value: settings },
    { source: 'config', value: config.freecadCmd },
    { source: 'env', value: process.env.FREECAD_CMD },
    ...KNOWN_FREECAD_DIRS.map((value) => ({ source: 'default', value })),
  ]
    .map((entry) => ({
      ...entry,
      resolved: entry.value ? freecadCmdFrom(entry.value) : undefined,
    }))
    .filter((entry) => Boolean(entry.resolved))
}

/**
 * Pick the executable to run.
 *
 * An explicit choice (saved settings, config, FREECAD_CMD) is used exactly as
 * given — a typo there must surface as "not found" instead of silently running
 * another FreeCAD.  Only the fallbacks are probed for existence.
 * @param settings - the path saved on the Plugins page, if any.
 * @param config - the cordis config of this plugin.
 * @returns {cmd, source}; `cmd` may not exist when nothing was found.
 */
function resolveFreeCAD(settings, config = {}) {
  const candidates = freecadCandidates(settings, config)
  const explicit = candidates.find((entry) => entry.source !== 'default')
  if (explicit) return { cmd: explicit.resolved, source: explicit.source }
  const found = candidates.find((entry) => isExecutableFile(entry.resolved))
  if (found) return { cmd: found.resolved, source: found.source }
  const fromPath = freecadFromPath()
  if (fromPath) return { cmd: fromPath, source: 'PATH' }
  return { cmd: candidates[0]?.resolved ?? 'freecadcmd.exe', source: candidates[0]?.source ?? 'none' }
}

/**
 * Parse `freecadcmd --version` output ("FreeCAD 1.1.4 (Git ...)").
 * @param output - combined stdout/stderr of the version probe.
 * @returns the version string, or null.
 */
function parseFreeCADVersion(output) {
  const line = (output ?? '').split(/\r?\n/).find((row) => /freecad\s+v?\d/i.test(row))
  if (!line) return null
  const match = /FreeCAD\s+v?(\d+(?:\.\d+){1,3})/i.exec(line)
  return match ? match[1] : line.trim() || null
}

/**
 * Extra environment for a portable (unzipped) FreeCAD.
 *
 * The portable build initialises its user directories relative to the executable
 * and aborts with "Could not create directories. Access is denied." when none of
 * them is writable. Redirecting FREECAD_USER_HOME / FREECAD_USER_DATA / TMP makes
 * such builds start without touching their own folder.
 *
 * The redirect goes next to the install (`<FreeCAD>/dsh-user`) first: a directory
 * under %TEMP% was measured to fail on FreeCAD 1.1.4 with "Unknown runtime error
 * occurred while initializing FreeCAD", while a folder beside the install works.
 * %TEMP% stays as the fallback for read-only installs. Installed builds (Program
 * Files) are left untouched so the user's own preferences stay in use.
 * @param cmd - the resolved freecadcmd path.
 * @returns environment additions, empty when none are needed.
 */
function portableEnv(cmd) {
  if (process.env.FREECAD_USER_HOME) return {}
  if (/^[a-z]:[\\/]program files/i.test(cmd)) return {}
  const bases = []
  if (path.isAbsolute(cmd)) bases.push(path.join(path.dirname(path.dirname(cmd)), 'dsh-user'))
  bases.push(path.join(os.tmpdir(), 'dsh-freecad', 'freecad-home'))
  for (const base of bases) {
    const env = {
      FREECAD_USER_HOME: path.join(base, 'home'),
      FREECAD_USER_DATA: path.join(base, 'data'),
      TMP: path.join(base, 'temp'),
      TEMP: path.join(base, 'temp'),
    }
    try {
      for (const dir of [env.FREECAD_USER_HOME, env.FREECAD_USER_DATA, env.TMP]) {
        fsSync.mkdirSync(dir, { recursive: true })
      }
      return env
    } catch {
      // fall through to the next base
    }
  }
  return {}
}

/** Run `freecadcmd --version` and return the parsed version (or null). */
function probeFreeCADVersion(cmd, timeoutMs = 20_000) {
  return new Promise((resolve) => {
    let settled = false
    let child
    const finish = (value) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve(value)
    }
    const timer = setTimeout(() => {
      try { child?.kill() } catch { /* ignore */ }
      finish(null)
    }, timeoutMs)
    try {
      child = spawn(cmd, ['--version'], {
        windowsHide: true,
        stdio: ['ignore', 'pipe', 'pipe'],
        env: { ...process.env, ...portableEnv(cmd) },
      })
    } catch {
      finish(null)
      return
    }
    let out = ''
    const collect = (chunk) => {
      if (out.length < 8000) out += chunk.toString('utf8')
    }
    child.stdout.on('data', collect)
    child.stderr.on('data', collect)
    child.on('error', () => finish(null))
    child.on('close', () => finish(parseFreeCADVersion(out)))
  })
}

function resolveWorkspacePath(value) {
  if (!value) return value
  return path.resolve(value)
}

function resultText(value) {
  if (!value) return ''
  return JSON.stringify(value, null, 2)
}

function collect(stream, limit = 12000) {
  let text = ''
  stream.on('data', (chunk) => {
    if (text.length < limit) text += chunk.toString('utf8')
  })
  return () => text
}

/**
 * Where to put the request/result JSON.
 *
 * `os.tmpdir()` is not reliable here: on Windows the FreeCAD process can be
 * denied write access to `%LOCALAPPDATA%\\Temp` (Defender's controlled folder
 * access, roaming profiles, …) while it happily writes inside its own user
 * home.  So when we know FreeCAD's user home, put the exchange next to it.
 */
function scratchDir(cmd) {
  const env = portableEnv(cmd)
  const home = env.FREECAD_USER_HOME || process.env.FREECAD_USER_HOME
  if (home && path.isAbsolute(home)) {
    const dir = path.join(path.dirname(home), 'rpc')
    try {
      fsSync.mkdirSync(dir, { recursive: true })
      return dir
    } catch {
      // fall through to the OS temp dir
    }
  }
  return os.tmpdir()
}

async function runWorker(payload, exec, signal, timeoutMs = TIMEOUT_MS) {
  const cmd = exec.cmd
  if (!isExecutableFile(cmd)) {
    throw new Error(
      `FreeCADCmd not found at ${cmd}. Install FreeCAD, then set the path in ` +
      'DSH → Settings → FreeCAD (FREECAD_CMD and config.freecadPath work too).',
    )
  }
  if (!fsSync.existsSync(WORKER)) {
    throw new Error(`Plugin worker missing: ${WORKER}`)
  }
  if (signal?.aborted) throw new Error('FreeCAD worker aborted')
  const tmp = await fs.mkdtemp(path.join(scratchDir(cmd), 'dsh-freecad-'))
  const reqPath = path.join(tmp, 'request.json')
  const resPath = path.join(tmp, 'result.json')
  const progressPath = path.join(tmp, 'progress.log')
  await fs.writeFile(reqPath, JSON.stringify(payload), 'utf8')
  const startedAt = Date.now()
  const readProgress = () => {
    try {
      return fsSync.readFileSync(progressPath, 'utf8')
        .split('\n')
        .filter(Boolean)
        .slice(-12)
        .map((line) => {
          const [fraction, ...rest] = line.split('\t')
          const text = rest.join('\t')
          return text || fraction
        })
    } catch {
      return []
    }
  }
  try {
    const outcome = await new Promise((resolve, reject) => {
      const child = spawn(cmd, [WORKER], {
        cwd: __dirname,
        windowsHide: true,
        env: {
          ...process.env,
          ...portableEnv(cmd),
          FREECAD_PLUGIN_REQUEST: reqPath,
          FREECAD_PLUGIN_RESULT: resPath,
          FREECAD_PLUGIN_PROGRESS: progressPath,
        },
        stdio: ['ignore', 'pipe', 'pipe'],
      })
      const stdout = collect(child.stdout)
      const stderr = collect(child.stderr)
      let settled = false
      let timer
      // DSH waits for a cancelled tool body to settle before the call ends, so
      // an ignored abort kept FreeCAD running until it finished on its own.
      // Kill it, and settle once the process has actually exited (bounded)
      // so the scratch directory can be removed afterwards.
      let closed = false
      const exited = new Promise((done) => child.once('close', () => { closed = true; done() }))
      const stop = async (error) => {
        if (settled) return
        settled = true
        clearTimeout(timer)
        signal?.removeEventListener('abort', onAbort)
        try { child.kill() } catch { /* ignore */ }
        if (!closed) await Promise.race([exited, new Promise((done) => setTimeout(done, 5000).unref?.())])
        reject(error)
      }
      const onAbort = () => {
        const trail = readProgress()
        const where = trail.length ? ` (进度：${trail.join(' → ')})` : ''
        void stop(new Error(`FreeCAD worker aborted${where}`))
      }
      timer = setTimeout(() => {
        const trail = readProgress()
        const where = trail.length ? `\n进度：${trail.join(' → ')}` : ''
        void stop(new Error(
          `FreeCAD worker timed out after ${Math.max(1, Math.round(timeoutMs / 1000))}s` +
          `${where}\n可以调大 timeoutMs（最多 30 分钟），或把任务拆小。`,
        ))
      }, timeoutMs)
      if (signal) {
        if (signal.aborted) return onAbort()
        signal.addEventListener('abort', onAbort, { once: true })
      }
      child.on('error', (error) => {
        if (settled) return
        settled = true
        clearTimeout(timer)
        signal?.removeEventListener('abort', onAbort)
        reject(new Error(`Failed to start FreeCADCmd: ${error.message}`))
      })
      child.on('close', (code) => {
        if (settled) return
        settled = true
        clearTimeout(timer)
        signal?.removeEventListener('abort', onAbort)
        resolve({ code, stdout: stdout(), stderr: stderr() })
      })
    })
    let raw = null
    try {
      raw = await fs.readFile(resPath, 'utf8')
    } catch {
      // handled below
    }
    if (!raw) {
      throw new Error(
        `FreeCAD produced no result (exit ${outcome.code}).\n${outcome.stderr || outcome.stdout || 'no output'}`,
      )
    }
    let parsed
    try {
      parsed = JSON.parse(raw)
    } catch (error) {
      throw new Error(`Invalid worker result: ${error.message}\n${raw.slice(0, 1000)}`)
    }
    if (!parsed.ok) {
      const detail = parsed.traceback || parsed.error || 'unknown FreeCAD error'
      throw new Error(`FreeCAD worker failed: ${parsed.error}\n${detail}`)
    }
    const elapsedMs = Date.now() - startedAt
    if (parsed.data && typeof parsed.data === 'object' && !Array.isArray(parsed.data)) {
      // Give the model a timeline it can reason about when something is slow.
      parsed.data.timing = { elapsedMs, phases: readProgress() }
    }
    return parsed.data
  } finally {
    try { await fs.rm(tmp, { recursive: true, force: true }) } catch { /* ignore */ }
  }
}

const STATS_SCHEMA = {
  type: 'object',
  additionalProperties: true,
  properties: {
    shapeType: { type: 'string' },
    valid: { type: 'boolean' },
    solids: { type: 'number' },
    faces: { type: 'number' },
    edges: { type: 'number' },
    volume: { type: 'number' },
    bbox: { type: 'object', additionalProperties: true },
  },
}

const OPERATION_SCHEMA = {
  type: 'object',
  additionalProperties: true,
  properties: {
    type: {
      type: 'string',
      enum: ['translate', 'move', 'rotate', 'rotation', 'scale', 'mirror', 'fillet', 'chamfer', 'hole', 'drill', 'primitive', 'boolean'],
      description: 'Operation type',
    },
    vector: { type: 'array', items: { type: 'number' }, minItems: 3, maxItems: 3, description: 'Translation vector [x,y,z] (mm)' },
    dx: { type: 'number' },
    dy: { type: 'number' },
    dz: { type: 'number' },
    axis: { type: 'array', items: { type: 'number' }, minItems: 3, maxItems: 3, description: 'Rotation/drill axis [x,y,z]' },
    angle: { type: 'number', description: 'Rotation angle in degrees' },
    center: { type: 'array', items: { type: 'number' }, minItems: 3, maxItems: 3, description: 'Rotation center or hole entry point [x,y,z]' },
    factor: { type: 'number', description: 'Uniform scale factor' },
    plane: { type: 'string', enum: ['XY', 'XZ', 'YZ'] },
    point: { type: 'array', items: { type: 'number' }, minItems: 3, maxItems: 3, description: 'Mirror plane point [x,y,z] (default origin)' },
    normal: { type: 'array', items: { type: 'number' }, minItems: 3, maxItems: 3, description: 'Mirror plane normal; overrides plane' },
    radius: { type: 'number', description: 'Fillet radius or chamfer distance (mm)' },
    distance: { type: 'number', description: 'Chamfer distance alias for radius (mm)' },
    edges: { type: 'array', items: { type: 'number' }, description: '1-based edge indices for fillet/chamfer' },
    edgeAt: {
      type: 'array',
      items: { type: 'number' },
      minItems: 3,
      maxItems: 3,
      description: '按位置选边：在该点附近选择一条边（推荐的稳健做法，边索引每次编辑后都会变）',
    },
    edgesNear: {
      type: 'array',
      items: { type: 'number' },
      minItems: 3,
      maxItems: 3,
      description: '按位置选边：选择该点附近的全部边',
    },
    diameter: { type: 'number', description: 'Hole diameter' },
    depth: { type: 'number', description: 'Blind hole depth from center/entry along +axis' },
    through: { type: 'boolean' },
    shape: { type: 'string', enum: ['box', 'cylinder', 'sphere'] },
    size: { type: 'array', items: { type: 'number' }, minItems: 3, maxItems: 3 },
    position: { type: 'array', items: { type: 'number' }, minItems: 3, maxItems: 3 },
    height: { type: 'number' },
    action: { type: 'string', enum: ['cut', 'fuse'] },
  },
  required: ['type'],
}

const OUTPUT_SCHEMA = {
  type: 'object',
  additionalProperties: true,
}

function inspectTool(exec) {
  return {
    name: 'freecad_inspect_step',
    description:
      '读取 STEP/STP（也支持 IGES/BREP）立体 CAD 文件，返回对象列表、包围盒、体积、面/边数量、圆柱孔识别结果（直径/轴向/通孔/中心/深度）、长圆孔（宽×长）以及非整圆的凹圆柱面（内腔弧、圆底槽等，curvedFeatures）。编辑前先用它确认边缘索引和孔位。所有长度单位为 mm。',
    parameters: {
      type: 'object',
      properties: {
        input: { type: 'string', description: 'STEP/STP 文件绝对路径（也支持 IGES/BREP）' },
        detail: { type: 'boolean', description: '是否返回面和边的详细清单' },
        maxItems: { type: 'integer', minimum: 10, maximum: 2000, description: '单页条数上限，默认 200' },
        offset: { type: 'integer', minimum: 0, description: '跳过前多少条（0 = 从第 1 条开始），翻页时填返回的“下一页 offset”，默认 0' },
        limit: { type: 'integer', minimum: 1, maximum: 2000, description: `本页条数（面和边各自），默认 ${DETAIL_PAGE}；本页每一条都会显示` },
        timeoutMs: timeoutParam(),
      },
      required: ['input'],
    },
    output: {
      schema: { ...OUTPUT_SCHEMA, properties: { shape: STATS_SCHEMA } },
      render: (_args, value) => {
        const s = value.shape || {}
        const b = s.bbox || {}
        const size = b.size || []
        const holes = value.holes || []
        const curved = value.curvedFeatures || []
        const slots = holes.filter((h) => h.kind === 'slot')
        const lines = [
          `📐 ${value.file?.name || value.input}`,
          `尺寸 ${size.map((x) => Number(x).toFixed(2)).join(' × ')} mm | 体积 ${Number(s.volume || 0).toFixed(2)} mm³ | ${s.solids ?? '?'} solid / ${s.faces ?? '?'} faces`,
          `对象 ${value.objectCount} 个 | 有效 ${s.valid} | 孔 ${holes.length - slots.length} 个 | 长圆孔 ${slots.length} 个 | 曲面特征 ${curved.length} 处`,
        ]
        for (const h of holes.slice(0, 12)) {
          const at = `@ (${h.center.map((x) => Number(x).toFixed(1)).join(', ')})`
          if (h.kind === 'slot') {
            const how = h.through ? '通槽' : `深${h.depth}`
            lines.push(`  ${h.id}: 长圆孔 ${h.length}×${h.diameter} ${h.axisName}轴 ${how} ${at}`)
            continue
          }
          const kind = h.through ? `通孔${h.depth ? ` 厚${h.depth}` : ''}` : `盲孔深${h.depth}`
          lines.push(`  ${h.id}: Ø${h.diameter} ${h.axisName}轴 ${kind} ${at}`)
        }
        if (holes.length > 12) lines.push(`  … 共 ${holes.length} 个孔/槽`)
        for (const g of curved.slice(0, 6)) {
          lines.push(`  ${g.id}: 弧面 R${g.radius} ${g.axisName}轴 ${g.angleDeg}° 深${g.depth} @ (${g.center.map((x) => Number(x).toFixed(1)).join(', ')})（凹圆柱面，非整圆：内腔弧、圆底槽这类）`)
        }
        if (curved.length > 6) lines.push(`  … 共 ${curved.length} 处曲面特征`)
        const objects = value.objects || []
        if (objects.length > 1) {
          lines.push(`零件 ${objects.length} 个：`)
          for (const o of objects.slice(0, 30)) {
            const sz = o.bbox?.size ? ` ${o.bbox.size.map((x) => Number(x).toFixed(2)).join('×')} mm` : ''
            lines.push(`  ${o.label} (${o.typeId})${sz} | 体积 ${Number(o.stats?.volume || 0).toFixed(2)} mm³`)
          }
          if (objects.length > 30) lines.push(`  … 共 ${objects.length} 个`)
        }
        for (const w of value.warnings || []) lines.push(`⚠ ${w}`)
        // The model only reads this text, not the JSON value: every row the
        // page returned must be listed, faces included (freecad_measure takes
        // face numbers, which used to be invisible).
        const detail = value.detail || {}
        if (Array.isArray(detail.faces) && detail.faces.length) {
          const first = detail.faces[0].index
          const last = detail.faces.at(-1).index
          lines.push(`面（freecad_measure 用 {"face": n}，1-based）：#${first}–#${last}，共 ${detail.facesTotal ?? detail.faces.length} 个`)
          for (const f of detail.faces) {
            let extra = ''
            if (f.surface === 'Cylinder' && f.radius != null) {
              extra = ` Ø${Number(f.radius * 2).toFixed(2)} 轴(${fmt1(f.axis || [])})${f.concave === true ? ' 凹/孔壁' : f.concave === false ? ' 凸' : ''}`
            }
            const at = f.centerOfMass ? ` 中心(${fmt1(f.centerOfMass)})` : ''
            lines.push(`  F${f.index} ${f.surface} 面积${Number(f.area).toFixed(2)}${extra}${at}`)
          }
          if (detail.nextFaceOffset != null) lines.push(`  面还有更多：下一页 offset=${detail.nextFaceOffset}`)
        }
        if (Array.isArray(detail.edges) && detail.edges.length) {
          const first = detail.edges[0].index
          const last = detail.edges.at(-1).index
          lines.push(`边（倒圆角/倒角的 edges，1-based）：#${first}–#${last}，共 ${detail.edgesTotal ?? detail.edges.length} 条`)
          for (const e of detail.edges) {
            if (e.curve === 'Circle' && e.center) {
              lines.push(`  #${e.index} Circle R${Number(e.radius).toFixed(2)} @ (${fmt1(e.center)})`)
            } else {
              const from = e.start ? fmt1(e.start) : '?'
              const to = e.end ? fmt1(e.end) : '?'
              lines.push(`  #${e.index} ${e.curve} L=${Number(e.length).toFixed(2)} (${from}) → (${to})`)
            }
          }
          if (detail.nextEdgeOffset != null) lines.push(`  边还有更多：下一页 offset=${detail.nextEdgeOffset}`)
        }
        return [{ type: 'text', text: lines.join('\n') }]
      },
    },
    timeoutMs: TOOL_TIMEOUT_CEILING_MS,
    isConcurrencySafe: () => false,
    async execute(args, call) {
      if (!args?.input) throw new Error('freecad_inspect_step needs an input path')
      return runWorker({
        action: 'inspect',
        input: resolveWorkspacePath(args.input),
        detail: Boolean(args.detail),
        maxItems: args.maxItems,
        offset: args.offset || 0,
        // Every returned row is rendered for the model, so the default page
        // stays small; it used to return 200 and show only the first 24.
        limit: args.limit ?? Math.min(DETAIL_PAGE, args.maxItems ?? DETAIL_PAGE),
      }, exec, call?.signal, timeoutOf(args))
    },
  }
}

function editTool(exec) {
  return {
    name: 'freecad_edit_step',
    description:
      '编辑 STEP/STP 立体模型并导出新的 STEP：平移/旋转/缩放/镜像、在指定位置钻通孔或盲孔、盒/圆柱/球布尔增删、按 1-based 边索引倒圆角或倒角。STEP 没有特征历史，编辑是 B-Rep 几何级操作；默认不覆盖输入文件，输出 <原名>_edited.step。所有长度单位为 mm。',
    parameters: {
      type: 'object',
      properties: {
        input: { type: 'string', description: '输入 STEP/STP 绝对路径' },
        output: { type: 'string', description: '输出 STEP 路径；默认 <输入名>_edited.step' },
        operations: { type: 'array', items: OPERATION_SCHEMA, minItems: 1, description: '按顺序执行的编辑操作' },
        overwrite: { type: 'boolean', description: '允许输出路径与输入相同，默认 false' },
        saveFCStd: { type: 'boolean', description: '同时保存 FreeCAD FCStd 文件' },
        timeoutMs: timeoutParam(),
      },
      required: ['input', 'operations'],
    },
    output: {
      schema: { ...OUTPUT_SCHEMA, properties: { before: STATS_SCHEMA, after: STATS_SCHEMA } },
      render: (_args, value) => {
        const before = value.before || {}
        const after = value.after || {}
        const lines = [
          `✅ 已导出 ${value.output}`,
          `体积 ${Number(before.volume || 0).toFixed(2)} → ${Number(after.volume || 0).toFixed(2)} mm³ | ${after.solids ?? '?'} solid | 有效 ${after.valid}`,
          `孔 ${(value.holes || []).length} 个 | 操作 ${(value.operations || []).length} 步`,
        ]
        for (const op of value.operations || []) {
          const vol = op.volumeAfter != null ? ` 体积→${Number(op.volumeAfter).toFixed(2)}` : ''
          lines.push(`  #${op.index} ${op.type}${vol}${op.valid === false ? ' ⚠无效' : ''}`)
          // Edge indices renumber after every operation; showing what the
          // selector actually hit is the only way to confirm the choice.
          for (const e of op.edges || []) {
            const mid = e.mid ? ` 中点(${fmt1(e.mid)})` : ''
            lines.push(`      命中边 #${e.index} ${e.curve || ''} L=${Number(e.length).toFixed(2)}${mid}`)
          }
        }
        for (const w of value.warnings || []) lines.push(`⚠ ${w}`)
        if (value.fcstd) lines.push(`FCStd: ${value.fcstd}`)
        return [{ type: 'text', text: lines.join('\n') }]
      },
    },
    timeoutMs: TOOL_TIMEOUT_CEILING_MS,
    isConcurrencySafe: () => false,
    presentCall: (args) => ({ card: 'generic', title: 'FreeCAD STEP 编辑', kind: 'write', rawInput: args }),
    async execute(args, call) {
      if (!args?.input) throw new Error('freecad_edit_step needs an input path')
      if (!Array.isArray(args.operations) || args.operations.length === 0) {
        throw new Error('freecad_edit_step needs at least one operation')
      }
      return runWorker({
        action: 'edit',
        input: resolveWorkspacePath(args.input),
        output: args.output ? resolveWorkspacePath(args.output) : undefined,
        operations: args.operations,
        overwrite: Boolean(args.overwrite),
        saveFCStd: Boolean(args.saveFCStd),
      }, exec, call?.signal, timeoutOf(args))
    },
  }
}

function drawingTool(exec) {
  return {
    name: 'freecad_step_to_drawing',
    description:
      '把 STEP/STP 立体模型转成二维加工图纸：FreeCAD HLR 隐藏线消除，第一角法主视图/俯视图/右视图/轴测图，自动比例与图幅，整体尺寸、孔中心线、孔表、标题栏，导出 SVG / DXF / PDF / PNG。默认生成 A3、前三视图+轴测图、1:1 或自动适配比例。所有长度单位为 mm。',
    parameters: {
      type: 'object',
      properties: {
        input: { type: 'string', description: '输入 STEP/STP 绝对路径' },
        outputDir: { type: 'string', description: '输出目录；默认 <输入名>_drawing' },
        formats: { type: 'array', items: { type: 'string', enum: ['svg', 'dxf', 'pdf', 'png'] }, description: '输出格式，默认全部四种' },
        sheet: { type: 'string', enum: ['A4', 'A3', 'A2', 'A1'], description: '图幅，默认 A3' },
        views: { type: 'array', items: { type: 'string', enum: ['front', 'top', 'right', 'left', 'rear', 'bottom', 'iso'] }, description: '视图列表，默认 front/top/right/iso' },
        scale: { type: 'number', description: '固定比例（如 0.5 表示 1:2，2 表示 2:1）；0 或不填自动适配' },
        hiddenLines: { type: 'boolean', description: '是否绘制虚线隐藏线，默认 false' },
        dimensions: { type: 'boolean', description: '是否绘制总体尺寸，默认 true' },
        title: { type: 'string', description: '图纸标题' },
        header: { type: 'string', description: '图纸左上角页眉，默认 FreeCAD 二维加工图' },
        material: { type: 'string', description: '材料，如 6061-T6' },
        drawingNo: { type: 'string', description: '图号' },
        timeoutMs: timeoutParam(),
      },
      required: ['input'],
    },
    output: {
      schema: { ...OUTPUT_SCHEMA, properties: { files: { type: 'object', additionalProperties: true } } },
      render: (_args, value) => {
        const files = value.files || {}
        const lines = [
          `✅ 二维加工图 ${value.sheet} ${value.scaleLabel || `1:${value.scale}`}`,
          `输出目录: ${value.outputDir}`,
          ...Object.entries(files).map(([fmt, file]) => `  ${fmt.toUpperCase()}: ${file}`),
          `视图: ${Object.keys(value.views || {}).join(', ')} | 孔: ${(value.holes || []).length}`,
        ]
        return [{ type: 'text', text: lines.join('\n') }]
      },
    },
    timeoutMs: TOOL_TIMEOUT_CEILING_MS,
    isConcurrencySafe: () => false,
    presentCall: (args) => ({ card: 'generic', title: 'FreeCAD 二维加工图', kind: 'write', rawInput: args }),
    async execute(args, call) {
      if (!args?.input) throw new Error('freecad_step_to_drawing needs an input path')
      return runWorker({
        action: 'drawing',
        input: resolveWorkspacePath(args.input),
        outputDir: args.outputDir ? resolveWorkspacePath(args.outputDir) : undefined,
        formats: args.formats,
        options: {
          sheet: args.sheet,
          views: args.views,
          scale: args.scale,
          hiddenLines: args.hiddenLines,
          dimensions: args.dimensions,
          title: args.title,
          header: args.header,
          material: args.material,
          drawingNo: args.drawingNo,
        },
      }, exec, call?.signal, timeoutOf(args))
    },
  }
}

/**
 * freecad_status always answers, even when nothing is installed: it is the
 * first call a user makes, so a thrown error would hide the fix.
 */
function statusTool(exec) {
  return {
    name: 'freecad_status',
    description: '检查 FreeCADCmd 路径、版本以及本插件 worker 是否就绪；二维图纸生成异常时先调用它定位环境问题。',
    parameters: { type: 'object', properties: {} },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: (_args, value) => [{
        type: 'text',
        text: [
          `FreeCADCmd: ${value.freecadCmd}`,
          `来源: ${value.source ?? 'unknown'} | 存在: ${value.exists} | worker: ${value.workerExists}`,
          `版本: ${value.version || value.error || '未知'}`,
        ].join('\n'),
      }],
    },
    timeoutMs: 30_000,
    isConcurrencySafe: () => true,
    async execute() {
      const exists = isExecutableFile(exec.cmd)
      let version = null
      let error = null
      if (exists) {
        try {
          version = await probeFreeCADVersion(exec.cmd)
          if (version === null) error = 'FreeCADCmd --version printed no FreeCAD version'
        } catch (e) {
          error = e.message
        }
      } else {
        error = 'FreeCADCmd not found; set the FreeCAD path in DSH → Settings → FreeCAD'
      }
      return {
        freecadCmd: exec.cmd,
        source: exec.source,
        exists,
        workerExists: fsSync.existsSync(WORKER),
        version,
        error,
      }
    },
  }
}

/**
 * Read the FreeCAD path saved from DSH → Settings → FreeCAD.
 *
 * The settings page writes the volatile `freecadPath` field, which the Host
 * hands to `apply()` as a reference with `.get()`.  Older deployments stored
 * the same value as plain `config.settings.freecadPath` (or a bare
 * `config.freecadPath` in cordis.patch.yml); both keep working, and the
 * settings page wins because the user typed it last.
 * @param config - the plugin configuration DSH passes to {@link apply}.
 * @returns the saved path, or undefined when nothing is set.
 */
function settingsPath(config) {
  const field = config?.[PATH_KEY]
  const candidates = [
    field && typeof field === 'object' && typeof field.get === 'function' ? field.get() : field,
    config?.settings?.[PATH_KEY],
  ]
  for (const raw of candidates) {
    if (typeof raw === 'string' && raw.trim()) return raw.trim()
  }
  return undefined
}

const MEASURE_ITEM_SCHEMA = {
  type: 'object',
  additionalProperties: true,
  properties: {
    kind: {
      type: 'string',
      enum: ['distance', 'angle', 'radius'],
      description: '类型：distance 两点/面/边之间的距离，angle 两面或两直边夹角，radius 圆孔/圆柱直径',
    },
    a: {
      type: 'object',
      additionalProperties: true,
      description: '被测对象 A：{"point":[x,y,z]} 或 {"face":3} 或 {"edge":12}（1-based）',
    },
    b: {
      type: 'object',
      additionalProperties: true,
      description: '被测对象 B，格式同 a；kind=distance/angle 时必填',
    },
  },
  required: ['kind'],
}

function measureTool(exec) {
  return {
    name: 'freecad_measure',
    description:
      '在不改动模型的前提下量尺寸：点到点/点到面/面到面/边到边的距离（返回最近点与 ΔX/ΔY/ΔZ）、两面或两直边夹角、圆柱面或圆边的直径。配合 freecad_inspect_step 的 face/edge 索引使用；坐标单位为 mm。量出来的就是可以标到图纸上的数字。',
    parameters: {
      type: 'object',
      properties: {
        input: { type: 'string', description: 'STEP/STP 文件绝对路径' },
        items: {
          type: 'array',
          items: MEASURE_ITEM_SCHEMA,
          minItems: 1,
          description: '要量的项目列表',
        },
        timeoutMs: timeoutParam(),
      },
      required: ['input', 'items'],
    },
    output: {
      schema: { ...OUTPUT_SCHEMA, properties: { count: { type: 'number' } } },
      render: (_args, value) => {
        const items = value.measurements || []
        const okCount = value.resolved ?? items.filter((m) => !m.error).length
        const lines = [
          `📏 ${value.file?.name || value.input} — ${okCount}/${value.count ?? items.length} 项成功（单位 ${value.units || 'mm'}）`,
        ]
        for (const m of items) {
          if (m.error) {
            lines.push(`  #${m.index} ❌ ${m.kind}: ${m.error}`)
            continue
          }
          const unit = m.unit || 'mm'
          if (m.kind === 'angle') {
            if (m.normalAngle != null) {
              lines.push(`  #${m.index} 两平面夹角 ${Number(m.value).toFixed(3)}° | 外法线夹角 ${Number(m.normalAngle).toFixed(3)}°`)
            } else {
              const how = m.sharedVertex ? '（共顶点，0–180°）' : '（不共点，按直线取锐角）'
              lines.push(`  #${m.index} 夹角 ${Number(m.value).toFixed(3)}°${how}`)
            }
          } else if (m.kind === 'radius') {
            const r = m.radius != null ? ` (R${Number(m.radius).toFixed(3)})` : ''
            lines.push(`  #${m.index} 直径 Ø${Number(m.value).toFixed(3)}${r}`)
          } else {
            lines.push(`  #${m.index} 距离 ${Number(m.value).toFixed(3)} ${unit}`)
            if (m.planeOffset != null) {
              lines.push(`      两平面间距 ${Number(m.planeOffset).toFixed(3)} mm`)
            }
            if (m.delta) {
              lines.push(`      ΔX=${Number(m.delta[0]).toFixed(3)} ΔY=${Number(m.delta[1]).toFixed(3)} ΔZ=${Number(m.delta[2]).toFixed(3)}`)
            }
          }
        }
        if (value.timing?.elapsedMs != null) {
          lines.push(`  用时 ${(value.timing.elapsedMs / 1000).toFixed(1)}s`)
        }
        return [{ type: 'text', text: lines.join('\n') }]
      },
    },
    timeoutMs: TOOL_TIMEOUT_CEILING_MS,
    isConcurrencySafe: () => true,
    async execute(args, call) {
      if (!args?.input) throw new Error('freecad_measure needs an input path')
      if (!Array.isArray(args.items) || args.items.length === 0) {
        throw new Error('freecad_measure needs a non-empty items array')
      }
      return runWorker({
        action: 'measure',
        input: resolveWorkspacePath(args.input),
        items: args.items,
      }, exec, call?.signal, timeoutOf(args))
    },
  }
}

export async function apply(ctx, config = {}) {
  const saved = settingsPath(config)
  // The path is resolved per call so a value saved from the settings card takes
  // effect without restarting DSH.
  const exec = {
    get cmd() { return resolveFreeCAD(saved, config).cmd },
    get source() { return resolveFreeCAD(saved, config).source },
  }
  const tools = [
    inspectTool(exec),
    editTool(exec),
    drawingTool(exec),
    measureTool(exec),
    statusTool(exec),
  ]
  const summary = tools.map((tool) => ({
    name: tool.name,
    required: tool.parameters.required || [],
    timeoutMs: tool.timeoutMs,
  }))
  const resolved = resolveFreeCAD(saved, config)
  const result = {
    freecadCmd: resolved.cmd,
    source: resolved.source,
    exists: isExecutableFile(resolved.cmd),
    worker: WORKER,
    workerExists: fsSync.existsSync(WORKER),
    tools: summary,
  }
  // Self-test mode: no DSH context, just report what would be registered.
  if (ctx === undefined || ctx === null || typeof ctx.tools?.register !== 'function') {
    return result
  }
  for (const tool of tools) {
    try {
      ctx.tools.register(tool)
    } catch (error) {
      console.error(`[freecad] tool registration skipped: ${error}`)
    }
  }
  // Report the resolved executable once, so a misconfigured path is visible in
  // the DSH log instead of only in the first failing tool call.
  console.log(`[freecad] FreeCADCmd: ${resolved.cmd} (${resolved.source})`)
  // Cordis reads a plugin's return value as its disposer: returning anything
  // that is not a function throws "Invalid effect" and fails the whole entry,
  // which is why the mounted path must return nothing (the self-test above is
  // the only caller that uses the status object).
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href
if (isMain && process.argv.includes('--self-test')) {
  const status = await apply(undefined, {})
  console.log(resultText(status))
}

/** @internal exposed for test/call_tool.mjs and local debugging. */
export const _internal = {
  freecadCmdFrom,
  freecadCandidates,
  resolveFreeCAD,
  parseFreeCADVersion,
  KNOWN_FREECAD_DIRS,
  PATH_KEY,
  settingsPath,
  timeoutOf,
  runWorker,
  TIMEOUT_MS,
  MAX_TIMEOUT_MS,
  TOOL_TIMEOUT_CEILING_MS,
  DETAIL_PAGE,
}
