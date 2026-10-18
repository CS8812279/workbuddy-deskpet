/**
 * dsh-deskpet — host half.
 *
 * 随 DSH 启动拉起桌宠（Python 进程），随 DSH 退出把它收掉。
 * 只做进程托管，桌宠本身的逻辑全在 Python 里。
 */
import { spawn } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export const name = 'dsh-deskpet';

const pkgRoot = dirname(dirname(fileURLToPath(import.meta.url)));

/** 安装时写入的 deskpet.json：{ dir, python } */
function readSettings() {
  try {
    const raw = readFileSync(join(pkgRoot, 'deskpet.json'), 'utf8');
    const cfg = JSON.parse(raw);
    if (typeof cfg.dir === 'string' && typeof cfg.python === 'string') return cfg;
  } catch {
    /* 未配置：静默跳过，不影响宿主启动 */
  }
  return null;
}

export function apply(ctx) {
  const cfg = readSettings();
  if (!cfg) return;

  const script = join(cfg.dir, 'main.py');
  if (!existsSync(script) || !existsSync(cfg.python)) return;

  ctx.effect(() => {
    let child;
    try {
      child = spawn(cfg.python, [script, '--parent-pid', String(process.pid)], {
        cwd: cfg.dir,
        stdio: 'ignore',
        windowsHide: true,
        detached: false,
      });
    } catch {
      return () => {};
    }
    child.on('error', () => {});

    return () => {
      // DSH 关闭 / 插件卸载时收掉桌宠；parent-pid 看门狗兜底强杀场景
      try {
        child.kill();
      } catch {
        /* 已经退了 */
      }
    };
  });
}

export default apply;
