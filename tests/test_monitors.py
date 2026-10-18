"""核心逻辑离线自测：增量解压、确认事件解析、会话状态迁移。

运行：python tests/test_monitors.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import zstandard  # noqa: E402

from core.store import Store  # noqa: E402
from monitor import dsh as dsh_mod  # noqa: E402
from monitor import workbuddy as wb_mod  # noqa: E402

FAILS: list[str] = []


def check(cond: bool, name: str, extra: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        FAILS.append(name)


def frame(obj: dict) -> bytes:
    return zstandard.ZstdCompressor().compress(
        (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
    )


def test_dsh_incremental(tmp: Path) -> None:
    print("\n[1] DSH 增量读取 + 确认事件")
    base = tmp / "sessions" / "--D-demo--"
    sdir = base / "abc123"
    sdir.mkdir(parents=True)
    f = sdir / "session.v4.jsonl.zstd"

    head = {"type": "session", "version": 4, "id": "session-abc123", "cwd": "D:/demo"}
    with open(f, "wb") as fh:
        fh.write(frame(head))
        fh.write(frame({"type": "session/title", "data": {"title": "演示任务"}}))

    store = Store(tmp / "ledger.json")
    mon = dsh_mod.DshMonitor(store, 30)
    mon.base = tmp / "sessions"

    r = mon.poll()          # 首次：只登记文件，不产生事件
    check(r["ok"], "poll 返回 ok")
    check(r["events"] == [], "首次不重放历史事件")

    with open(f, "ab") as fh:
        fh.write(frame({"type": "turn/start", "data": {"turn": 1}}))
        fh.write(frame({"type": "approval/asked", "data": {
            "id": "ap-1", "toolName": "命令执行", "reason": "需要越权",
        }}))
    r = mon.poll()
    kinds = [e["kind"] for e in r["events"]]
    check("turn_start" in kinds, "捕获 turn_start", str(kinds))
    check("approval" in kinds, "捕获 approval", str(kinds))
    ap = next((e for e in r["events"] if e["kind"] == "approval"), None)
    check(bool(ap) and ap["tool"] == "命令执行" and ap["approval_id"] == "ap-1",
          "approval 字段完整", str(ap))
    check(len(mon.pending_alerts()) == 1, "待确认队列 +1")

    with open(f, "ab") as fh:
        fh.write(frame({"type": "approval/decided", "data": {"id": "ap-1", "outcome": "accept"}}))
        fh.write(frame({"type": "turn/end", "data": {"reason": {"kind": "completed"}}}))
    r = mon.poll()
    kinds = [e["kind"] for e in r["events"]]
    check("approval_cleared" in kinds, "捕获 approval_cleared", str(kinds))
    check("turn_end" in kinds, "捕获 turn_end", str(kinds))
    check(len(mon.pending_alerts()) == 0, "待确认队列清空")

    r = mon.poll()
    check(r["events"] == [], "无新字节时不重复解析", str(r["events"]))


def test_workbuddy(tmp: Path) -> None:
    print("\n[2] WorkBuddy 状态迁移 + 积分增量")
    db = tmp / "workbuddy.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE sessions(
            id TEXT PRIMARY KEY, title TEXT, custom_title TEXT, cwd TEXT, status TEXT,
            model TEXT, expert_id TEXT, created_at INTEGER, updated_at INTEGER,
            last_activity_at INTEGER, deleted_at INTEGER, is_playground INTEGER DEFAULT 0
        );
        CREATE TABLE session_usage(
            session_id TEXT PRIMARY KEY, used INTEGER, size INTEGER,
            updated_at INTEGER, credit_json TEXT
        );
        """
    )
    now = int(time.time() * 1000)
    conn.execute("INSERT INTO sessions VALUES('s1','演示任务',NULL,'D:/demo','working',"
                 "'m',NULL,?,?,NULL,NULL,0)", (now, now))
    conn.execute("INSERT INTO session_usage VALUES('s1',0,0,?,'{\"r1\":2.5}')", (now,))
    conn.commit()
    conn.close()

    store = Store(tmp / "ledger2.json")
    mon = wb_mod.WorkBuddyMonitor(store, 30)
    mon.DB_PATH = db
    wb_mod.DB_PATH = db

    r = mon.poll()
    check(r["ok"], "首次读取 ok")
    check(r["events"] == [], "首次不上报（建立基线）")
    check(len(r["tasks"]) == 1, "读到 1 个会话")
    check(abs(store.credits_today() - 2.5) < 0.01, "基线积分归到当天",
          f"{store.credits_today()}")

    conn = sqlite3.connect(db)
    conn.execute("UPDATE sessions SET status='completed', updated_at=? WHERE id='s1'",
                 (now + 1000,))
    conn.commit()
    conn.close()

    r = mon.poll()
    kinds = [e["kind"] for e in r["events"]]
    check("session_completed" in kinds, "working→completed 触发完成事件", str(kinds))

    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO sessions VALUES('s2','新任务',NULL,'D:/demo2','working',"
                 "'m',NULL,?,?,NULL,NULL,0)", (now + 2000, now + 2000))
    conn.execute("UPDATE session_usage SET credit_json='{\"r1\":2.5,\"r2\":1.25}' WHERE session_id='s1'")
    conn.commit()
    conn.close()

    r = mon.poll()
    kinds = [e["kind"] for e in r["events"]]
    check("session_started" in kinds, "新会话触发开始事件", str(kinds))
    check(len(r["credits"]) == 1 and abs(r["credits"][0]["amount"] - 1.25) < 0.001,
          "只上报新增积分", str(r["credits"]))
    check(abs(store.credits_today() - 3.75) < 0.01, "今日积分累加",
          f"{store.credits_today()}")


