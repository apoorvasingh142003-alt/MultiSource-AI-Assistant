"""HubSpot CRM as a grounded data source (per-tenant, via a Private App token).

A user pastes their HubSpot Private App access token; we validate it, store it per user,
and pull contacts / companies / deals into their ISOLATED engine as SQLite tables (reusing
the same materialisation path as Google Sheets). Questions then route over that CRM data
with grounding + citations, private to each tenant.

Outbound HTTP uses the stdlib. The token is stored server-side in the local state DB; note
for hardening: encrypt this column at rest before any shared/cloud deployment.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

from app.db.migrations import get_session_db
from app.integrations.google_sheets import build_sqlite

log = logging.getLogger("aba.hubspot")

PROVIDER = "hubspot"
_BASE = "https://api.hubapi.com/crm/v3/objects"

# object type → (properties to pull, page cap)
_OBJECTS: dict[str, list[str]] = {
    "contacts": ["firstname", "lastname", "email", "phone", "company", "jobtitle", "lifecyclestage"],
    "companies": ["name", "domain", "industry", "city", "country", "numberofemployees"],
    "deals": ["dealname", "amount", "dealstage", "pipeline", "closedate"],
}
_MAX_RECORDS = 300


class HubSpotError(Exception):
    pass


# --------------------------------------------------------------------------- #
# Token storage
# --------------------------------------------------------------------------- #
def save_token(user_id: str, token: str) -> None:
    db = get_session_db()
    try:
        db.execute(
            "INSERT INTO integration_tokens (user_id, provider, token) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, provider) DO UPDATE SET token = excluded.token, "
            "created_at = datetime('now')",
            (user_id, PROVIDER, token),
        )
        db.commit()
    finally:
        db.close()


def get_token(user_id: str) -> str | None:
    db = get_session_db()
    try:
        row = db.execute(
            "SELECT token FROM integration_tokens WHERE user_id = ? AND provider = ?",
            (user_id, PROVIDER),
        ).fetchone()
        return row["token"] if row else None
    finally:
        db.close()


def delete_token(user_id: str) -> None:
    db = get_session_db()
    try:
        db.execute("DELETE FROM integration_tokens WHERE user_id = ? AND provider = ?",
                   (user_id, PROVIDER))
        db.commit()
    finally:
        db.close()


def status(user_id: str) -> dict:
    return {"connected": get_token(user_id) is not None}


# --------------------------------------------------------------------------- #
# HubSpot API
# --------------------------------------------------------------------------- #
def _get(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:  # type: ignore[attr-defined]
        if exc.code in (401, 403):
            raise HubSpotError(
                "HubSpot rejected the token. Make sure it's a Private App access token "
                "(pat-…) with the CRM read scopes, not a Personal Access Key."
            )
        raise HubSpotError(f"HubSpot API error ({exc.code}).")
    except Exception as exc:  # noqa: BLE001
        raise HubSpotError(f"Could not reach HubSpot: {exc}")


def fetch_objects(token: str, object_type: str, properties: list[str],
                  max_records: int = _MAX_RECORDS) -> list[dict]:
    """Return a flat list of {id, <props…>} dicts for an object type (paginated)."""
    out: list[dict] = []
    after: str | None = None
    while len(out) < max_records:
        params = {"limit": "100", "properties": ",".join(properties)}
        if after:
            params["after"] = after
        data = _get(f"{_BASE}/{object_type}?{urllib.parse.urlencode(params)}", token)
        for r in data.get("results", []):
            props = r.get("properties", {}) or {}
            out.append({"id": r.get("id", ""), **{p: props.get(p, "") for p in properties}})
        after = (((data.get("paging") or {}).get("next") or {}).get("after"))
        if not after:
            break
    return out[:max_records]


def validate_token(token: str) -> None:
    """Cheap call to confirm the token works before we store it."""
    _get(f"{_BASE}/contacts?limit=1", token)


# --------------------------------------------------------------------------- #
# Import into the tenant's engine
# --------------------------------------------------------------------------- #
def import_for_user(user_id: str, token: str) -> dict:
    """Pull CRM objects and register them as tables in the user's isolated engine."""
    from app.engine import get_engine

    eng = get_engine(user_id)
    eng.uploads_dir.mkdir(parents=True, exist_ok=True)
    db_path = eng.uploads_dir / "hubspot.db"
    if db_path.exists():
        db_path.unlink()

    summary: dict[str, int] = {}
    for obj, props in _OBJECTS.items():
        rows = fetch_objects(token, obj, props)
        if not rows:
            summary[obj] = 0
            continue
        header = ["id"] + props
        data = [[str(r.get(c, "")) for c in header] for r in rows]
        build_sqlite(db_path, f"hubspot_{obj}", header, data)
        summary[obj] = len(rows)

    if not any(summary.values()):
        raise HubSpotError("Connected, but no CRM records were found to import.")

    info = eng.add_database("HubSpot CRM", db_path)
    return {"ok": info.status == "indexed", "imported": summary, "status": info.status}


def connect_and_import(user_id: str, token: str) -> dict:
    validate_token(token)
    save_token(user_id, token)
    return import_for_user(user_id, token)


def resync(user_id: str) -> dict:
    token = get_token(user_id)
    if not token:
        raise HubSpotError("HubSpot isn't connected.")
    return import_for_user(user_id, token)
