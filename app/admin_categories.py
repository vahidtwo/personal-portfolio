"""Admin page for the global spend categories (/admin/categories) and its JSON API (/admin/api/categories).

Admins only. Shows the group tree with spend COUNTS over all users (never amounts or usernames). Every write
keeps each spend's category_id: rows are only renamed, re-ordered, moved to another group, archived or restored;
a hard delete is allowed only for a row no spend and no subcategory uses, and never for a system (SMS) row.
"""

from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.category_style import ICON_CHOICES, ICON_SET, PALETTE, PALETTE_SET, group_badge, white_contrast
from app.daily_spend import DAILY_SPEND_TREE, _color_for, ensure_spend_categories, next_sort_order
from app.db import get_db
from app.db_admin import SYSTEM_CATEGORY_SLUGS
from app.models import AdminAuditLog, DailySpend, SpendCategory, User, category_name_key
from app.security import get_authenticated_user, is_admin, redirect_to_login, require_csrf

router = APIRouter()

PAGE = "/admin/categories"
API = "/admin/api/categories"
NAME_MAX = 64
SMS_FEE_SLUG = "sms_fee"
NO_STORE = {"Cache-Control": "no-store"}

ERR_NAME = "نام دسته را بنویسید."
ERR_NAME_LONG = "نام حداکثر ۶۴ نویسه است."
ERR_DUP = "دسته‌ای با همین نام در همین گروه هست."
ERR_PARENT = "گروه انتخاب‌شده پیدا نشد."
ERR_HAS_KIDS = "گروهی که زیردسته دارد نمی‌تواند زیر گروه دیگری برود."
ERR_TO_GROUP = "زیردسته را نمی‌شود گروه کرد؛ گروه تازه بسازید."
ERR_ICON = "یکی از آیکن‌های فهرست را انتخاب کنید."
ERR_COLOR = "یکی از رنگ‌های فهرست را انتخاب کنید."
ERR_SYSTEM = "این دستهٔ سیستمی برای خرج‌های پیامکی لازم است و این بخشش قفل است."
ERR_STALE = "این دسته همین حالا در صفحهٔ دیگری تغییر کرده. صفحه را تازه کنید."


# ---------- access ----------

def _wants_json(request: Request) -> bool:
    return request.url.path.startswith("/admin/api/")


def _admin(request: Request, db: Session):
    """User for an admin; otherwise the response: signed out -> login (401 for the API), not admin -> 403."""
    user = get_authenticated_user(request, db)
    if user is None:
        if _wants_json(request):
            return JSONResponse({"ok": False, "error": "signed_out"}, status_code=401, headers=NO_STORE)
        return redirect_to_login(request)
    if not is_admin(user):
        if _wants_json(request):
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403, headers=NO_STORE)
        return PlainTextResponse("forbidden", status_code=403)
    return user


def _csrf(request: Request) -> None:
    require_csrf(request, request.headers.get("x-csrf-token"))