def test_deepseek(tmp: Path) -> None:
    """余额接口解析 + 今日消耗按快照下降量累计（不依赖任何挂件）。"""
    print("\n[deepseek]")
    import io
    import os
    from unittest import mock

    from monitor import deepseek as ds_mod

    store = Store(tmp / "ledger_ds.json")
    mon = ds_mod.DeepSeekMonitor(1, "sk-test-key", store=store,
                                 ledger_path=tmp / "no-ledger.json")

    payload = json.dumps({
        "is_available": True,
        "balance_infos": [{"currency": "CNY", "total_balance": "120.50",
                           "granted_balance": "0.00", "topped_up_balance": "120.50"}],
    }).encode()

    class FakeResp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with mock.patch.object(ds_mod.urllib.request, "urlopen", return_value=FakeResp(payload)):
        r1 = mon.poll(force=True)
    check(r1["ok"] and abs(r1["balance"] - 120.50) < 1e-6, "解析官方余额", str(r1))
    check(r1["currency"] == "CNY", "识别币种")
    check(r1["today"] == 0.0, "首次轮询不产生消耗", str(r1["today"]))

    payload2 = json.dumps({"is_available": True, "balance_infos": [
        {"currency": "CNY", "total_balance": "118.00"}]}).encode()
    with mock.patch.object(ds_mod.urllib.request, "urlopen", return_value=FakeResp(payload2)):
        r2 = mon.poll(force=True)
    check(abs(r2["today"] - 2.50) < 1e-6, "下降量记为今日消耗", str(r2["today"]))

    payload3 = json.dumps({"is_available": True, "balance_infos": [
        {"currency": "CNY", "total_balance": "168.00"}]}).encode()
    with mock.patch.object(ds_mod.urllib.request, "urlopen", return_value=FakeResp(payload3)):
        r3 = mon.poll(force=True)
    check(abs(r3["today"] - 2.50) < 1e-6, "充值不冲抵已用", str(r3["today"]))

    # key 优先级：构造函数 > 环境变量
    os.environ["DEEPSEEK_API_KEY"] = "sk-from-env"
    check(ds_mod.DeepSeekMonitor(1, "", store=store)._resolve_key() == "sk-from-env",
          "环境变量兜底")
    check(ds_mod.DeepSeekMonitor(1, "sk-from-config")._resolve_key() == "sk-from-config",
          "配置优先于环境变量")
    os.environ.pop("DEEPSEEK_API_KEY", None)


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        test_dsh_incremental(tmp)
        test_workbuddy(tmp)
        test_deepseek(tmp)
    print("\n结果：", "全部通过" if not FAILS else f"{len(FAILS)} 项失败 -> {FAILS}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
