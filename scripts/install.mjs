#!/usr/bin/env node
/**
 * Zero-dependency installer for dsh-freecad.
 *
 *   node scripts/install.mjs
 *   node scripts/install.mjs --profile "C:\Users\me\.dsh\profiles\other"
 *
 * It does exactly what DSH needs and nothing else:
 *   1. copy this package into <profile>/plugins/dsh-freecad
 *   2. declare it in <profile>/package.json (file: dependency + bundle entry)
 *   3. mount the entry in cordis.patch.yml as a top-level row (creating the file if absent)
 *   4. try `pnpm install`; when pnpm is unavailable, copy the package into
 *      <profile>/node_modules/dsh-freecad by hand
 *
 * Every modified file is backed up first.  Re-running is safe and idempotent.
 */
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const source = path.resolve(here, '..')
const args = process.argv.slice(2)
function argValue(name) {
  const at = args.indexOf(`--${name}`)
  return at >= 0 ? args[at + 1] : undefined
}

const profile = path.resolve(
  argValue('profile') || process.env.DSH_PROFILE
    || path.join(os.homedir(), '.dsh', 'profiles', 'desktop'),
)
const installDir = path.join(profile, 'plugins', 'dsh-freecad')
const modulesDir = path.join(profile, 'node_modules', 'dsh-freecad')
const packageFile = path.join(profile, 'package.json')
const patchFile = path.join(profile, 'cordis.patch.yml')
const stamp = new Date().toISOString().replace(/[:.]/g, '-')

const COPY = ['index.js', 'package.json', 'cordis.patch.yml', 'README.md', 'LICENSE',
  'INSTALL-FOR-AI.md', 'dsh', 'examples', 'scripts', 'docs']
const BASE_BUNDLES = ['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-web-app']

function log(message) {
  console.log(`[install] ${message}`)
}
function fail(message) {
  console.error(`[install] ERROR: ${message}`)
  process.exit(1)
}
function backup(file) {
  if (!fs.existsSync(file)) return
  const dest = `${file}.bak-${stamp}`
  fs.copyFileSync(file, dest)
  log(`backup: ${dest}`)
}
function copyTree(from, to) {
  fs.rmSync(to, { recursive: true, force: true })
  fs.mkdirSync(to, { recursive: true })
  for (const name of COPY) {
    const src = path.join(from, name)
    if (!fs.existsSync(src)) continue
    fs.cpSync(src, path.join(to, name), {
      recursive: true,
      filter: (p) => !p.includes('__pycache__') && !p.endsWith('.pyc'),
    })
  }
}

// ---------------------------------------------------------------- 1. files
if (path.resolve(installDir) === path.resolve(source)) {
  fail('this package is already the installed plugin; run it from a copy')
}
if (!fs.existsSync(profile)) fail(`profile directory does not exist: ${profile}`)
copyTree(source, installDir)
for (const must of ['index.js', path.join('dsh', 'fc_worker.py')]) {
  if (!fs.existsSync(path.join(installDir, must))) fail(`copy incomplete: ${must} missing`)
}
log(`installed files: ${installDir}`)

// ------------------------------------------------------------ 2. package.json
if (!fs.existsSync(packageFile)) {
  fail(`profile has no package.json: ${packageFile}\n` +
    'Start DSH once with this profile so it creates the profile, then re-run.')
}
const pkgText = fs.readFileSync(packageFile, 'utf8').replace(/^\uFEFF/, '')
let pkg
try {
  pkg = JSON.parse(pkgText)
} catch (error) {
  fail(`profile package.json is not valid JSON: ${error.message}`)
}
pkg.dependencies ??= {}
pkg.dsh ??= {}
pkg.dsh.profile ??= {}
let bundles = Array.isArray(pkg.dsh.profile.bundles) ? pkg.dsh.profile.bundles : null
if (bundles === null) {
  bundles = [...BASE_BUNDLES]
  pkg.dsh.profile.bundles = bundles
  log('profile had no bundle list; seeded the DSH base bundles')
}
let changed = false
if (pkg.dependencies['dsh-freecad'] !== 'file:./plugins/dsh-freecad') {
  pkg.dependencies['dsh-freecad'] = 'file:./plugins/dsh-freecad'
  changed = true
}
if (!bundles.includes('dsh-freecad')) {
  bundles.push('dsh-freecad')
  changed = true
}
if (changed) {
  backup(packageFile)
  fs.writeFileSync(packageFile, `${JSON.stringify(pkg, null, 2)}\n`, 'utf8')
  log('profile package.json updated')
} else {
  log('profile package.json already declares dsh-freecad')
}