async def _body(request: Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _err(status: int, **body) -> JSONResponse:
    return JSONResponse({"ok": False, **body}, status_code=status, headers=NO_STORE)


# ---------- reading ----------

def _counts(db: Session) -> dict[int, int]:
    return {cid: n for cid, n in db.query(DailySpend.category_id, func.count(DailySpend.id)).group_by(DailySpend.category_id)}


def _version(row: SpendCategory) -> str:
    state = [row.name, row.parent_id, row.icon or "", row.color or "", bool(row.archived), row.sort_order]
    return hashlib.sha256(json.dumps(state, ensure_ascii=False).encode()).hexdigest()[:12]


def _locks(row: SpendCategory) -> list[str]:
    if row.slug not in SYSTEM_CATEGORY_SLUGS:
        return []
    locks = ["slug", "parent", "archive", "delete"]
    if row.slug == SMS_FEE_SLUG:
        locks.append("name")
    return locks


def _ordered(db: Session) -> list[SpendCategory]:
    rows = db.query(SpendCategory).order_by(SpendCategory.sort_order.asc(), SpendCategory.id.asc()).all()
    parents = [r for r in rows if r.parent_id is None]
    out: list[SpendCategory] = []
    for p in parents:
        out.append(p)
        out.extend(r for r in rows if r.parent_id == p.id)
    known = {r.id for r in out}
    out.extend(r for r in rows if r.id not in known)  # a child whose parent is missing: still listed
    return out


def category_rows(db: Session) -> list[dict]:
    """Every category in tree order, with counts only (no amounts, no usernames)."""
    counts = _counts(db)
    rows = _ordered(db)
    kids: dict[int, int] = {}
    for r in rows:
        if r.parent_id is not None:
            kids[r.parent_id] = kids.get(r.parent_id, 0) + 1
    by_id = {r.id: r for r in rows}
    group_index = {r.id: i for i, r in enumerate(x for x in rows if x.parent_id is None)}
    out = []
    for r in rows:
        parent = by_id.get(r.parent_id) if r.parent_id else None
        out.append({
            "id": r.id,
            "parent_id": r.parent_id,
            "name": r.name,
            "slug": r.slug,
            "is_seed": bool(r.is_seed),
            "sort_order": int(r.sort_order or 0),
            "archived": bool(r.archived),
            "icon": r.icon or "",
            "color": r.color or "",
            "shown_color": _color_for(r, group_index.get(r.id, 0)) if r.parent_id is None else "",
            "badge": group_badge(r.icon, r.name) if r.parent_id is None else group_badge(parent.icon if parent else "",
                                                                                         parent.name if parent else r.name),
            "spend_count": counts.get(r.id, 0),
            "child_count": kids.get(r.id, 0),
            "system": r.slug in SYSTEM_CATEGORY_SLUGS,
            "locks": _locks(r),
            "version": _version(r),
        })
    return out


def page_config() -> dict:
    return {
        "api": API,
        "palette": [{"hex": h, "name": n, "contrast": round(white_contrast(h), 2)} for h, n in PALETTE],
        "icons": [{"icon": i, "name": n} for i, n in ICON_CHOICES],
        "seed_groups": len(DAILY_SPEND_TREE),
        "seed_children": sum(len(c) for _, _, c in DAILY_SPEND_TREE),
    }


# ---------- validation ----------

def _clean_name(raw) -> str:
    return " ".join(str(raw or "").split())


def _name_error(db: Session, name: str, parent_id: int | None, row_id: int | None) -> str | None:
    if not name:
        return ERR_NAME
    if len(name) > NAME_MAX:
        return ERR_NAME_LONG
    q = db.query(SpendCategory).filter(SpendCategory.name_key == category_name_key(name))
    q = q.filter(SpendCategory.parent_id.is_(None)) if parent_id is None else q.filter(SpendCategory.parent_id == parent_id)
    if any(other.id != row_id for other in q.all()):
        return ERR_DUP
    return None


def _style_errors(data: dict, row: SpendCategory | None) -> tuple[dict, str | None, str | None]:
    """(field errors, icon, colour) for a group. An unchanged legacy value is kept as it is."""
    errors = {}
    icon = str(data.get("icon") or "").strip() if "icon" in data else (row.icon or "" if row else "")
    color = str(data.get("color") or "").strip().lower() if "color" in data else (row.color or "" if row else "")
    if icon and icon not in ICON_SET and not (row is not None and icon == (row.icon or "")):
        errors["icon"] = ERR_ICON
    if color and color not in PALETTE_SET and not (row is not None and color == (row.color or "").lower()):
        errors["color"] = ERR_COLOR
    return errors, icon or None, color or None


def _parent_from(db: Session, raw) -> tuple[SpendCategory | None, str | None]:
    if raw in (None, "", 0, "0"):
        return None, None
    try:
        pid = int(raw)
    except (TypeError, ValueError):
        return None, ERR_PARENT
    parent = db.get(SpendCategory, pid)
    if parent is None or parent.parent_id is not None:
        return None, ERR_PARENT
    return parent, None


def _audit(db: Session, actor: User, action: str, targets: list[dict], counts: dict | None = None) -> None:
    db.add(AdminAuditLog(actor_username=actor.username, action=action[:32],
                         targets_json=json.dumps(targets, ensure_ascii=False),
                         counts_json=json.dumps(counts or {}, ensure_ascii=False)))


def _renumber(db: Session, parent_id: int | None, skip_id: int | None = None) -> None:
    q = db.query(SpendCategory)
    q = q.filter(SpendCategory.parent_id.is_(None)) if parent_id is None else q.filter(SpendCategory.parent_id == parent_id)
    rows = [r for r in q.order_by(SpendCategory.sort_order.asc(), SpendCategory.id.asc()).all() if r.id != skip_id]
    for i, r in enumerate(rows):
        r.sort_order = i


def _ok(db: Session, **extra) -> JSONResponse:
    return JSONResponse({"ok": True, "rows": category_rows(db), **extra}, headers=NO_STORE)


def _load(db: Session, cid: int) -> SpendCategory | None:
    return db.get(SpendCategory, cid)


def _stale(row: SpendCategory, data: dict) -> bool:
    expect = data.get("version")
    return bool(expect) and expect != _version(row)


# ---------- page ----------

@router.get(PAGE)
async def categories_page(request: Request, db: Session = Depends(get_db)):
    admin = _admin(request, db)
    if not isinstance(admin, User):
        return admin
    from app.web import render

    rows = category_rows(db)
    response = render(request, "admin_categories.html", db, rows=rows, config=page_config(),
                      active_count=sum(1 for r in rows if not r["archived"]),
                      archived_count=sum(1 for r in rows if r["archived"]),
                      group_count=sum(1 for r in rows if r["parent_id"] is None),
                      child_count=sum(1 for r in rows if r["parent_id"] is not None))
    response.headers["Cache-Control"] = "no-store"
    return response


# ---------- API ----------

@router.get(API)
async def api_list(request: Request, db: Session = Depends(get_db)):
    admin = _admin(request, db)
    if not isinstance(admin, User):
        return admin
    return _ok(db)


@router.post(API)
async def api_create(request: Request, db: Session = Depends(get_db)):
    admin = _admin(request, db)
    if not isinstance(admin, User):
        return admin
    _csrf(request)
    data = await _body(request)
    parent, perr = _parent_from(db, data.get("parent_id"))
    errors = {}
    if perr:
        errors["parent_id"] = perr
    name = _clean_name(data.get("name"))
    nerr = _name_error(db, name, parent.id if parent else None, None)
    if nerr:
        errors["name"] = nerr
    icon = color = None
    if parent is None:
        serr, icon, color = _style_errors(data, None)
        errors.update(serr)
    if errors:
        return _err(422, error=next(iter(errors.values())), fields=errors)
    row = SpendCategory(parent_id=parent.id if parent else None, name=name, slug=None, is_seed=False,
                        sort_order=next_sort_order(db, parent.id if parent else None), icon=icon, color=color,
                        archived=False)
    db.add(row)
    db.commit()
    return _ok(db, id=row.id)


@router.patch(API + "/{cid}")
async def api_update(cid: int, request: Request, db: Session = Depends(get_db)):
    admin = _admin(request, db)
    if not isinstance(admin, User):
        return admin
    _csrf(request)
    row = _load(db, cid)
    if row is None:
        return _err(404, error="دسته پیدا نشد.")
    data = await _body(request)
    if _stale(row, data):
        return _err(409, reason="stale", error=ERR_STALE)
    locks = _locks(row)
    errors: dict[str, str] = {}

    new_parent_id = row.parent_id
    if "parent_id" in data:
        parent, perr = _parent_from(db, data.get("parent_id"))
        new_parent_id = parent.id if parent else None
        if new_parent_id != row.parent_id:
            if "parent" in locks:
                return _err(409, reason="system", field="parent_id", error=ERR_SYSTEM)
            if perr:
                errors["parent_id"] = perr
            elif parent is not None and parent.id == row.id:
                errors["parent_id"] = ERR_PARENT
            elif row.parent_id is not None and new_parent_id is None:
                errors["parent_id"] = ERR_TO_GROUP
            elif row.parent_id is None and db.query(SpendCategory.id).filter(SpendCategory.parent_id == row.id).first():
                errors["parent_id"] = ERR_HAS_KIDS
    name = row.name
    if "name" in data:
        name = _clean_name(data.get("name"))
        if name != row.name and "name" in locks:
            return _err(409, reason="system", field="name", error=ERR_SYSTEM)
    if "slug" in data and (data.get("slug") or None) != row.slug:
        return _err(409, reason="system" if "slug" in locks else "readonly", field="slug", error=ERR_SYSTEM)
    if "parent_id" not in errors:
        nerr = _name_error(db, name, new_parent_id, row.id)
        if nerr:
            errors["name"] = nerr
    icon, color = row.icon, row.color
    if new_parent_id is None:
        serr, icon, color = _style_errors(data, row)
        errors.update(serr)
    if errors:
        return _err(422, error=next(iter(errors.values())), fields=errors)

    moved = new_parent_id != row.parent_id
    spend_count = db.query(func.count(DailySpend.id)).filter(DailySpend.category_id == row.id).scalar() or 0
    if moved and spend_count and not data.get("confirm_move"):
        return _err(409, reason="needs_confirm", spend_count=spend_count,
                    error="این زیردسته خرج دارد؛ جابه‌جایی‌اش خرج‌های قبلی را هم به گروه تازه می‌برد.")
    old_parent_id = row.parent_id
    row.name = name
    if moved:
        old_parent = db.get(SpendCategory, old_parent_id) if old_parent_id else None
        new_parent = db.get(SpendCategory, new_parent_id) if new_parent_id else None
        row.sort_order = next_sort_order(db, new_parent_id)
        row.parent_id = new_parent_id
        db.flush()
        _renumber(db, old_parent_id)
        _audit(db, admin, "category_reparent", [
            {"id": row.id, "name": row.name,
             "from": {"id": old_parent_id, "name": old_parent.name if old_parent else None},
             "to": {"id": new_parent_id, "name": new_parent.name if new_parent else None}}],
            {"spends": spend_count})
    if new_parent_id is None:
        row.icon, row.color = icon, color
    else:
        row.icon, row.color = None, None  # a subcategory shows its group's icon and colour
    db.commit()
    return _ok(db, id=row.id)


@router.post(API + "/{cid}/archive")
async def api_archive(cid: int, request: Request, db: Session = Depends(get_db)):
    admin = _admin(request, db)
    if not isinstance(admin, User):
        return admin
    _csrf(request)
    row = _load(db, cid)
    if row is None:
        return _err(404, error="دسته پیدا نشد.")
    if "archive" in _locks(row):
        return _err(409, reason="system", error=ERR_SYSTEM)
    counts = _counts(db)
    hidden = []
    if row.parent_id is None:
        hidden = [{"id": c.id, "name": c.name, "spend_count": counts.get(c.id, 0)}
                  for c in db.query(SpendCategory).filter(SpendCategory.parent_id == row.id, SpendCategory.archived.is_(False))
                  .order_by(SpendCategory.sort_order.asc(), SpendCategory.id.asc())]
    if not row.archived:
        row.archived = True
        _audit(db, admin, "category_archive", [{"id": row.id, "name": row.name}],
               {"spends": counts.get(row.id, 0), "hidden_children": len(hidden)})
        db.commit()
    return _ok(db, id=row.id, hidden_children=hidden)


@router.post(API + "/{cid}/restore")
async def api_restore(cid: int, request: Request, db: Session = Depends(get_db)):
    admin = _admin(request, db)
    if not isinstance(admin, User):
        return admin
    _csrf(request)
    row = _load(db, cid)
    if row is None:
        return _err(404, error="دسته پیدا نشد.")
    data = await _body(request)
    parent = db.get(SpendCategory, row.parent_id) if row.parent_id else None
    if parent is not None and parent.archived:
        if not data.get("with_parent"):
            return _err(409, reason="needs_parent_restore", needs_parent_restore=True, parent_id=parent.id,
                        parent_name=parent.name, error=f"گروه «{parent.name}» بایگانی است؛ اول آن را بازگردانید.")
        parent.archived = False
        _audit(db, admin, "category_restore", [{"id": parent.id, "name": parent.name}])
    if row.archived:
        row.archived = False
        _audit(db, admin, "category_restore", [{"id": row.id, "name": row.name}])
    db.commit()
    return _ok(db, id=row.id)


@router.delete(API + "/{cid}")
async def api_delete(cid: int, request: Request, db: Session = Depends(get_db)):
    admin = _admin(request, db)
    if not isinstance(admin, User):
        return admin
    _csrf(request)
    row = _load(db, cid)
    if row is None:
        return _err(404, error="دسته پیدا نشد.")
    if "delete" in _locks(row):
        return _err(409, reason="system", error=ERR_SYSTEM)
    spend_count = db.query(func.count(DailySpend.id)).filter(DailySpend.category_id == row.id).scalar() or 0
    child_count = db.query(func.count(SpendCategory.id)).filter(SpendCategory.parent_id == row.id).scalar() or 0
    if spend_count or child_count:
        return _err(409, reason="in_use", spend_count=spend_count, child_count=child_count,
                    error="این دسته خرج یا زیردسته دارد و حذف نمی‌شود؛ به‌جای حذف بایگانی‌اش کنید.")
    parent_id = row.parent_id
    _audit(db, admin, "category_delete", [{"id": row.id, "name": row.name, "parent_id": parent_id}])
    db.delete(row)
    db.flush()
    _renumber(db, parent_id)
    db.commit()
    return _ok(db, id=cid)


@router.post(API + "/reorder")
async def api_reorder(request: Request, db: Session = Depends(get_db)):
    admin = _admin(request, db)
    if not isinstance(admin, User):
        return admin
    _csrf(request)
    data = await _body(request)
    parent_raw = data.get("parent_id")
    ids = data.get("ids")
    if not isinstance(ids, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        return _err(422, error="ترتیب نامعتبر است.")
    if parent_raw in (None, ""):
        parent_id = None
    else:
        try:
            parent_id = int(parent_raw)
        except (TypeError, ValueError):
            return _err(422, error="گروه نامعتبر است.")
    q = db.query(SpendCategory)
    q = q.filter(SpendCategory.parent_id.is_(None)) if parent_id is None else q.filter(SpendCategory.parent_id == parent_id)
    siblings = {r.id: r for r in q.all()}
    if len(ids) != len(set(ids)) or set(ids) != set(siblings):
        return _err(409, reason="stale", error=ERR_STALE)
    for i, sid in enumerate(ids):
        siblings[sid].sort_order = i
    db.commit()
    return _ok(db)


@router.post(API + "/seed")
async def api_seed(request: Request, db: Session = Depends(get_db)):
    admin = _admin(request, db)
    if not isinstance(admin, User):
        return admin
    _csrf(request)
    if db.query(SpendCategory.id).first() is not None:
        return _err(409, reason="not_empty", error="جدول دسته‌ها خالی نیست.")
    ensure_spend_categories(db)
    return _ok(db)
