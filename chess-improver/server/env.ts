import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * Keys that this loader put into process.env, and the exact value it set.
 * Real process environment variables always win; only file-managed values are
 * updated or removed when `.env` changes or disappears.
 */
const managed = new Map<string, string>();

function parseEnvFile(filePath: string): Map<string, string> {
  const values = new Map<string, string>();
  if (!fs.existsSync(filePath)) return values;
  for (const rawLine of fs.readFileSync(filePath, 'utf8').replace(/^\uFEFF/, '').split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const match = line.match(/^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/);
    if (!match) continue;
    const [, key, raw] = match;
    let value: string;
    if (raw.startsWith('"') || raw.startsWith("'")) {
      const quote = raw[0];
      const end = raw.indexOf(quote, 1);
      // Ignore malformed lines rather than accidentally using a partial key.
      if (end < 0 || !/^\s*(?:#.*)?$/.test(raw.slice(end + 1))) continue;
      value = raw.slice(1, end);
    } else {
      value = raw.replace(/\s+#.*$/, '').trim();
    }
    values.set(key, value);
  }
  return values;
}

/**
 * Minimal `.env` loader for the local launcher. No dependency, no browser copy:
 * values are merged into process.env only when the variable is not already set
 * by the real environment. The loader is safe to call on every coach request,
 * so adding, changing, or removing a key takes effect on the next refresh
 * without a restart. The key itself is never returned or logged.
 */
export function loadLocalEnv(): string[] {
  const envPath = process.env.CHESS_ENV_FILE ? path.resolve(process.env.CHESS_ENV_FILE) : path.resolve(__dirname, '../.env');
  let fileValues: Map<string, string>;
  try {
    fileValues = parseEnvFile(envPath);
  } catch {
    // Never expose filesystem details or keep using a key from a file that
    // can no longer be read. Process-level overrides remain untouched.
    console.warn('[env] Could not read the local environment file; using process environment only.');
    fileValues = new Map();
  }
  const loaded: string[] = [];

  // Reconcile values this loader previously owned.
  for (const [key, previous] of [...managed]) {
    const next = fileValues.get(key);
    if (next === undefined) {
      if (process.env[key] === previous) delete process.env[key];
      managed.delete(key);
    } else if (next !== previous) {
      if (process.env[key] === previous) {
        process.env[key] = next;
        managed.set(key, next);
      } else {
        // A real environment variable took over; stop managing this key.
        managed.delete(key);
      }
    }
  }

  // Apply file values that are not overridden by the real environment.
  for (const [key, value] of fileValues) {
    if (process.env[key] === undefined) {
      process.env[key] = value;
      managed.set(key, value);
      loaded.push(key);
    }
  }

  return loaded;
}
