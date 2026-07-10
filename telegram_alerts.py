# telegram_alerts.py
# Pure-stdlib Telegram notifier + "no forms" monitor (no external pip installs)

from __future__ import annotations

import json
import os
import platform
import threading
import ssl
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional


_CONFIG_LOCK = threading.Lock()
_CONFIG: Optional[Dict[str, Any]] = None

_LAST_SENT_LOCK = threading.Lock()
_LAST_SENT_AT = 0.0


def _base_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _load_config() -> Dict[str, Any]:
    global _CONFIG
    with _CONFIG_LOCK:
        if _CONFIG is not None:
            return _CONFIG

        cfg_path = os.path.join(_base_dir(), "telegram_config.json")
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                _CONFIG = json.load(f) or {}
        except Exception:
            _CONFIG = {}

        # Defaults
        _CONFIG.setdefault("enabled", False)
        _CONFIG.setdefault("bot_token", "")
        _CONFIG.setdefault("chat_id", "")
        _CONFIG.setdefault("cooldown_seconds", 300)
        _CONFIG.setdefault("timeout_seconds", 8)
        _CONFIG.setdefault("debug_print", False)

        return _CONFIG


def _dbg(msg: str) -> None:
    cfg = _load_config()
    if cfg.get("debug_print"):
        print(f"[TG] {msg}")


def _now_str() -> str:
    # local time string
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def _cooldown_ok() -> bool:
    cfg = _load_config()
    cooldown = int(cfg.get("cooldown_seconds") or 0)
    if cooldown <= 0:
        return True
    with _LAST_SENT_LOCK:
        return (time.time() - _LAST_SENT_AT) >= cooldown


def _mark_sent() -> None:
    global _LAST_SENT_AT
    with _LAST_SENT_LOCK:
        _LAST_SENT_AT = time.time()


def send_telegram_message(text: str, force: bool = False) -> bool:
    """
    Sends a Telegram message using Bot API.
    Returns True on success, False otherwise.
    Never raises (fails silently).
    """
    cfg = _load_config()
    if not cfg.get("enabled"):
        return False

    token = str(cfg.get("bot_token") or "").strip()
    chat_id = str(cfg.get("chat_id") or "").strip()
    if not token or not chat_id:
        _dbg("Config missing bot_token/chat_id.")
        return False

    # Check cooldown UNLESS force is True
    if not force and not _cooldown_ok():
        _dbg("Cooldown active; skipping send.")
        return False

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        timeout = float(cfg.get("timeout_seconds") or 8)
        with urllib.request.urlopen(req, timeout=timeout, context=ssl._create_unverified_context()) as resp:
            ok = (resp.status == 200)
        if ok:
            _mark_sent()
        return ok
    except Exception as e:
        _dbg(f"Send failed: {e}")
        return False


def _build_no_forms_message(context: Dict[str, Any]) -> str:
    host = platform.node() or os.environ.get("COMPUTERNAME") or "PC"
    form_index = context.get("form_index")
    signature = context.get("signature")
    last_signature = context.get("last_signature")
    reason = context.get("reason") or "No new forms detected"

    lines = []
    lines.append("🚨 MPF BOT ALERT: NO FORMS / BOT WILL TERMINATE")
    lines.append(f"🕒 Time: {_now_str()}")
    lines.append(f"💻 PC: {host}")
    lines.append(f"❓ Reason: {reason}")

    if form_index is not None:
        lines.append(f"🔢 form_index: {form_index}")
    if signature is not None:
        lines.append(f"🧾 signature: {signature}")
    if last_signature is not None:
        lines.append(f"🧾 last_signature: {last_signature}")

    # Small hint so you know it's the 7-minute exit
    lines.append("⏳ Bot entered 7-minute wait and is about to stop.")

    return "\n".join(lines)


