#!/usr/bin/env node
/**
 * Web conformance host — fixture codegen.
 *
 * 1. Copies every web-applicable fixture layout from the conformance
 *    manifest into src/Layouts/pages/ under a stable synthetic name
 *    (fx_NNNN.json → component FxNNNN).
 * 2. Runs `rjui build` (rjui_tools React codegen) over them — the exact
 *    production codegen path.
 * 3. Emits src/generated/fixtureRegistry.tsx (fixture id → lazy route),
 *    src/generated/fixture-map.json (metadata for the runner) and
 *    src/generated/conformance-colors.css (named-color utilities).
 *
 * Everything under src/generated/ and src/Layouts/ is a build artifact
 * (@generated) and is gitignored.
 *
 * Paths (all overridable):
 *   --conformance-dir / JSONUI_CONFORMANCE_DIR  default: ../../.. of this script (repo conformance/)
 *   --rjui / RJUI_TOOLS_PATH                    default: <repo>/rjui_tools
 *   --ruby / RUBY_BIN                           default: ruby
 */

import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const hostDir = path.resolve(scriptDir, '..');

function arg(name, envName, fallback) {
  const idx = process.argv.indexOf(name);
  if (idx !== -1 && process.argv[idx + 1]) return process.argv[idx + 1];
  if (envName && process.env[envName]) return process.env[envName];
  return fallback;
}

const conformanceDir = path.resolve(
  arg('--conformance-dir', 'JSONUI_CONFORMANCE_DIR', path.resolve(hostDir, '../..'))
);
const rjuiDir = path.resolve(
  arg('--rjui', 'RJUI_TOOLS_PATH', path.resolve(conformanceDir, '../rjui_tools'))
);
const rubyBin = arg('--ruby', 'RUBY_BIN', 'ruby');

const manifestPath = path.join(conformanceDir, 'manifest.json');
if (!fs.existsSync(manifestPath)) {
  console.error(`manifest not found: ${manifestPath} — run \`jui conformance generate\` first`);
  process.exit(1);
}
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));

// ---------------------------------------------------------------- clean
const layoutsPagesDir = path.join(hostDir, 'src/Layouts/pages');
const layoutsResourcesDir = path.join(hostDir, 'src/Layouts/Resources');
const generatedDir = path.join(hostDir, 'src/generated');
for (const dir of [layoutsPagesDir, layoutsResourcesDir, generatedDir]) {
  fs.rmSync(dir, { recursive: true, force: true });
}
fs.mkdirSync(layoutsPagesDir, { recursive: true });

// ---------------------------------------------------------------- copy layouts
const webFixtures = manifest.fixtures.filter((f) => f.platforms.includes('web'));
const entries = [];
webFixtures.forEach((fixture, i) => {
  const name = `fx_${String(i + 1).padStart(4, '0')}`;
  const component = `Fx${String(i + 1).padStart(4, '0')}`;
  fs.copyFileSync(
    path.join(conformanceDir, fixture.layout),
    path.join(layoutsPagesDir, `${name}.json`)
  );
  // `state` (interactive fixtures) is the conformanceState contract the
  // StateHost provider satisfies — see src/conformanceState.tsx.
  entries.push({ id: fixture.id, component, state: fixture.state ?? null });
});
console.log(`[generate] copied ${entries.length} web-applicable fixture layouts`);

// Companion embedded-screen layouts (Embed fixtures) keep their BARE names
// so the fixture's `screen: "embed_root"` reference resolves to the
// generated EmbedRoot component (`@/generated/components/EmbedRoot`).
const companionPaths = new Set();
for (const fixture of webFixtures) {
  for (const companion of fixture.companions ?? []) companionPaths.add(companion);
}
for (const companion of companionPaths) {
  const base = path.basename(companion).replace(/\.layout\.json$/, '.json');
  fs.copyFileSync(path.join(conformanceDir, companion), path.join(layoutsPagesDir, base));
}
if (companionPaths.size > 0) {
  console.log(`[generate] copied ${companionPaths.size} companion embedded-screen layout(s)`);
}

