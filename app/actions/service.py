"""Per-tenant action configuration, n8n dispatch, and the audit log.

Dispatch contract (what the client's n8n Webhook node receives):

    POST <webhook_url>
    Content-Type: application/json
    X-ABA-Action: <action name>
    X-ABA-Signature: sha256=<hex hmac of the body with the per-action secret>   (if set)

    {"action": "...", "params": {...}, "user_id": "...", "session_id": "...",
     "requested_at": "<UTC ISO8601>"}

No webhook configured → the execution is recorded as ``simulated`` (the whole flow —
propose → confirm → audit log — works offline and in demos with zero external setup).
Dispatch never raises: any network/HTTP failure becomes a logged ``error`` result.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

from app.actions.catalog import ACTIONS, get_action
from app.crypto import decrypt, encrypt
from app.db.migrations import get_session_db
from app.models import ActionResult, ProposedAction

log = logging.getLogger("aba.actions")

_TIMEOUT_S = 10
_DETAIL_MAX = 500


# --------------------------------------------------------------------------- #
# Per-tenant config
# --------------------------------------------------------------------------- #
def set_config(user_id: str, action: str, webhook_url: str | None = None,
               secret: str | None = None, enabled: bool | None = None) -> dict:
    """Upsert one action's config. ``None`` leaves the existing value untouched."""
    if not get_action(action):
        raise ValueError(f"Unknown action '{action}'.")
    db = get_session_db()
    try:
        row = db.execute(
            "SELECT webhook_url, secret, enabled FROM action_configs "
            "WHERE user_id = ? AND action = ?", (user_id, action),
        ).fetchone()
        cur_url = decrypt(row["webhook_url"]) if row else ""
        cur_secret = decrypt(row["secret"]) if row else ""
        cur_enabled = bool(row["enabled"]) if row else True
        new_url = cur_url if webhook_url is None else webhook_url.strip()
        new_secret = cur_secret if secret is None else secret.strip()
        new_enabled = cur_enabled if enabled is None else bool(enabled)
        db.execute(
            "INSERT INTO action_configs (user_id, action, webhook_url, secret, enabled) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id, action) DO UPDATE SET webhook_url = excluded.webhook_url, "
            "secret = excluded.secret, enabled = excluded.enabled, "
            "updated_at = datetime('now')",
            (user_id, action, encrypt(new_url), encrypt(new_secret), int(new_enabled)),
        )
        db.commit()
    finally:
        db.close()
    return {"action": action, "configured": bool(new_url), "enabled": new_enabled}


def get_config(user_id: str, action: str) -> dict:
    """One action's effective config (decrypted webhook/secret stay server-side)."""
    db = get_session_db()
    try:
        row = db.execute(
            "SELECT webhook_url, secret, enabled FROM action_configs "
            "WHERE user_id = ? AND action = ?", (user_id, action),
        ).fetchone()
    finally:
        db.close()
    if not row:
        # Unconfigured actions are enabled by default (dispatch = simulated), so the demo
        # flow works with zero setup and a real n8n URL is a paste away.
        return {"webhook_url": "", "secret": "", "enabled": True}
    return {
        "webhook_url": decrypt(row["webhook_url"]) or "",
        "secret": decrypt(row["secret"]) or "",
        "enabled": bool(row["enabled"]),
    }


def list_configs(user_id: str) -> list[dict]:
    """Catalog + per-tenant status for the UI (never exposes the stored secrets)."""
    out = []
    for spec in ACTIONS.values():
        cfg = get_config(user_id, spec.name)
        out.append({
            "action": spec.name, "title": spec.title, "description": spec.description,
            "params": spec.params, "required": spec.required,
            "configured": bool(cfg["webhook_url"]), "has_secret": bool(cfg["secret"]),
            "enabled": cfg["enabled"],
        })
    return out


