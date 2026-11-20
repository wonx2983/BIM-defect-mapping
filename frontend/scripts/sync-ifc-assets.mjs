import { copyFile, mkdir } from 'node:fs/promises';
await mkdir('public', { recursive: true });
for (const name of ['web-ifc.wasm', 'web-ifc-mt.wasm']) {
  await copyFile(`node_modules/web-ifc/${name}`, `public/${name}`);
}
