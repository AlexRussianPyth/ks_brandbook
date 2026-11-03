#!/usr/bin/env node
// Генерирует платформенные форматы из tokens/tokens.json (единый источник истины).
// Запуск: node tools/build.mjs  (или npm run build)
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const DIST = join(ROOT, 'dist');
const tokens = JSON.parse(readFileSync(join(ROOT, 'tokens', 'tokens.json'), 'utf8'));

// --- плоский список токенов с разрешением ссылок {path.to.token} ---

const flat = new Map(); // "color.signal-blue" -> значение

function walk(node, path) {
  if (Array.isArray(node) || typeof node !== 'object' || node === null) return;
  if ('$value' in node) {
    flat.set(path.join('.'), resolve(node.$value));
    return;
  }
  for (const [key, value] of Object.entries(node)) {
    if (key.startsWith('$')) continue;
    walk(value, [...path, key]);
  }
}

function resolve(value) {
  if (typeof value !== 'string') return value;
  return value.replace(/\{([^}]+)\}/g, (_, ref) => {
    const target = flat.get(ref.trim());
    if (target === undefined) throw new Error(`Неизвестная ссылка на токен: {${ref}}`);
    return target;
  });
}

walk(tokens, []);

const cssVal = (v) =>
  typeof v === 'string' ? v.replace(/(\d[\d.]*)\s+(mm|cm|pt|px|rem|em)/g, '$1$2') : String(v);
const varName = (k) => `--ks-${k.replaceAll('.', '-')}`;
const kebab = (k) => k.replaceAll('.', '-');

// --- CSS custom properties ---

const cssLines = [...flat.entries()].map(([k, v]) => `  ${varName(k)}: ${cssVal(v)};`);
write(DIST, 'tokens.css', `:root {\n${cssLines.join('\n')}\n}\n`);

// --- SCSS переменные ---

write(DIST, 'tokens.scss', [...flat.entries()].map(([k, v]) => `$ks-${kebab(k)}: ${cssVal(v)};`).join('\n') + '\n');

// --- JS-модуль (ESM): дерево с разрешёнными ссылками ---

function buildTree() {
  const tree = {};
  for (const [key, value] of flat) {
    const parts = key.split('.');
    let cur = tree;
    for (const part of parts.slice(0, -1)) cur = cur[part] ??= {};
    cur[parts.at(-1)] = value;
  }
  return tree;
}

const tree = buildTree();
write(
  DIST,
  'index.js',
  `// Сгенерировано из tokens/tokens.json — не редактировать вручную (npm run build)\n` +
    `export const tokens = ${JSON.stringify(tree, null, 2)};\n\nexport default tokens;\n`,
);

// --- Tailwind preset ---

const pick = (prefix) =>
  Object.fromEntries(
    [...flat.entries()]
      .filter(([k]) => k.startsWith(prefix))
      .map(([k, v]) => [kebab(k.slice(prefix.length)), v]),
  );

const preset = {
  theme: {
    extend: {
      colors: { ...pick('color.'), ...pick('role.') },
      fontFamily: { base: [tree.font.family.base] },
      fontWeight: tree.font.weight,
    },
  },
};

write(
  DIST,
  'tailwind-preset.cjs',
  `// Сгенерировано из tokens/tokens.json — не редактировать вручную (npm run build)\n` +
    `module.exports = ${JSON.stringify(preset, null, 2)};\n`,
);
write(
  DIST,
  'tailwind-preset.mjs',
  `// Сгенерировано из tokens/tokens.json — не редактировать вручную (npm run build)\n` +
    `export default ${JSON.stringify(preset, null, 2)};\n`,
);

console.log(`dist/: tokens.css, tokens.scss, index.js, tailwind-preset.cjs, tailwind-preset.mjs (${flat.size} токенов)`);

function write(dir, name, content) {
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, name), content);
}
