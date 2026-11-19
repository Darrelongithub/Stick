import fs from 'node:fs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';

/** Replace a file only after its complete contents have been written nearby. */
export function writeFileAtomic(filePath: string, contents: string): void {
  const temporary = path.join(path.dirname(filePath), `.${path.basename(filePath)}.${randomUUID()}.tmp`);
  try {
    fs.writeFileSync(temporary, contents, { encoding: 'utf8', flag: 'wx', mode: 0o600 });
    fs.renameSync(temporary, filePath);
  } finally {
    fs.rmSync(temporary, { force: true });
  }
}
