"""Streamable HTTP MCP. Read-only tools for one user, identified by a Bearer token."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Debt, PortfolioSnapshot, User
from app.portfolio import build_portfolio, load_prices

router = APIRouter()

PROTOCOL_VERSION = "2025-06-18"
_MAX_SNAPSHOTS = 100


def hash_mcp_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _money(value: Decimal | int | str | None) -> str:
    return format(Decimal(value or 0).quantize(Decimal("1")), "f")


def _qty(value: Decimal | int | str | None) -> str:
    text = format(Decimal(value or 0), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _user_from_bearer(db: Session, request: Request) -> User | None:
    header = request.headers.get("authorization", "")
    scheme, _, raw = header.partition(" ")
    if scheme.lower() != "bearer" or not raw.strip():
        return None
    digest = hash_mcp_token(raw.strip())
    return db.query(User).filter(User.mcp_token_hash == digest).one_or_none()


def _tool_result(payload: Any, *, error: bool = False) -> dict:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "isError": error,
    }


def _portfolio(db: Session, user: User) -> dict:
    view = build_portfolio(user, load_prices(db))
    return {
        "username": user.username,
        "total_toman": _money(view.total_toman),
        "prices_fetched_at": _iso(view.prices_fetched_at),
        "missing_prices": view.missing_prices,
        "assets": [
            {
                "key": row.key,
                "name_fa": row.name_fa,
                "name_en": row.name_en,
                "quantity": _qty(row.quantity),
                "unit_fa": row.unit_fa,
                "unit_en": row.unit_en,
                "unit_price_toman": None if row.unit_price is None else _qty(row.unit_price),
                "value_toman": _money(row.value_toman),
            }
            for row in view.rows
        ],
    }


def _salary(user: User) -> dict:
    return {"username": user.username, "salary_toman": _money(user.salary_toman)}


def _debts(db: Session, user: User) -> dict:
    from app.main import next_jalali_due

    rows = []
    total = Decimal("0")
    for debt in db.query(Debt).filter(Debt.user_id == user.id).order_by(Debt.id.asc()).all():
        amount = Decimal(debt.monthly_toman) * Decimal(debt.months_left)
        total += amount
        nxt = next_jalali_due(debt.due_day)
        rows.append(
            {
                "id": debt.id,
                "title": (debt.title or "").strip(),
                "monthly_toman": _money(debt.monthly_toman),
                "months_left": debt.months_left,
                "total_toman": _money(amount),
                "due_jalali": f"{debt.due_year}/{debt.due_month:02d}/{debt.due_day:02d}",
                "next_due_jalali": f"{nxt.year}/{nxt.month:02d}/{nxt.day:02d}" if nxt else None,
            }
        )
    return {"username": user.username, "total_toman": _money(total), "debts": rows}


def _snapshot_row(snap: PortfolioSnapshot, *, include_breakdown: bool) -> dict:
    row = {
        "id": snap.id,
        "taken_at": _iso(snap.taken_at),
        "total_toman": _money(snap.total_toman),
    }
    if include_breakdown:
        try:
            row["breakdown"] = json.loads(snap.breakdown_json or "{}")
        except json.JSONDecodeError:
            row["breakdown"] = {}
    return row


def _list_snapshots(db: Session, user: User, arguments: dict) -> dict:
    raw_limit = arguments.get("limit", 20)
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return _tool_result({"error": "limit must be an integer"}, error=True)
    if limit < 1 or limit > _MAX_SNAPSHOTS:
        return _tool_result({"error": f"limit must be 1..{_MAX_SNAPSHOTS}"}, error=True)
    snaps = (
        db.query(PortfolioSnapshot)
        .filter(PortfolioSnapshot.user_id == user.id)
        .order_by(PortfolioSnapshot.taken_at.desc(), PortfolioSnapshot.id.desc())
        .limit(limit)
        .all()
    )
    return _tool_result(
        {
            "username": user.username,
            "snapshots": [_snapshot_row(snap, include_breakdown=False) for snap in snaps],
        }
    )


def _get_snapshot(db: Session, user: User, arguments: dict) -> dict:
    raw_id = arguments.get("id")
    try:
        snap_id = int(raw_id)
    except (TypeError, ValueError):
        return _tool_result({"error": "id is required"}, error=True)
    snap = db.get(PortfolioSnapshot, snap_id)
    if snap is None or snap.user_id != user.id:
        return _tool_result({"error": "snapshot not found"}, error=True)
    return _tool_result(_snapshot_row(snap, include_breakdown=True))


_TOOLS = [
    {
        "name": "get_portfolio",
        "description": "Current holdings and toman value for the token's user. Read only.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_salary",
        "description": "Monthly salary in toman for the token's user. Read only.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "list_debts",
        "description": "Debts for the token's user: monthly installment, months left, and totals. Read only.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "list_snapshots",
        "description": "Recent portfolio snapshots for the token's user, newest first. Read only.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": _MAX_SNAPSHOTS,
                    "description": "How many snapshots to return. Default 20.",
                }
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_snapshot",
        "description": "One portfolio snapshot, including the per-asset breakdown. Read only.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_chande_currencies",
        "description": (
            "Live currency prices from chande.net (category currency only). "
            "price_toman is the API priceToman value and is not divided. Read only."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]


def _call_tool(db: Session, user: User, name: str, arguments: dict) -> dict:
    if name == "get_portfolio":
        return _tool_result(_portfolio(db, user))
    if name == "get_salary":
        return _tool_result(_salary(user))
    if name == "list_debts":
        return _tool_result(_debts(db, user))
    if name == "list_snapshots":
        return _list_snapshots(db, user, arguments)
    if name == "get_snapshot":
        return _get_snapshot(db, user, arguments)
    return _tool_result({"error": f"unknown tool: {name}"}, error=True)


async def _chande_currencies() -> dict:
    from app.chande import fetch_chande_currencies

    try:
        return _tool_result(await fetch_chande_currencies())
    except Exception as exc:
        return _tool_result({"error": f"chande request failed: {exc}"}, error=True)


async def _rpc(body: dict, db: Session, user: User) -> Response:
    method = body.get("method")
    req_id = body.get("id")
    if not isinstance(method, str) or "id" not in body and not method.startswith("notifications/"):
        return _error(req_id, -32600, "Invalid Request")

    if method.startswith("notifications/"):
        return Response(status_code=202)

    if method == "ping":
        return _ok(req_id, {})
    if method == "initialize":
        return _ok(
            req_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "my-inventory", "version": "1.0.0"},
            },
        )
    if method == "tools/list":
        return _ok(req_id, {"tools": _TOOLS})
    if method == "tools/call":
        params = body.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return _error(req_id, -32602, "Invalid params")
        if name == "get_chande_currencies":
            return _ok(req_id, await _chande_currencies())
        return _ok(req_id, _call_tool(db, user, name, arguments))
    return _error(req_id, -32601, "Method not found")


def _ok(req_id: Any, result: dict) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": result})


def _error(req_id: Any, code: int, message: str) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


def _unauthorized() -> JSONResponse:
    return JSONResponse(
        {"error": "invalid or missing bearer token"},
        status_code=401,
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/mcp")
async def mcp_post(request: Request):
    accept = request.headers.get("accept", "*/*")
    if "application/json" not in accept and "text/event-stream" not in accept and "*/*" not in accept:
        return JSONResponse({"error": "Accept must include application/json"}, status_code=406)
    db = SessionLocal()
    try:
        user = _user_from_bearer(db, request)
        if user is None:
            return _unauthorized()
        try:
            body = await request.json()
        except Exception:
            return _error(None, -32700, "Parse error")
        if not isinstance(body, dict):
            return _error(None, -32600, "Invalid Request")
        return await _rpc(body, db, user)
    finally:
        db.close()


@router.get("/mcp")
async def mcp_get():
    return JSONResponse({"error": "method not allowed"}, status_code=405)
