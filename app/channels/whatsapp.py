"""WhatsApp channel — two-way via the Meta Cloud API (shared number + link code).

Mirrors the Telegram channel: a signed-in user mints a one-time code and sends it from
WhatsApp to the business number; that binds their WhatsApp id to their account. Later
messages run their ISOLATED engine and the grounded answer is sent back. Because the bot
only ever *replies* to a user-initiated message (inside the 24h window), outbound is
free-form text — no pre-approved templates are required for Q&A.
"""
from __future__ import annotations

import json
import logging
import secrets
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta

from app.config import get_settings
from app.db.migrations import get_session_db

log = logging.getLogger("aba.whatsapp")

CHANNEL = "whatsapp"
_CODE_TTL_MIN = 15
_GRAPH = "https://graph.facebook.com/v21.0"


# --------------------------------------------------------------------------- #
# Linking (channel_links / channel_link_codes, shared schema with Telegram)
# --------------------------------------------------------------------------- #
def create_link_code(user_id: str) -> dict:
    code = secrets.token_hex(4).upper()
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
    num = (s.whatsapp_business_number or "").lstrip("+")
    text = f"LINK {code}"
    deep_link = f"https://wa.me/{num}?text={urllib.parse.quote(text)}" if num else None
    return {"code": code, "deep_link": deep_link, "expires_in_minutes": _CODE_TTL_MIN,
            "business_number": s.whatsapp_business_number}


def _redeem_code(code: str, wa_id: str) -> str | None:
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
            (str(uuid.uuid4()), CHANNEL, str(wa_id), user_id),
        )
        db.execute("DELETE FROM channel_link_codes WHERE code = ?", (code.strip().upper(),))
        db.commit()
        return user_id
    finally:
        db.close()


def resolve_user(wa_id: str) -> str | None:
    db = get_session_db()
    try:
        row = db.execute(
            "SELECT user_id FROM channel_links WHERE channel = ? AND external_id = ?",
            (CHANNEL, str(wa_id)),
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
# Meta Cloud API (outbound)
# --------------------------------------------------------------------------- #
def send_message(wa_id: str, text: str) -> None:
    s = get_settings()
    if not (s.whatsapp_access_token and s.whatsapp_phone_number_id):
        log.warning("whatsapp: not configured; skipping send")
        return
    url = f"{_GRAPH}/{s.whatsapp_phone_number_id}/messages"
    for chunk in _chunks(text or "…", 3800):
        payload = {"messaging_product": "whatsapp", "to": str(wa_id),
                   "type": "text", "text": {"body": chunk}}
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {s.whatsapp_access_token}",
                     "Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=15).read()
        except Exception as exc:  # noqa: BLE001
            log.warning("whatsapp send failed: %s", exc)


def _chunks(text: str, n: int) -> list[str]:
    return [text[i:i + n] for i in range(0, len(text), n)] or [text]


# --------------------------------------------------------------------------- #
# Inbound
# --------------------------------------------------------------------------- #
_WELCOME = (
    "👋 Welcome to the Multi-Source Knowledge Assistant. This chat isn't linked to an "
    "account yet. In the web app open Settings → Connect WhatsApp and send the code shown "
    "(e.g. LINK ABCD1234). Then just message me your questions."
)


def verify_webhook(mode: str | None, token: str | None, challenge: str | None) -> str | None:
    """GET verification handshake Meta performs when you register the webhook."""
    s = get_settings()
    if mode == "subscribe" and token and token == s.whatsapp_verify_token:
        return challenge
    return None


def handle_webhook(payload: dict) -> None:
    """Process an inbound webhook: extract text messages and route them."""
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {}) or {}
                for msg in value.get("messages", []) or []:
                    if msg.get("type") != "text":
                        continue
                    wa_id = msg.get("from")
                    text = ((msg.get("text") or {}).get("body") or "").strip()
                    if wa_id and text:
                        _route(wa_id, text)
    except Exception:
        log.exception("whatsapp: failed to handle webhook")


def _route(wa_id: str, text: str) -> None:
    # Link command: "LINK <code>" or a bare code.
    upper = text.upper()
    if upper.startswith("LINK "):
        code = text.split(None, 1)[1].strip()
        user_id = _redeem_code(code, wa_id)
        send_message(wa_id, "✅ Linked! Ask me anything about your data." if user_id
                     else "⚠️ Invalid or expired code. Generate a fresh one in the app.")
        return

    user_id = resolve_user(wa_id)
    if not user_id:
        # A bare code (no LINK prefix) is a common mistake — try it as a code first.
        if len(text) == 8 and text.isalnum():
            uid = _redeem_code(text, wa_id)
            if uid:
                send_message(wa_id, "✅ Linked! Ask me anything about your data.")
                return
        send_message(wa_id, _WELCOME)
        return

    _answer_and_reply(wa_id, user_id, text)


def _answer_and_reply(wa_id: str, user_id: str, question: str) -> None:
    from app.engine import get_engine
    session_id = f"wa:{wa_id}"
    _persist(session_id, user_id, "user", question)
    try:
        resp = get_engine(user_id).ask(question, scope="all", session_id=session_id)
        answer = resp.answer or "I couldn't find an answer to that."
        route = resp.trace.route.route if resp.trace and resp.trace.route else None
        conf = resp.trace.route.confidence if resp.trace and resp.trace.route else None
    except Exception:
        log.exception("whatsapp: engine.ask failed")
        answer, route, conf = "Sorry — something went wrong. Please try again.", None, None
    _persist(session_id, user_id, "assistant", answer, route, conf)
    send_message(wa_id, answer)


def _persist(session_id: str, user_id: str, role: str, content: str,
             route: str | None = None, confidence: float | None = None) -> None:
    db = get_session_db()
    try:
        db.execute("INSERT OR IGNORE INTO sessions (id, user_id, title) VALUES (?, ?, ?)",
                   (session_id, user_id, "WhatsApp chat"))
        db.execute(
            "INSERT INTO messages (id, session_id, role, content, route, confidence) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), session_id, role, content, route, confidence),
        )
        db.commit()
    except Exception:
        log.exception("whatsapp: persist failed")
    finally:
        db.close()