# --------------------------------------------------------------------------- #
# Proposals
# --------------------------------------------------------------------------- #
def build_proposal(user_id: str, action: str, params: dict[str, str],
                   origin: str = "command") -> ProposedAction:
    """Assemble a ProposedAction for a chat turn: catalog contract + extracted params +
    this tenant's config state. Pure read — nothing is dispatched."""
    spec = get_action(action)
    assert spec is not None, f"unknown action {action!r}"
    cfg = get_config(user_id, action)
    clean = {k: str(v).strip() for k, v in (params or {}).items() if str(v).strip()}
    return ProposedAction(
        id=str(uuid.uuid4()), action=spec.name, title=spec.title,
        description=spec.description,
        params={p: clean.get(p, "") for p in spec.params},
        required=list(spec.required),
        missing=[p for p in spec.required if not clean.get(p)],
        origin=origin,  # type: ignore[arg-type]
        configured=bool(cfg["webhook_url"]), enabled=cfg["enabled"],
    )


# --------------------------------------------------------------------------- #
# Execution (confirm → dispatch → audit log)
# --------------------------------------------------------------------------- #
def execute(user_id: str, action: str, params: dict[str, str],
            session_id: str | None = None) -> ActionResult:
    spec = get_action(action)
    if not spec:
        return _logged(user_id, session_id, action, params, "error",
                       f"Unknown action '{action}'.")
    clean = {k: str(v).strip() for k, v in (params or {}).items()
             if k in spec.params and str(v).strip()}
    missing = [p for p in spec.required if not clean.get(p)]
    if missing:
        return _logged(user_id, session_id, action, clean, "error",
                       f"Missing required field(s): {', '.join(missing)}.")
    cfg = get_config(user_id, action)
    if not cfg["enabled"]:
        return _logged(user_id, session_id, action, clean, "error",
                       f"The '{spec.title}' action is disabled for this workspace.")
    if not cfg["webhook_url"]:
        return _logged(
            user_id, session_id, action, clean, "simulated",
            "No n8n webhook configured for this action — recorded locally only. "
            "Add your webhook URL under Sources → Actions & automations to go live.",
        )

    body = json.dumps({
        "action": action, "params": clean, "user_id": user_id,
        "session_id": session_id,
        "requested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }).encode("utf-8")
    headers = {"Content-Type": "application/json", "X-ABA-Action": action}
    if cfg["secret"]:
        sig = hmac.new(cfg["secret"].encode("utf-8"), body, hashlib.sha256).hexdigest()
        headers["X-ABA-Signature"] = f"sha256={sig}"
    req = urllib.request.Request(cfg["webhook_url"], data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            reply = resp.read(_DETAIL_MAX).decode("utf-8", errors="replace").strip()
            detail = f"n8n accepted the action (HTTP {resp.status})."
            if reply:
                detail += f" Response: {reply}"
            return _logged(user_id, session_id, action, clean, "executed", detail)
    except urllib.error.HTTPError as exc:
        return _logged(user_id, session_id, action, clean, "error",
                       f"The n8n webhook rejected the action (HTTP {exc.code}).")
    except Exception as exc:  # noqa: BLE001 — dispatch must never take down the API
        log.warning("action dispatch failed for %s/%s: %s", user_id, action, exc)
        return _logged(user_id, session_id, action, clean, "error",
                       f"Could not reach the n8n webhook: {exc}")


def _logged(user_id: str, session_id: str | None, action: str, params: dict,
            status: str, detail: str) -> ActionResult:
    rid = str(uuid.uuid4())
    db = get_session_db()
    try:
        db.execute(
            "INSERT INTO action_log (id, user_id, session_id, action, params, status, detail) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (rid, user_id, session_id, action, json.dumps(params), status, detail[:2000]),
        )
        db.commit()
        row = db.execute("SELECT created_at FROM action_log WHERE id = ?", (rid,)).fetchone()
        created = row["created_at"] if row else ""
    finally:
        db.close()
    return ActionResult(id=rid, action=action, status=status, detail=detail,
                        params=params, created_at=created)


def list_log(user_id: str, limit: int = 50) -> list[dict]:
    db = get_session_db()
    try:
        rows = db.execute(
            "SELECT id, session_id, action, params, status, detail, created_at "
            "FROM action_log WHERE user_id = ? ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["params"] = json.loads(d.get("params") or "{}")
            except Exception:
                d["params"] = {}
            out.append(d)
        return out
    finally:
        db.close()
