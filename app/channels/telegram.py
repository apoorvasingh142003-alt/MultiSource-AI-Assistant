"""Telegram channel — two-way bot on a shared bot with per-tenant link codes.

Flow:
  1. A signed-in user calls POST /telegram/link → we mint a one-time code and return a
     deep link (https://t.me/<bot>?start=<code>).
  2. They open it in Telegram; the bot receives ``/start <code>``; we bind that chat id to
     the user (channel_links) and confirm.
  3. Any later message from that chat runs the user's ISOLATED engine (get_engine(user_id))
     and the grounded answer is sent back. The conversation is also stored as a normal
     session (id ``tg:<chat_id>``) so it shows up in the web app and supports follow-ups.

Outbound calls use the stdlib (urllib) so the backend gains no dependency. Inbound is
authenticated by the secret Telegram echoes in the X-Telegram-Bot-Api-Secret-Token header.
"""
from __future__ import annotations

import json
import logging
import secrets
import urllib.request
import uuid
from datetime import datetime, timedelta

from app.config import get_settings
from app.db.migrations import get_session_db

log = logging.getLogger("aba.telegram")

CHANNEL = "telegram"
_CODE_TTL_MIN = 15
_TG_MAX = 4000  # Telegram hard limit is 4096; leave headroom


# --------------------------------------------------------------------------- #
# Linking
# --------------------------------------------------------------------------- #
def create_link_code(user_id: str) -> dict:
    """Mint a one-time link code for a signed-in user; return the code + deep link."""
    code = secrets.token_hex(4).upper()  # 8 hex chars, easy to type
    expires = (datetime.utcnow() + timedelta(minutes=_CODE_TTL_MIN)).strftime("%Y-%m-%d %H:%M:%S")
    db = get_session_db()
    try:
        db.execute("DELETE FROM channel_link_codes WHERE user_id = ? AND channel = ?", (user_id, CHANNEL))
        db.execute(
            "INSERT INTO channel_link_codes (code, channel, user_id, expires_at) VALUES (?, ?, ?, ?)",
            (code, CHANNEL, user_id, expires),
        )
        db.commit()
    finally:
        db.close()
    s = get_settings()
    bot = s.telegram_bot_username
    deep_link = f"https://t.me/{bot}?start={code}" if bot else None
    return {"code": code, "deep_link": deep_link, "expires_in_minutes": _CODE_TTL_MIN,
            "bot_username": bot}


def _redeem_code(code: str, chat_id: str) -> str | None:
    """Redeem a code from within Telegram → bind chat_id to the user. Returns user_id or None."""
    db = get_session_db()
    try:
        row = db.execute(
            "SELECT user_id, expires_at FROM channel_link_codes WHERE code = ? AND channel = ?",
            (code.strip().upper(), CHANNEL),
        ).fetchone()
        if not row:
            return None
        if row["expires_at"] < datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"):
            db.execute("DELETE FROM channel_link_codes WHERE code = ?", (code.strip().upper(),))
            db.commit()
            return None
        user_id = row["user_id"]
        db.execute(
            "INSERT INTO channel_links (id, channel, external_id, user_id) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(channel, external_id) DO UPDATE SET user_id = excluded.user_id",
            (str(uuid.uuid4()), CHANNEL, str(chat_id), user_id),
        )
        db.execute("DELETE FROM channel_link_codes WHERE code = ?", (code.strip().upper(),))
        db.commit()
        return user_id
    finally:
        db.close()


def resolve_user(chat_id: str) -> str | None:
    db = get_session_db()
    try:
        row = db.execute(
            "SELECT user_id FROM channel_links WHERE channel = ? AND external_id = ?",
            (CHANNEL, str(chat_id)),
        ).fetchone()
        return row["user_id"] if row else None
    finally:
        db.close()


def link_status(user_id: str) -> dict:
    db = get_session_db()
    try:
        n = db.execute(
            "SELECT COUNT(*) AS n FROM channel_links WHERE channel = ? AND user_id = ?",
            (CHANNEL, user_id),
        ).fetchone()["n"]
    finally:
        db.close()
    return {"linked": n > 0, "chats": n}


def unlink(user_id: str) -> None:
    db = get_session_db()
    try:
        db.execute("DELETE FROM channel_links WHERE channel = ? AND user_id = ?", (CHANNEL, user_id))
        db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Telegram Bot API (outbound)
