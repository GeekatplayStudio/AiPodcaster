#!/usr/bin/env node
// Verifies that every literal t("...") key used in src/ exists in each locale for the
// namespace its file uses (or in "common", the fallback namespace).
// Usage: node scripts/check-i18n.mjs [--ns <namespace>] [--strict]
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const root = new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const src = join(root, "src");
const localesDir = join(src, "i18n", "locales");
const args = process.argv.slice(2);
const onlyNs = args.includes("--ns") ? args[args.indexOf("--ns") + 1] : null;

const languages = readdirSync(localesDir).filter((name) => statSync(join(localesDir, name)).isDirectory());
const load = (language, namespace) => {
  try {
    return JSON.parse(readFileSync(join(localesDir, language, `${namespace}.json`), "utf8"));
  } catch {
    return {};
  }
};

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return name === "i18n" ? [] : walk(path);
    return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : [];
  });
}

const keyPattern = /\bt\(\s*(["'])((?:\\.|(?!\1).)*)\1/g;
const nsPattern = /useTranslation\(\s*["']([\w-]+)["']\s*\)/;
let missingTotal = 0;
const unused = new Map();

for (const file of walk(src)) {
  const code = readFileSync(file, "utf8");
  if (!code.includes("useTranslation")) continue;
  const namespace = code.match(nsPattern)?.[1] ?? "common";
  if (onlyNs && namespace !== onlyNs) continue;
  // t("...") calls plus <Trans i18nKey="..."> / i18nKey={"..."} props.
  const transPattern = /\bi18nKey=\{?\s*(["'])((?:\\.|(?!\1).)*)\1/g;
  const keys = [...code.matchAll(keyPattern), ...code.matchAll(transPattern)].map((match) => match[2].replace(/\\(["'\\])/g, "$1"));
  for (const language of languages) {
    const own = load(language, namespace);
    const common = load(language, "common");
    const missing = [...new Set(keys)].filter((key) => !(key in own) && !(key in common));
    if (missing.length) {
      missingTotal += missing.length;
      console.log(`${relative(root, file)} [${namespace}] ${language}: ${missing.length} missing`);
      for (const key of missing) console.log(`    ${JSON.stringify(key)}`);
    }
  }
  for (const key of keys) unused.set(`${namespace}\u0000${key}`, true);
}

for (const language of languages) {
  for (const file of readdirSync(join(localesDir, language))) {
    const namespace = file.replace(/\.json$/, "");
    if (onlyNs && namespace !== onlyNs) continue;
    const dictionary = load(language, namespace);
    for (const [key, value] of Object.entries(dictionary)) {
      const placeholders = (text) => [...String(text).matchAll(/\{\{\s*(\w+)\s*\}\}/g)].map((m) => m[1]).sort().join(",");
      if (placeholders(key) !== placeholders(value)) {
        missingTotal += 1;
        console.log(`${language}/${namespace}.json: placeholder mismatch for ${JSON.stringify(key)} -> ${JSON.stringify(value)}`);
      }
    }
  }
}

if (missingTotal) {
  console.log(`\n${missingTotal} problem(s) found.`);
  process.exit(1);
}
console.log(`i18n OK: ${languages.join(", ")}${onlyNs ? ` (namespace ${onlyNs})` : ""}`);
