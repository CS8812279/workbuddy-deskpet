"""验证 parent-pid 看门狗：宿主被强杀后桌宠会自己退出。"""
import subprocess
import sys
import time
from pathlib import Path

import ctypes

ROOT = Path(__file__).resolve().parent.parent
PYW = Path(sys.executable).with_name("pythonw.exe")
NODE = Path(r"C:\Users\43771\.workbuddy\binaries\node\versions\22.22.2-6\node.exe")


def count() -> int:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "@(Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | "
         "Where-Object { $_.CommandLine -like '*main.py*' }).Count"],
        capture_output=True, text=True)
    try:
        return int(out.stdout.strip())
    except ValueError:
        return -1


def main() -> int:
    parent = subprocess.Popen([str(NODE), "-e", "setTimeout(()=>{},60000)"])
    time.sleep(0.5)
    print("host pid", parent.pid)

    child = subprocess.Popen([str(PYW), str(ROOT / "main.py"), "--parent-pid", str(parent.pid)],
                             cwd=str(ROOT))
    time.sleep(5)
    print("桌宠进程数（宿主存活）:", count())

    parent.kill()
    parent.wait()
    print("宿主已强杀，等待看门狗…")
    time.sleep(6)
    print("桌宠进程数（宿主已死）:", count())
    try:
        child.wait(timeout=5)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