# --------------------------------------------------------------------------- #
def _api(method: str, payload: dict) -> dict | None:
    s = get_settings()
    if not s.telegram_bot_token:
        log.warning("telegram: no bot token configured; skipping %s", method)
        return None
    url = f"https://api.telegram.org/bot{s.telegram_bot_token}/{method}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:  # noqa: BLE001
        log.warning("telegram %s failed: %s", method, exc)
        return None


def send_message(chat_id: str | int, text: str) -> None:
    for chunk in _chunks(text or "…", _TG_MAX):
        _api("sendMessage", {"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True})


def _chunks(text: str, n: int) -> list[str]:
    return [text[i:i + n] for i in range(0, len(text), n)] or [text]


def set_webhook() -> dict | None:
    """Register our webhook with Telegram (idempotent). Called at startup when configured."""
    s = get_settings()
    if not s.telegram_bot_token:
        return None
    url = f"{s.public_base_url.rstrip('/')}/api/telegram/webhook"
    payload = {"url": url, "allowed_updates": ["message"]}
    if s.telegram_webhook_secret:
        payload["secret_token"] = s.telegram_webhook_secret
    res = _api("setWebhook", payload)
    log.info("telegram setWebhook %s -> %s", url, res)
    return res


# --------------------------------------------------------------------------- #
# Inbound update handling (runs off the webhook thread)
# --------------------------------------------------------------------------- #
_WELCOME = (
    "👋 Welcome to the Multi-Source Knowledge Assistant.\n\n"
    "This chat isn't linked to an account yet. Open the app, go to Settings → Connect "
    "Telegram, and tap the link (or send me /start <code>) to connect. Then just message "
    "me your questions and I'll answer from your documents and data."
)


def handle_update(update: dict) -> None:
    """Process one Telegram update: linking via /start <code>, or answer a question."""
    try:
        msg = update.get("message") or {}
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        text = (msg.get("text") or "").strip()
        if chat_id is None or not text:
            return

        # /start [code]
        if text.startswith("/start"):
            parts = text.split(maxsplit=1)
            code = parts[1].strip() if len(parts) > 1 else ""
            if code:
                user_id = _redeem_code(code, chat_id)
                if user_id:
                    send_message(chat_id, "✅ Linked! This chat is now connected to your "
                                          "account. Ask me anything about your documents and data.")
                else:
                    send_message(chat_id, "⚠️ That link code is invalid or expired. Generate a "
                                          "fresh one in the app (Settings → Connect Telegram).")
                return
            # bare /start
            if resolve_user(chat_id):
                send_message(chat_id, "You're linked. Ask me anything about your data.")
            else:
                send_message(chat_id, _WELCOME)
            return

        # Regular message → must be linked
        user_id = resolve_user(chat_id)
        if not user_id:
            send_message(chat_id, _WELCOME)
            return

        _answer_and_reply(chat_id, user_id, text)
    except Exception:  # never crash the webhook worker
        log.exception("telegram: failed to handle update")


def _answer_and_reply(chat_id: str | int, user_id: str, question: str) -> None:
    from app.engine import get_engine
    session_id = f"tg:{chat_id}"
    _persist(session_id, user_id, "user", question)
    try:
        resp = get_engine(user_id).ask(question, scope="all", session_id=session_id)
        answer = resp.answer or "I couldn't find an answer to that."
        route = resp.trace.route.route if resp.trace and resp.trace.route else None
        conf = resp.trace.route.confidence if resp.trace and resp.trace.route else None
    except Exception:
        log.exception("telegram: engine.ask failed")
        answer, route, conf = "Sorry — something went wrong answering that. Please try again.", None, None
    _persist(session_id, user_id, "assistant", answer, route, conf)
    send_message(chat_id, answer)


def _persist(session_id: str, user_id: str, role: str, content: str,
             route: str | None = None, confidence: float | None = None) -> None:
    """Store the turn as a normal session so Telegram chats appear in the web app too."""
    db = get_session_db()
    try:
        db.execute("INSERT OR IGNORE INTO sessions (id, user_id, title) VALUES (?, ?, ?)",
                   (session_id, user_id, "Telegram chat"))
        db.execute(
            "INSERT INTO messages (id, session_id, role, content, route, confidence) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), session_id, role, content, route, confidence),
        )
        db.commit()
    except Exception:
        log.exception("telegram: persist failed")
    finally:
        db.close()
