import {readFile, writeFile} from 'node:fs/promises';

// The protected proxy occasionally returns upstream feed tarball URLs. Keep the
// same package, version and integrity; correct only that registry's path prefix.
const file = new URL('../package-lock.json', import.meta.url);
const lock = JSON.parse(await readFile(file, 'utf8'));
const upstream = 'https://ms-feed-25.pkgs.visualstudio.com/1es-public/_packaging/npm-public/npm/registry/';
const proxy = 'https://packagefeedproxy.microsoft.io/npm/';
let count = 0;
for (const entry of Object.values(lock.packages)) {
  if (entry.resolved?.startsWith(upstream)) {
    entry.resolved = proxy + entry.resolved.slice(upstream.length);
    count++;
  }
}
await writeFile(file, JSON.stringify(lock, null, 2) + '\n');
console.log(`Normalized ${count} upstream tarball URLs to the configured protected proxy.`);