// Responsive machinery: variant-file dispatches (and landscape branches)
// import `@/hooks/useMediaQuery`, normally installed into consumer
// projects by `rjui init`. Vendor the current template unconditionally —
// build artifact, gitignored.
const hooksDir = path.join(hostDir, 'src/hooks');
fs.rmSync(hooksDir, { recursive: true, force: true });
fs.mkdirSync(hooksDir, { recursive: true });
fs.copyFileSync(
  path.join(rjuiDir, 'lib/react/templates/use_media_query.ts'),
  path.join(hooksDir, 'useMediaQuery.ts')
);
console.log('[generate] vendored use_media_query.ts template into src/hooks/');

// Embed fixtures need the EmbedContainer runtime helper (normally emitted
// into consumer projects by `rjui init`). Vendor the current template so
// the host always matches the codegen it just ran (template v2 for
// isolated). Emitted as a build artifact next to src/, gitignored.
const extensionsDir = path.join(hostDir, 'src/components/extensions');
fs.rmSync(extensionsDir, { recursive: true, force: true });
if (companionPaths.size > 0) {
  fs.mkdirSync(extensionsDir, { recursive: true });
  fs.copyFileSync(
    path.join(rjuiDir, 'lib/react/templates/EmbedContainer.tsx'),
    path.join(extensionsDir, 'EmbedContainer.tsx')
  );
  console.log('[generate] vendored EmbedContainer.tsx template into src/components/extensions/');
}

// ---------------------------------------------------------------- rjui build
const rjuiBin = path.join(rjuiDir, 'bin/rjui');
if (!fs.existsSync(rjuiBin)) {
  console.error(`rjui_tools not found: ${rjuiBin} (set RJUI_TOOLS_PATH)`);
  process.exit(1);
}
console.log(`[generate] running rjui build (${rjuiDir})`);
const build = spawnSync(rubyBin, [rjuiBin, 'build'], {
  cwd: hostDir,
  stdio: ['ignore', 'pipe', 'pipe'],
  encoding: 'utf8',
  maxBuffer: 64 * 1024 * 1024,
});
fs.writeFileSync(path.join(hostDir, 'rjui-build.log'), (build.stdout ?? '') + (build.stderr ?? ''));
if (build.status !== 0) {
  console.error('[generate] rjui build failed — see rjui-build.log');
  process.exit(1);
}
const buildErrors = (build.stdout ?? '')
  .split('\n')
  .filter((l) => l.includes('[ERROR]'));
if (buildErrors.length > 0) {
  console.warn(`[generate] rjui build reported ${buildErrors.length} error line(s) — see rjui-build.log`);
}

// ---------------------------------------------------------------- registry
const componentsDir = path.join(generatedDir, 'components');
const dataDir = path.join(generatedDir, 'data');
let generatedCount = 0;
for (const entry of entries) {
  entry.hasComponent = fs.existsSync(path.join(componentsDir, `${entry.component}.tsx`));
  entry.hasData = fs.existsSync(path.join(dataDir, `${entry.component}Data.ts`));
  if (entry.hasComponent) generatedCount += 1;
}
console.log(`[generate] ${generatedCount}/${entries.length} components generated`);

// Companion screens are registered into the template's global screen table
// so isolated-embed pushes can resolve ANY companion by name — the
// per-fixture resolver table only ever contains the root screen.
const pascalCase = (snake) => snake.replace(/(?:^|_)([a-z0-9])/g, (_, c) => c.toUpperCase());
const companionComponents = [...companionPaths]
  .map((companion) => pascalCase(path.basename(companion).replace(/\.layout\.json$/, '')))
  .filter((component) => fs.existsSync(path.join(componentsDir, `${component}.tsx`)))
  .sort();

