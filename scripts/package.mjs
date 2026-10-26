#!/usr/bin/env node
/**
 * Build an installable dsh-freecad package.
 *
 *   node scripts/package.mjs [--out <dir>] [--name <basename>]
 *
 * The archive is a plain zip that unpacks to a single folder named
 * `dsh-freecad/`.  Inside it the plugin is laid out exactly as a DSH profile
 * expects, so the receiver can either run `node scripts/install.mjs` or copy
 * the folder into `<profile>/plugins/` by hand.
 *
 * Nothing machine-specific is packaged: no profile copies, no __pycache__, no
 * test artifacts.  The file list is derived from package.json "files" plus the
 * installer and the docs, so the package and the repository cannot drift apart.
 */
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import crypto from 'node:crypto'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, '..')
const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'))

const args = process.argv.slice(2)
function arg(name, fallback) {
  const at = args.indexOf(`--${name}`)
  return at >= 0 && args[at + 1] ? args[at + 1] : fallback
}
const outDir = path.resolve(arg('out', path.join(root, 'dist')))
const baseName = arg('name', `dsh-freecad-${pkg.version}`)
const stageRoot = path.join(os.tmpdir(), `dsh-freecad-pack-${process.pid}`)
const stage = path.join(stageRoot, 'dsh-freecad')

// every path that may be shipped, relative to the repository root
const SKIP = new Set(['node_modules', '.git', '__pycache__', 'dist', 'test', '_stash'])
function collect(relDir, acc = []) {
  const abs = path.join(root, relDir)
  if (!fs.existsSync(abs)) return acc
  for (const entry of fs.readdirSync(abs, { withFileTypes: true })) {
    if (SKIP.has(entry.name)) continue
    if (entry.name.endsWith('.pyc') || entry.name.endsWith('.bak') || entry.name.includes('.bak-')) continue
    const rel = path.join(relDir, entry.name)
    if (entry.isDirectory()) collect(rel, acc)
    else acc.push(rel)
  }
  return acc
}

const wanted = []
for (const entry of pkg.files ?? []) wanted.push(entry)
wanted.push('scripts/install.mjs')
wanted.push('INSTALL-FOR-AI.md')

const files = new Set()
for (const entry of wanted) {
  const abs = path.join(root, entry)
  if (!fs.existsSync(abs)) {
    console.warn(`[package] skip missing entry: ${entry}`)
    continue
  }
  if (fs.statSync(abs).isDirectory()) {
    for (const rel of collect(entry)) files.add(rel)
  } else {
    files.add(entry)
  }
}
for (const rel of collect('docs')) files.add(rel)
files.add('package.json')

// stage the tree
fs.rmSync(stageRoot, { recursive: true, force: true })
fs.mkdirSync(stage, { recursive: true })
for (const rel of [...files].sort()) {
  const to = path.join(stage, rel)
  fs.mkdirSync(path.dirname(to), { recursive: true })
  fs.copyFileSync(path.join(root, rel), to)
}

// a package is only installable if the worker and the host entry are present
for (const must of ['index.js', 'package.json', 'cordis.patch.yml', 'dsh/fc_worker.py',
  'dsh/fc_common.py', 'dsh/fc_render.py', 'scripts/install.mjs',
  'INSTALL-FOR-AI.md', 'examples/demo_bracket.step']) {
  if (!fs.existsSync(path.join(stage, must))) {
    console.error(`[package] missing required file: ${must}`)
    process.exit(1)
  }
}

// zip it: the archive root is the `dsh-freecad/` folder itself, so unpacking
// gives a ready-to-copy plugin directory instead of a staging wrapper
fs.mkdirSync(outDir, { recursive: true })
const zipPath = path.join(outDir, `${baseName}.zip`)
fs.rmSync(zipPath, { force: true })
execFileSync('powershell', ['-NoProfile', '-Command',
  `Compress-Archive -Path '${stage}' -DestinationPath '${zipPath}' -Force`],
  { stdio: 'inherit' })

function sha256(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')
}

const manifest = {
  name: pkg.name,
  version: pkg.version,
  builtAt: new Date().toISOString(),
  files: [...files].sort().map((rel) => ({
    path: rel,
    bytes: fs.statSync(path.join(stage, rel)).size,
    sha256: sha256(path.join(stage, rel)),
  })),
  zip: { path: zipPath, bytes: fs.statSync(zipPath).size, sha256: sha256(zipPath) },
}
fs.writeFileSync(path.join(outDir, `${baseName}.manifest.json`),
  `${JSON.stringify(manifest, null, 2)}\n`, 'utf8')
fs.writeFileSync(path.join(outDir, 'SHA256SUMS.txt'),
  manifest.files.map((f) => `${f.sha256}  dsh-freecad/${f.path}`).join('\n') + '\n', 'utf8')

console.log(`[package] ${files.size} files staged from ${root}`)
console.log(`[package] zip: ${zipPath} (${(manifest.zip.bytes / 1024).toFixed(1)} KiB)`)
console.log(`[package] sha256: ${manifest.zip.sha256}`)
