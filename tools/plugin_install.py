"""把桌宠装成 DSH 插件（或卸掉）。

    python tools/plugin_install.py            # 安装（默认）
    python tools/plugin_install.py --off      # 卸载
    python tools/plugin_install.py --status   # 查看状态

安装做的事：
1. 把 plugin/ 复制到 <profile>/node_modules/dsh-deskpet
2. 写入 deskpet.json（项目路径 + pythonw 路径）
3. 在 <profile>/cordis.patch.yml 追加一段带标记的 insert，指向该插件
4. 备份补丁文件 + 校验 YAML + 校验 JS 能被 node 载入

卸载 = 删掉这段 insert 和 node_modules 里的包，补丁文件保持原样（只去标记段）。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "plugin"
PROFILE = Path(os.path.expanduser("~")) / ".dsh" / "profiles" / "desktop"
PATCH = PROFILE / "cordis.patch.yml"
TARGET = PROFILE / "node_modules" / "dsh-deskpet"
NAME = "dsh-deskpet"

BEGIN = "# >>> dsh-deskpet（由 tools/plugin_install.py 管理，勿手改）"
END = "# <<< dsh-deskpet"
BLOCK = (
    f"{BEGIN}\n"
    "- insert:\n"
    f"    - id: {NAME}\n"
    f"      name: {NAME}\n"
    f"{END}\n"
)


def find_pythonw() -> Path | None:
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    if pyw.exists():
        return pyw
    if exe.exists():
        return exe
    return None


def strip_block(text: str) -> str:
    if BEGIN not in text:
        return text
    out, skip = [], False
    for line in text.splitlines(keepends=True):
        if line.strip() == BEGIN:
            skip = True
            continue
        if line.strip() == END:
            skip = False
            continue
        if not skip:
            out.append(line)
    return "".join(out)


def validate_yaml(path: Path) -> bool:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"  ✗ YAML 解析失败：{exc}")
        return False
    if not isinstance(data, list):
        print("  ✗ 补丁层不是数组")
        return False
    return True


def validate_js() -> bool:
    node = shutil.which("node")
    if not node:
        print("  · 跳过 JS 校验（PATH 里没有 node）")
        return True
    uri = (TARGET / "lib" / "index.js").as_uri()
    code = (
        f"import('{uri}').then(m=>{{"
        f"if(!m.default||typeof m.default!=='function')throw new Error('no apply');"
        f"console.log('apply-ok')}}).catch(e=>{{console.error(e.message);process.exit(1)}})"
    )
    proc = subprocess.run([node, "--input-type=module", "-e", code],
                          capture_output=True, text=True, timeout=30)
    if proc.returncode != 0 or "apply-ok" not in proc.stdout:
        print(f"  ✗ JS 载入失败：{proc.stderr.strip()[:200]}")
        return False
    print("  ✓ JS 可被 node 载入，apply 导出正常")
    return True


def register_dependency(pyw: str) -> bool:
    """把插件登记为 profile 的 link 依赖，否则包管理器会把它挪进 .ignored。"""
    pkg = PROFILE / "package.json"
    if not pkg.exists():
        return False
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except Exception:
        return False
    deps = data.setdefault("dependencies", {})
    want = "link:" + str(PACKAGE).replace("\\", "/")
    if deps.get(NAME) == want:
        return False
    shutil.copyfile(pkg, pkg.with_name(f"package.json.bak-deskpet-{time.strftime('%Y%m%d-%H%M%S')}"))
    deps[NAME] = want
    pkg.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (PACKAGE / "deskpet.json").write_text(
        json.dumps({"dir": str(ROOT), "python": pyw,
                    "installedAt": time.strftime("%Y-%m-%d %H:%M:%S")},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return True


def install() -> int:
    if not PROFILE.exists():
        print(f"找不到 profile：{PROFILE}")
        return 1
    if not PATCH.exists():
        print(f"找不到补丁文件：{PATCH}")
        return 1

    pyw = find_pythonw()
    if not pyw:
        print("找不到 pythonw.exe")
        return 1

    print(f"[1/4] 复制插件 → {TARGET}")
    if TARGET.exists():
        shutil.rmtree(TARGET)
    shutil.copytree(PACKAGE, TARGET)

    print("[2/4] 写入 deskpet.json")
    (TARGET / "deskpet.json").write_text(
        json.dumps({"dir": str(ROOT), "python": str(pyw),
                    "installedAt": time.strftime("%Y-%m-%d %H:%M:%S")},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("[2.5/4] 登记为 profile 依赖（防止被包管理器挪走）")
    if register_dependency(str(pyw)):
        print(f"  ✓ package.json 增加 {NAME}: link:{PACKAGE}")
    else:
        print("  · 已登记，跳过")

    print("[3/4] 更新 profile 补丁层")
    text = PATCH.read_text(encoding="utf-8")
    backup = PATCH.with_name(f"cordis.patch.yml.bak-deskpet-{time.strftime('%Y%m%d-%H%M%S')}")
    if not backup.exists():
        shutil.copyfile(PATCH, backup)
        print(f"  · 已备份 {backup.name}")
    cleaned = strip_block(text).rstrip("\n")
    PATCH.write_text(cleaned + "\n" + BLOCK, encoding="utf-8")
    if not validate_yaml(PATCH):
        shutil.copyfile(backup, PATCH)
        print("  ✗ 校验失败，已回滚补丁文件")
        return 1
    print("  ✓ YAML 合法")

    print("[4/4] 校验插件")
    if not validate_js():
        return 1

    print("\n完成。重启 DSH 生效：桌宠会随宿主启动，DSH 关闭时自动退出。")
    return 0


def uninstall() -> int:
    if PATCH.exists():
        backup = PATCH.with_name(f"cordis.patch.yml.bak-uninstall-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copyfile(PATCH, backup)
        PATCH.write_text(strip_block(PATCH.read_text(encoding="utf-8")).rstrip("\n") + "\n",
                         encoding="utf-8")
        validate_yaml(PATCH)
        print(f"已从补丁层移除 {NAME}（备份 {backup.name}）")
    if TARGET.exists():
        shutil.rmtree(TARGET)
        print(f"已删除 {TARGET}")
    print("重启 DSH 后不再随宿主启动。")
    return 0


def status() -> int:
    print(f"profile  : {PROFILE}")
    print(f"插件目录 : {'存在' if TARGET.exists() else '不存在'}  ({TARGET})")
    if (TARGET / "deskpet.json").exists():
        print("配置     :", (TARGET / "deskpet.json").read_text(encoding="utf-8").replace("\n", " "))
    if PATCH.exists():
        text = PATCH.read_text(encoding="utf-8")
        print(f"补丁登记 : {'已登记' if BEGIN in text else '未登记'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--off", action="store_true", help="卸载")
    ap.add_argument("--status", action="store_true", help="查看状态")
    args = ap.parse_args()
    if args.status:
        return status()
    if args.off:
        return uninstall()
    return install()


if __name__ == "__main__":
    sys.exit(main())