const registryLines = [];
registryLines.push('// @generated by scripts/generate.mjs — DO NOT EDIT');
registryLines.push("import React, { lazy } from 'react';");
registryLines.push("import { StateHost } from '../conformanceState';");
if (companionComponents.length > 0) {
  registryLines.push("import { registerEmbedScreens } from '../components/extensions/EmbedContainer';");
  for (const component of companionComponents) {
    registryLines.push(`import ${component} from './components/${component}';`);
  }
  registryLines.push('');
  registryLines.push('registerEmbedScreens({');
  for (const component of companionComponents) {
    const screen = component.replace(/([a-z0-9])([A-Z])/g, '$1_$2').toLowerCase();
    registryLines.push(`  ${JSON.stringify(screen)}: ${component},`);
  }
  registryLines.push('});');
}
registryLines.push('');
registryLines.push('type Entry = { component: React.LazyExoticComponent<React.ComponentType> };');
registryLines.push('');
registryLines.push('export const fixtures: Record<string, Entry> = {');
for (const entry of entries) {
  if (!entry.hasComponent) continue;
  registryLines.push(`  ${JSON.stringify(entry.id)}: {`);
  registryLines.push('    component: lazy(async () => {');
  registryLines.push(`      const m = await import('./components/${entry.component}');`);
  if (entry.state) {
    // interactive: stateful conformanceState provider (generic, per contract)
    const createData = entry.hasData
      ? `d.create${entry.component}Data as () => Record<string, unknown>`
      : '() => ({})';
    if (entry.hasData) {
      registryLines.push(`      const d = await import('./data/${entry.component}Data');`);
    }
    registryLines.push('      const C = m.default as React.ComponentType<{ data: unknown }>;');
    registryLines.push(`      const state = ${JSON.stringify(entry.state)};`);
    registryLines.push(
      `      return { default: () => <StateHost createData={${createData}} state={state} Component={C as React.ComponentType<{ data: Record<string, unknown> }>} /> };`
    );
  } else {
    const dataImport = entry.hasData
      ? `const d = await import('./data/${entry.component}Data'); const data = d.create${entry.component}Data();`
      : 'const data = {};';
    registryLines.push(`      ${dataImport}`);
    registryLines.push('      const C = m.default as React.ComponentType<{ data: unknown }>;');
    registryLines.push('      return { default: () => <C data={data} /> };');
  }
  registryLines.push('    }),');
  registryLines.push('  },');
}
registryLines.push('};');
registryLines.push('');
fs.writeFileSync(path.join(generatedDir, 'fixtureRegistry.tsx'), registryLines.join('\n'));

fs.writeFileSync(
  path.join(generatedDir, 'fixture-map.json'),
  JSON.stringify(
    Object.fromEntries(entries.map((e) => [e.id, { component: e.component, hasComponent: e.hasComponent }])),
    null,
    2
  ) + '\n'
);

// ---------------------------------------------------------------- colors css
// rjui build extracts hex colors into Layouts/Resources/colors.json and
// rewrites layouts to named keys (bg-<key> etc.). Emit plain utilities so the
// classes resolve regardless of Tailwind theme configuration.
const colorsPath = path.join(layoutsResourcesDir, 'colors.json');
const cssLines = ['/* @generated by scripts/generate.mjs — DO NOT EDIT */'];
if (fs.existsSync(colorsPath)) {
  const colors = JSON.parse(fs.readFileSync(colorsPath, 'utf8'));
  const palette = colors[colors.fallback_mode || 'light'] || {};
  for (const [key, hex] of Object.entries(palette)) {
    cssLines.push(`.bg-${key} { background-color: ${hex}; }`);
    cssLines.push(`.text-${key} { color: ${hex}; }`);
    cssLines.push(`.border-${key} { border-color: ${hex}; }`);
    cssLines.push(`.placeholder-${key}::placeholder { color: ${hex}; }`);
  }
}
cssLines.push('');
fs.writeFileSync(path.join(generatedDir, 'conformance-colors.css'), cssLines.join('\n'));

console.log('[generate] wrote fixtureRegistry.tsx, fixture-map.json, conformance-colors.css');
const failed = entries.filter((e) => !e.hasComponent);
if (failed.length > 0) {
  console.warn(`[generate] fixtures WITHOUT component (will be reported as error):`);
  for (const f of failed) console.warn(`  - ${f.id}`);
}