def _infer_context_from_caller(caller_locals: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pull useful info from autofill_mode locals when safe_sleep(7*60) is called.
    """
    ctx: Dict[str, Any] = {}
    for k in ("form_index", "signature", "last_signature"):
        if k in caller_locals:
            try:
                ctx[k] = caller_locals.get(k)
            except Exception:
                pass

    # Determine likely reason based on locals
    try:
        extracted = caller_locals.get("extracted", None)
        sig = caller_locals.get("signature", None)
        last_sig = caller_locals.get("last_signature", None)

        if extracted == {} or extracted is None:
            # This matches the branch where info panel extraction returns empty,
            # then bot speaks "No more forms..." and safe_sleep(7*60).
            ctx["reason"] = "Info panel extraction empty (no more forms)"
        elif (last_sig is not None) and (sig == last_sig):
            # This matches "Same form data detected again..." then safe_sleep(7*60).
            ctx["reason"] = "Info panel signature unchanged (same form again)"
        else:
            ctx["reason"] = "Entered 7-minute terminate wait"
    except Exception:
        ctx["reason"] = "Entered 7-minute terminate wait"

    return ctx


def install_no_forms_monitor() -> None:
    """
    Zero-edit hook:
    - Watches for calls to safe_sleep(7*60) inside MPF_BOT_V7_3.py
    - Sends Telegram alert right before the 7-minute wait starts.
    """
    cfg = _load_config()
    if not cfg.get("enabled"):
        _dbg("Telegram disabled; monitor not installed.")
        return

    # Prevent double-install
    if getattr(install_no_forms_monitor, "_installed", False):
        return
    install_no_forms_monitor._installed = True  # type: ignore[attr-defined]

    in_notify = {"flag": False}
    alerted = {"flag": False}

    def _profiler(frame, event, arg):
        # Keep overhead low: only care about function CALL events.
        if event != "call":
            return _profiler

        if in_notify["flag"]:
            return _profiler

        code = frame.f_code
        if code.co_name != "safe_sleep":
            return _profiler

        # Only act for the 7-minute wait (>= 419 sec)
        try:
            secs = float(frame.f_locals.get("seconds", 0))
        except Exception:
            secs = 0.0

        if secs < 419:
            return _profiler

        # Ensure it's *your* MPF bot file
        filename = os.path.basename(code.co_filename or "")
        if filename != "MPF_BOT_V7_3.py":
            return _profiler

        # Send only once per run (cooldown also exists)
        if alerted["flag"]:
            return _profiler

        try:
            caller = frame.f_back
            caller_locals = caller.f_locals if caller else {}
            ctx = _infer_context_from_caller(caller_locals)

            msg = _build_no_forms_message(ctx)

            in_notify["flag"] = True
            ok = send_telegram_message(msg)
            _dbg(f"Alert sent={ok} ctx={ctx}")
            alerted["flag"] = True
        except Exception as e:
            _dbg(f"Monitor error: {e}")
        finally:
            in_notify["flag"] = False

        return _profiler

    import sys
    sys.setprofile(_profiler)

    # Also apply to newly created threads (safe)
    try:
        import threading as _threading
        _threading.setprofile(_profiler)
    except Exception:
        pass

    _dbg("No-forms monitor installed.")


# ---------- Optional helpers (run manually) ----------

def get_last_chat_id() -> Optional[str]:
    """
    Reads the latest chat_id from getUpdates (you must have sent at least 1 message to the bot).
    """
    cfg = _load_config()
    token = str(cfg.get("bot_token") or "").strip()
    if not token:
        print("bot_token missing in telegram_config.json")
        return None

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        timeout = float(cfg.get("timeout_seconds") or 8)
        with urllib.request.urlopen(url, timeout=timeout, context=ssl._create_unverified_context()) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        data = json.loads(raw)
        results = data.get("result", [])
        if not results:
            print("No updates found. Send a message to your bot in Telegram first.")
            return None
        last = results[-1]
        chat = (((last.get("message") or {}).get("chat")) or {})
        chat_id = chat.get("id")
        if chat_id is None:
            print("Could not parse chat id from updates.")
            return None
        return str(chat_id)
    except Exception as e:
        print("getUpdates failed:", e)
        return None


if __name__ == "__main__":
    import sys

    args = [a.strip().lower() for a in sys.argv[1:]]

    if "--get-chat-id" in args:
        cid = get_last_chat_id()
        print("chat_id:", cid)
        raise SystemExit(0)

    if "--test" in args:
        ok = send_telegram_message(f"✅ MPF BOT Telegram test message at {_now_str()}")
        print("sent:", ok)
        raise SystemExit(0)

    print("Usage:")
    print("  python telegram_alerts.py --get-chat-id")
    print("  python telegram_alerts.py --test")
