"""父进程看门狗：宿主（DSH）退出后让桌宠自己收摊。

插件拉起桌宠时传入 --parent-pid，这里每 2 秒确认一次对方是否还活着。
宿主被强杀、崩溃、直接关窗口都能覆盖到。
"""
from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import QTimer

SYNCHRONIZE = 0x00100000
WAIT_TIMEOUT = 0x00000102


def _alive_windows(pid: int) -> bool:
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        return False
    try:
        # WAIT_TIMEOUT 说明进程还在跑；返回 0 表示已结束
        return kernel32.WaitForSingleObject(handle, 0) == WAIT_TIMEOUT
    finally:
        kernel32.CloseHandle(handle)


def _alive_generic(pid: int) -> bool:
    try:
        import os

        os.kill(pid, 0)
        return True
    except Exception:
        return False


def is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        return _alive_windows(pid)
    return _alive_generic(pid)


def watch(pid: int, on_gone) -> QTimer:
    """宿主不在就调用 on_gone()，返回定时器方便测试。"""
    timer = QTimer()
    timer.setInterval(2000)

    def tick() -> None:
        if not is_alive(pid):
            timer.stop()
            on_gone()

    timer.timeout.connect(tick)
    timer.start()
    return timer