// --------------------------------------------------------- 3. cordis.patch.yml
// The entry is declared as a top-level patch row (id + name), NOT inside an
// `insert:` block: the Settings UI can only write config into a top-level row,
// so an inserted entry would refuse every save with `settings/rejected`.
let patch = fs.existsSync(patchFile) ? fs.readFileSync(patchFile, 'utf8') : ''
if (/name:\s*['"]?dsh-freecad['"]?(\s|$)/m.test(patch)) {
  log('profile cordis.patch.yml already mounts dsh-freecad')
} else {
  if (patch) backup(patchFile)
  if (patch && !patch.endsWith('\n')) patch += '\n'
  patch += "\n# dsh-freecad: STEP/CAD inspection, editing and 2D drawing tools\n"
    + "- id: freecad\n  name: dsh-freecad\n"
  fs.writeFileSync(patchFile, patch, 'utf8')
  log('profile cordis.patch.yml updated')
}

// ---------------------------------------------------------- 4. node_modules
function findPnpm() {
  if (process.env.DSH_PNPM && fs.existsSync(process.env.DSH_PNPM)) return process.env.DSH_PNPM
  const runtimes = path.join(os.homedir(), '.dsh', 'dsh-runtimes')
  if (!fs.existsSync(runtimes)) return undefined
  for (const name of fs.readdirSync(runtimes)) {
    const candidate = path.join(runtimes, name, 'dependencies', 'pnpm', 'bin', 'pnpm.cjs')
    if (fs.existsSync(candidate)) return candidate
  }
  return undefined
}

/** True when node_modules/dsh-freecad holds this package (link or copy). */
function realPackage() {
  return fs.existsSync(path.join(modulesDir, 'index.js'))
}

/**
 * Ask pnpm what `dsh-freecad` resolves to, without mutating the profile.
 * @returns true (resolves), false (pnpm says it does not) or null (unknown,
 *   e.g. pnpm could not run at all).
 */
function pnpmResolves(pnpmBin) {
  const result = spawnSync(process.execPath, [pnpmBin, 'list', 'dsh-freecad', '--depth', '0'],
    { cwd: profile, encoding: 'utf8' })
  if (result.error) return null
  const text = `${result.stdout ?? ''}${result.stderr ?? ''}`
  if (/ERR_PNPM|No projects found|Cannot find/i.test(text)) return null
  return /\bdsh-freecad\b/.test(text)
}

let linked = false
const pnpm = findPnpm()
if (pnpm) {
  log(`pnpm install (${pnpm})`)
  const result = spawnSync(process.execPath,
    [pnpm, 'install', '--config.confirmModulesPurge=false'],
    { cwd: profile, stdio: 'inherit' })
  // pnpm can be non-zero because of OTHER packages in this profile (a missing
  // registry entry, a peer conflict).  The package's own resolution is what
  // matters, so look at its state instead of the exit status alone.
  const resolved = pnpmResolves(pnpm)
  if (result.status === 0 && resolved !== false) {
    linked = true
    log(`pnpm linked: ${modulesDir}`)
  } else if (resolved === true || realPackage()) {
    linked = true
    log(`dsh-freecad is installed at ${modulesDir}`)
    if (result.status !== 0) {
      log(`note: pnpm exited ${result.status}; that failure is in another package, `
        + 'dsh-freecad itself is in place')
    }
  } else {
    log(`pnpm exited ${result.status} and did not install the package; falling back to a direct copy`)
  }
}
if (!linked) {
  // No pnpm: DSH resolves the bundle through node_modules, so place a real
  // copy there.  The file: dependency stays declared, so a later pnpm run
  // simply replaces this copy with a proper link.
  copyTree(installDir, modulesDir)
  log(`copied into node_modules: ${modulesDir} (no pnpm needed)`)
}

// ------------------------------------------------------------------ 5. check
const worker = path.join(modulesDir, 'dsh', 'fc_worker.py')
for (const must of ['index.js', 'dsh/fc_worker.py']) {
  if (!fs.existsSync(path.join(modulesDir, must))) {
    fail(`node_modules copy incomplete: ${must} missing`)
  }
}
const selfTest = path.join(installDir, 'index.js')
const check = spawnSync(process.execPath, [selfTest, '--self-test'],
  { encoding: 'utf8', cwd: installDir })
const stdout = (check.stdout ?? '').trim()
let info = null
try {
  info = JSON.parse(stdout.replace(/^\uFEFF/, ''))
} catch {
  info = null
}
if (!info) {
  if (check.error) {
    // Never end on a red error when the install itself is complete: say what
    // is in place, what could not be checked, and how to check it by hand.
    log(`files: ${installDir}`)
    log(`linked: ${modulesDir}`)
    log(`WARNING: self-test could not run here (${check.error.code ?? check.error.message}).`)
    log('the plugin is installed; verify it by calling freecad_status in DSH after the restart')
    log(`manual check: cd "${modulesDir}" ; node index.js --self-test`)
    process.exit(0)
  }
  fail(`self-test failed (exit ${check.status}):\n${stdout}\n${check.stderr ?? ''}`)
}
log(`self-test: freecadCmd=${info.freecadCmd}`)
log(`self-test: freecadCmd exists = ${info.exists}`)
log(`self-test: worker = ${worker}`)
log(`self-test: tools = ${info.tools.map((t) => t.name).join(', ')}`)
if (!info.exists) {
  log('WARNING: FreeCADCmd was not found.  After restarting DSH, set the path in '
    + 'DSH -> Settings -> FreeCAD (or use the FREECAD_CMD environment variable).')
}

console.log('')
console.log('[install] done. Restart DSH Desktop, then call freecad_status.')
console.log('[install] verify with the bundled sample:')
console.log(`[install]   inspect ${path.join(installDir, 'examples', 'demo_bracket.step')}`)
console.log('[install] expected: 100 x 60 x 37 mm, 5 holes (4 x 脴9 + 1 x 脴25)')

