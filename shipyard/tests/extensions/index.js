// Lets `node --test shipyard/tests/extensions/` work on Node 22: Node resolves the directory to this file, which
// loads every *.test.mjs beside it. `node --test shipyard/tests/extensions/*.test.mjs` runs the same tests directly.
// ES module because package.json sets "type": "module".
import { readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
for (const f of readdirSync(here).filter((n) => n.endsWith('.test.mjs')).sort()) {
  await import(pathToFileURL(join(here, f)).href);
}
