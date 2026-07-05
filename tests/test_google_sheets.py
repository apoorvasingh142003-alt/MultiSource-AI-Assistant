"""Google Sheets import: id parsing, value reading (HTTP stubbed), SQLite materialisation,
and end-to-end import into a (stubbed) per-user engine. Hermetic and offline.
"""
from __future__ import annotations

import os
import sqlite3

os.environ.setdefault("ABA_OFFLINE_MODE", "always")

import pytest  # noqa: E402

import app.integrations.google_sheets as gs  # noqa: E402


def test_parse_spreadsheet_id():
    assert gs.parse_spreadsheet_id(
        "https://docs.google.com/spreadsheets/d/1AbC_dEfG-hijkLMNOpqrstuvwxyz012345/edit#gid=0"
    ) == "1AbC_dEfG-hijkLMNOpqrstuvwxyz012345"
    assert gs.parse_spreadsheet_id("1AbC_dEfG-hijkLMNOpqrstuvwxyz012345") == "1AbC_dEfG-hijkLMNOpqrstuvwxyz012345"
    with pytest.raises(gs.SheetsError):
        gs.parse_spreadsheet_id("not a sheet")


def _fake_get(meta, values):
    def _get(url, token):
        return {"values": values} if "/values/" in url else meta
    return _get


def test_read_sheet(monkeypatch):
    meta = {"properties": {"title": "Q3 Budget"}, "sheets": [{"properties": {"title": "Tab1"}}]}
    values = [["Name", "Amount"], ["Alice", "100"], ["Bob", "200"]]
    monkeypatch.setattr(gs, "_get", _fake_get(meta, values))
    title, header, data = gs.read_sheet("tok", "sid")
    assert title == "Q3 Budget"
    assert header == ["Name", "Amount"]
    assert data == [["Alice", "100"], ["Bob", "200"]]


def test_build_sqlite_sanitises_and_inserts(tmp_path):
    path = tmp_path / "s.db"
    table = gs.build_sqlite(path, "Q3 Budget", ["First Name", "First Name", "2024 $"],
                            [["Alice", "A", "100"], ["Bob", "B", "200"]])
    conn = sqlite3.connect(str(path))
    cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
    rows = conn.execute(f'SELECT * FROM "{table}"').fetchall()
    conn.close()
    assert table == "Q3_Budget"
    assert cols[0] == "First_Name" and cols[1].startswith("First_Name_")  # de-duped
    assert cols[2] == "_2024__"  # leading digit prefixed, $ sanitised
    assert len(rows) == 2


def test_build_sqlite_handles_empty_header_and_ragged_rows(tmp_path):
    # No header row + rows of differing width must not crash (regression for the 500).
    path = tmp_path / "r.db"
    table = gs.build_sqlite(path, "Data", [], [["a", "b", "c"], ["d"]])
    conn = sqlite3.connect(str(path))
    cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
    rows = conn.execute(f'SELECT * FROM "{table}"').fetchall()
    conn.close()
    assert cols == ["col1", "col2", "col3"]      # synthesised
    assert rows == [("a", "b", "c"), ("d", "", "")]  # short row padded


def test_read_sheet_skips_leading_blank_rows(monkeypatch):
    meta = {"properties": {"title": "T"}, "sheets": [{"properties": {"title": "S"}}]}
    values = [[], ["", ""], ["Name", "Qty"], ["A", "1"]]
    monkeypatch.setattr(gs, "_get", _fake_get(meta, values))
    _, header, data = gs.read_sheet("t", "s")
    assert header == ["Name", "Qty"]
    assert data == [["A", "1"]]


def test_import_sheet_for_user_registers_table(tmp_path, monkeypatch):
    monkeypatch.setattr(gs, "read_sheet",
                        lambda tok, sid: ("Sales", ["Region", "Total"], [["EU", "5"], ["US", "9"]]))

    added = {}

    class _Info:
        status, error = "indexed", None

    class _Eng:
        uploads_dir = tmp_path

        def add_database(self, name, path):
            added["name"], added["path"] = name, path
            assert path.exists()  # the SQLite file was materialised
            return _Info()

    monkeypatch.setattr("app.engine.get_engine", lambda uid=None: _Eng())

    res = gs.import_sheet_for_user("alice", "tok", "https://docs.google.com/spreadsheets/d/" + "x" * 30)
    assert res["ok"] and res["rows"] == 2 and res["table"] == "Sales"
    assert "Google Sheet" in added["name"]
