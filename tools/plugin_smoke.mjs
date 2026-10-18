/**
 * 冒烟测试：模拟 Cordis 的 ctx.effect，验证 apply 能拉起桌宠、dispose 能收掉。
 * 用法：node tools/plugin_smoke.mjs
 */
import { execSync } from 'node:child_process';
import { apply } from '../plugin/lib/index.js';

const disposers = [];
apply({ effect: (fn) => disposers.push(fn()) });

function count() {
  try {
    const out = execSync(
      'powershell -NoProfile -Command "@(Get-CimInstance Win32_Process -Filter \\"Name=\'pythonw.exe\'\\" | Where-Object { $_.CommandLine -like \'*main.py*\' }).Count"',
      { encoding: 'utf8' }
    );
    return out.trim();
  } catch {
    return '?';
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

console.log('disposers:', disposers.length);
await sleep(6000);
console.log('after apply  pythonw:', count());
for (const d of disposers) d();
await sleep(3500);
console.log('after dispose pythonw:', count());
