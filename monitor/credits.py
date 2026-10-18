"""WorkBuddy 积分余额：复用客户端登录态直连官方计费接口。

链路与 dsh-workbuddy-connect 一致（已在本机实测打通）：
1. 用 WorkBuddy 自己的 Electron 跑一行 Node，取回 `atRestSecretKey`；
2. sha256 派生保护密钥，AES-256-GCM 解开 `.info` 里的 accessToken；
3. POST /v2/billing/meter/get-user-resource，聚合各套餐包的剩余积分。

只读本地文件，不改登录态；密钥与令牌只存在内存，不写日志、不落盘。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

AUTH_RELATIVE = ["CodeBuddyExtension", "Data", "Public", "auth", "workbuddy-desktop.info"]
BILLING_URL = "https://www.codebuddy.cn/v2/billing/meter/get-user-resource"
HELPER = (
    'process.stdout.write(String(process._linkedBinding('
    '"electron_browser_workbuddy_storage").loggerGet()))'
)
UA = "CLI/2.63.2 CodeBuddy/2.63.2"


# ---------------- 定位客户端 ----------------
def _local_appdata() -> Path | None:
    v = os.environ.get("LOCALAPPDATA")
    return Path(v) if v else None


def find_auth_file() -> Path | None:
    lad = _local_appdata()
    cands = []
    if lad:
        cands.append(lad.joinpath(*AUTH_RELATIVE))
    roaming = os.environ.get("APPDATA")
    if roaming:
        cands.append(Path(roaming).joinpath(*AUTH_RELATIVE))
    for c in cands:
        if c.exists():
            return c
    return None


def find_electron(explicit: str = "") -> Path | None:
    """按 配置 → 环境变量 → 常见安装位 → 卸载注册表 的顺序找 WorkBuddy 主程序。"""
    for raw in (explicit, os.environ.get("WORKBUDDY_ELECTRON_BIN", "")):
        if raw:
            p = Path(raw)
            if p.exists():
                return p

    lad = _local_appdata()
    guesses = []
    if lad:
        guesses += [
            lad / "Programs" / "WorkBuddy" / "WorkBuddy.exe",
            lad / "WorkBuddy" / "WorkBuddy.exe",
        ]
    for p in guesses:
        if p.exists():
            return p

    try:
        import winreg

        roots = [
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]
        for hive, root in roots:
            try:
                key = winreg.OpenKey(hive, root)
            except OSError:
                continue
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    sub = winreg.OpenKey(key, winreg.EnumKey(key, i))
                    name = str(winreg.QueryValueEx(sub, "DisplayName")[0])
                except OSError:
                    continue
                if "workbuddy" not in name.lower():
                    continue
                for field in ("DisplayIcon", "InstallLocation"):
                    try:
                        val = str(winreg.QueryValueEx(sub, field)[0])
                    except OSError:
                        continue
                    raw = val.split(",")[0].strip().strip('"')
                    cand = Path(raw)
                    if cand.is_dir():
                        cand = cand / "WorkBuddy.exe"
                    if cand.exists() and cand.name.lower().endswith(".exe"):
                        return cand
    except Exception:
        pass
    return None


# ---------------- 解密 ----------------
def _aad(key_id: str, suite: int) -> bytes:
    def lp(s: str) -> bytes:
        b = s.encode("utf-8")
        return struct.pack(">I", len(b)) + b

    return (b"WB-AAD\x00" + b"\x01" + lp("WBEV1") + lp("sym-v1")
            + struct.pack(">I", suite) + lp(key_id) + b"\x02\x00\x00")


def _open_field(key: bytes, wrapped: dict) -> str:
    env = json.loads(base64.b64decode(wrapped["envelope"]).decode("utf-8"))
    if env.get("suite") != 1:
        raise ValueError("未知的加密套件")
    nonce = base64.b64decode(env["nonce"])
    tag = base64.b64decode(env["authTag"])
    ct = base64.b64decode(env["ciphertext"])
    return AESGCM(key).decrypt(
        nonce, ct + tag, _aad(env["keyId"], env["suite"])
    ).decode("utf-8")


def read_secret(exe: Path, timeout: float = 25.0) -> str:
    env = dict(os.environ, ELECTRON_RUN_AS_NODE="1")
    proc = subprocess.run(
        [str(exe), "-e", HELPER],
        capture_output=True, env=env, timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"取密钥失败（exit {proc.returncode}）")
    payload = json.loads(proc.stdout.decode("utf-8", "replace") or "{}")
    secret = payload.get("atRestSecretKey")
    if payload.get("version") != 1 or not isinstance(secret, str) or not secret:
        raise RuntimeError("密钥格式不认识")
    return secret


# ---------------- 主类 ----------------
class WorkBuddyCredits:
    def __init__(self, refresh_seconds: int = 300, exe: str = "", store=None):
        self.refresh = max(30, int(refresh_seconds))
        self.exe_override = exe
        self.store = store
        self._secret: str | None = None
        self._exe: Path | None = None
        self._last_at = 0.0
        self._force = False
        self._cache = {
            "ok": False, "remaining": None, "total": None, "used": None,
            "used_today": 0, "packages": 0, "expiring": None, "account": "",
            "at": 0, "error": "尚未刷新",
        }

    # -- 对外 --
    def request_refresh(self) -> None:
        """下次 poll 立即刷新（给“打开面板”用，UI 线程不阻塞）。"""
        self._force = True

    def poll(self, force: bool = False) -> dict:
        force = force or self._force
        self._force = False
        now = time.time()
        if force and now - self._last_at < 20:
            force = False        # 手动刷新做节流，避免连点打爆计费接口
        if not force and now - self._last_at < self.refresh:
            return self._cache
        if not force and self._cache["ok"] and now - self._last_at < 15:
            return self._cache
        self._last_at = now
        try:
            self._cache = self._fetch()
        except Exception as exc:
            self._cache = {
                "ok": False, "remaining": None, "total": None, "used": None,
                "packages": 0, "expiring": None, "account": "", "at": now,
                "error": _short(exc),
            }
        return self._cache

    # -- 内部 --
    def _resolve_exe(self) -> Path:
        if self._exe and self._exe.exists():
            return self._exe
        exe = find_electron(self.exe_override)
        if not exe:
            raise RuntimeError("找不到 WorkBuddy.exe（可在 config 里指定 credits.exe）")
        self._exe = exe
        return exe

    def _credential(self) -> tuple[str, str, int]:
        auth = find_auth_file()
        if not auth:
            raise RuntimeError("找不到 WorkBuddy 登录凭据")
        doc = json.loads(auth.read_text(encoding="utf-8"))
        token_field = doc.get("auth", {}).get("accessToken")
        if not token_field:
            raise RuntimeError("凭据里没有 accessToken")
        if isinstance(token_field, str):
            token = token_field
        else:
            if self._secret is None:
                self._secret = read_secret(self._resolve_exe())
            key = hashlib.sha256(self._secret.encode("utf-8")).digest()
            try:
                token = _open_field(key, token_field)
            except Exception:
                # 密钥换了（客户端升级/重装），重取一次
                self._secret = read_secret(self._resolve_exe())
                key = hashlib.sha256(self._secret.encode("utf-8")).digest()
                token = _open_field(key, token_field)

        uid = str(doc.get("account", {}).get("uid") or "")
        expires_at = int(doc.get("auth", {}).get("expiresAt") or 0)
        return token, uid, expires_at

    def _fetch(self) -> dict:
        token, uid, expires_at = self._credential()
        if expires_at and expires_at < int(time.time() * 1000):
            raise RuntimeError("登录已过期，请在 WorkBuddy 里刷新")

        now = datetime.now()
        now_ms = int(time.time() * 1000)
        accounts: list[dict] = []
        for page in range(1, 6):
            body = {
                "PageNumber": page,
                "PageSize": 100,
                "ProductCode": "p_tcaca",
                "Status": [0, 3],
                # 窗口必须够长：年度/长期套餐落在 37 天窗口外会被漏掉，
                # 实测少算一半（2622 vs 5277）。
                "PackageEndTimeRangeBegin": now.strftime("%Y-%m-%d %H:%M:%S"),
                "PackageEndTimeRangeEnd": (now + timedelta(days=365)).strftime("%Y-%m-%d %H:%M:%S"),
            }
            req = urllib.request.Request(
                BILLING_URL,
                data=json.dumps(body).encode(),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    **({"X-User-Id": uid} if uid else {}),
                    "User-Agent": UA,
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    payload = json.loads(resp.read().decode("utf-8", "replace"))
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403):
                    raise RuntimeError("登录凭据被拒绝，请在 WorkBuddy 里重新登录")
                raise RuntimeError(f"计费接口 HTTP {exc.code}")

            if payload.get("code") not in (0, None):
                raise RuntimeError(str(payload.get("msg") or "计费接口返回错误")[:40])

            batch = (
                payload.get("data", {})
                .get("Response", {})
                .get("Data", {})
                .get("Accounts", [])
                or []
            )
            accounts.extend(batch)
            if len(batch) < 100:
                break

        if not accounts:
            raise RuntimeError("未取到积分套餐（企业账号暂未适配）")

        remaining = 0
        total = 0
        used = 0
        expiring = None
        alive = 0
        for a in accounts:
            end = int(a.get("DeductionEndTime") or 0)
            if end and end <= now_ms:
                continue                     # 已过期，不可用
            size = int(a.get("CycleCapacitySize") or 0)
            remain = int(a.get("CycleCapacityRemain") or 0)
            used_n = int(a.get("CycleCapacityUsed") or 0)
            if size <= 0 and remain <= 0 and used_n <= 0:
                remain = int(a.get("CapacityRemain") or 0)
            remaining += max(0, remain)
            total += max(size, remain + used_n)
            used += max(0, used_n)
            if remain > 0:
                alive += 1
                if end and (expiring is None or end < expiring):
                    expiring = end

        return {
            "ok": True,
            "remaining": remaining,
            "total": total,
            "used": used,
            "used_today": self._account_today(remaining),
            "packages": alive,
            "expiring": (datetime.fromtimestamp(expiring / 1000).strftime("%m-%d")
                         if expiring else None),
            "account": uid[:8] + "…" if uid else "",
            "at": time.time(),
            "error": "",
        }


    def _account_today(self, remaining: int) -> int:
        """用服务端剩余值做日账：只累计下降量，充值不冲抵已用。"""
        day = datetime.now().strftime("%Y-%m-%d")
        if self.store is None:
            return 0
        st = self.store.data.setdefault("credits_daily", {})
        if st.get("day") != day:
            st.update(day=day, last=remaining, used=0)
        else:
            prev = st.get("last")
            if isinstance(prev, int) and remaining < prev:
                st["used"] = int(st.get("used", 0)) + (prev - remaining)
            st["last"] = remaining
        self.store.save()
        return int(st.get("used", 0))


def _short(exc: Exception) -> str:
    msg = str(exc) or exc.__class__.__name__
    if "timed out" in msg or "Timeout" in msg:
        return "取密钥超时"
    return msg[:60]
