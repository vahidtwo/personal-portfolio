/* Admin «دسته‌های خرج» (/admin/categories): tree, ordering, add/edit sheet, archive/restore/delete, picker preview.
   Data comes from #ac-data (first paint) and /admin/api/categories. Counts only: no amounts, no usernames. */
(function () {
  "use strict";
  var page = document.querySelector("[data-ac-page]");
  if (!page) return;
  var DATA = JSON.parse(document.getElementById("ac-data").textContent);
  var CFG = DATA.config, API = CFG.api, CSRF = page.getAttribute("data-csrf");
  var rows = DATA.rows;
  var root = page.querySelector("[data-ac-root]"), live = page.querySelector("[data-ac-live]");
  var meta = page.querySelector("[data-ac-meta]"), newBtn = page.querySelector("[data-ac-new]");
  var mq = window.matchMedia("(max-width: 899px)");
  var state = { filter: "active", q: "", collapsed: {}, reorder: false, pvMode: "new", scroll: 0 };
  var FA = "۰۱۲۳۴۵۶۷۸۹";

  /* ---------- helpers ---------- */
  function fa(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, "٬").replace(/\d/g, function (d) { return FA[+d]; }); }
  function faDec(x) { return fa(String(x)).replace(".", "٫"); }
  function esc(s) { return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }
  function $(sel, el) { return (el || document).querySelector(sel); }
  function $$(sel, el) { return Array.prototype.slice.call((el || document).querySelectorAll(sel)); }
  function mobile() { return mq.matches; }
  function byId(id) { return rows.find(function (r) { return r.id === id; }); }
  function groups() { return rows.filter(function (r) { return r.parent_id === null; }); }
  function kidsOf(id) { return rows.filter(function (r) { return r.parent_id === id; }); }
  function sortSib(list) { return list.slice().sort(function (a, b) { return a.sort_order - b.sort_order || a.id - b.id; }); }
  function siblings(r) { return sortSib(r.parent_id === null ? groups() : kidsOf(r.parent_id)); }
  function hasLock(r, k) { return r.locks.indexOf(k) !== -1; }
  function swatch(hex) { return CFG.palette.find(function (p) { return p.hex === hex; }); }
  function groupColor(g) { return g ? (g.color || g.shown_color || "#475569") : "#475569"; }
  function firstLetter(name) { return String(name || "").replace(/\u200c/g, "").trim().slice(0, 1); }
  function badgeOf(g) { return g && g.icon ? g.icon : firstLetter(g ? g.name : ""); }
  function norm(s) {
    return String(s || "").replace(/\u064a/g, "\u06cc").replace(/\u0643/g, "\u06a9").replace(/\u200c/g, "").replace(/\s+/g, " ").trim().toLowerCase();
  }
  function announce(text) { live.textContent = ""; setTimeout(function () { live.textContent = text; }, 30); }
  function icon(path) { return '<svg class="ac-i" viewBox="0 0 24 24" aria-hidden="true">' + path + "</svg>"; }
  var I = {
    up: icon('<path d="M12 19V5M6 11l6-6 6 6"/>'), dn: icon('<path d="M12 5v14M6 13l6 6 6-6"/>'),
    grip: icon('<circle cx="9" cy="6" r="1"/><circle cx="15" cy="6" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="9" cy="18" r="1"/><circle cx="15" cy="18" r="1"/>'),
    edit: icon('<path d="M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4"/>'),
    more: icon('<circle cx="12" cy="5.5" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="12" cy="18.5" r="1.2"/>'),
    chev: icon('<path d="M6 9l6 6 6-6"/>'), plus: icon('<path d="M12 5v14M5 12h14"/>'),
    lock: icon('<rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/>'),
    search: icon('<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.3-4.3"/>'), x: icon('<path d="M6 6l12 12M18 6L6 18"/>'),
    warn: icon('<path d="M12 3l9.5 17h-19zM12 10v4M12 17h.01"/>'), info: icon('<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>'),
    archive: icon('<path d="M3.5 4.5h17v4h-17zM5 8.5V20h14V8.5M10 12h4"/>'), restore: icon('<path d="M4 12a8 8 0 1 0 2.4-5.7M4 4v4h4"/>'),
    trash: icon('<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v6M14 11v6"/>'), eye: icon('<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>'),
    check: icon('<path d="M5 12.5l4.5 4.5L19 7.5"/>'), sort: icon('<path d="M8 4v16M4 8l4-4 4 4M16 20V4M12 16l4 4 4-4"/>'),
    retry: icon('<path d="M20 12a8 8 0 1 1-2.4-5.7M20 4v4h-4"/>')
  };

  function api(method, path, body) {
    var ctl = window.AbortController ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctl) ctl.abort(); }, 15000);
    return fetch(API + (path || ""), {
      method: method, credentials: "same-origin", cache: "no-store", signal: ctl ? ctl.signal : undefined,
      headers: { "Content-Type": "application/json", Accept: "application/json", "X-CSRF-Token": CSRF },
      body: body === undefined ? undefined : JSON.stringify(body)
    }).then(function (r) {
      clearTimeout(timer);
      return r.json().catch(function () { return {}; }).then(function (j) { return { status: r.status, body: j }; });
    }, function (e) { clearTimeout(timer); throw e; });
  }
  function take(res) { if (res.body && res.body.rows) rows = res.body.rows; return res; }

  /* ---------- counts / meta ---------- */
  function counts() {
    var a = rows.filter(function (r) { return !r.archived; }).length;
    return { active: a, archived: rows.length - a, all: rows.length };
  }
  function drawMeta() {
    var g = groups().length, k = rows.length - g, c = counts();
    meta.textContent = "مشترک برای همهٔ کاربران، " + fa(g) + " گروه، " + fa(k) + " زیردسته، " + fa(c.archived) + " بایگانی";
  }

  /* ---------- toast ---------- */
  var toastEl = null, toastTimer = null;
  function toast(text, undo) {
    if (toastEl) toastEl.remove();
    clearTimeout(toastTimer);
    toastEl = document.createElement("div");
    toastEl.className = "ac-toast"; toastEl.setAttribute("role", "status");
    toastEl.innerHTML = "<span>" + esc(text) + "</span>" + (undo ? '<button type="button">برگرداندن</button>' : "");
    document.body.appendChild(toastEl);
    if (undo) $("button", toastEl).addEventListener("click", function () { closeToast(); undo(); });
    toastTimer = setTimeout(closeToast, undo ? 6000 : 4000);
  }
  function closeToast() { if (toastEl) { toastEl.remove(); toastEl = null; } }

  /* ---------- tree ---------- */
  function rowVisible(r) {
    if (state.filter === "all") return true;
    if (state.filter === "archived") return r.archived;
    if (r.archived) return false;
    if (r.parent_id !== null) { var p = byId(r.parent_id); return !!p && !p.archived; }
    return true;
  }
  function visibleSiblings(r) { return siblings(r).filter(rowVisible); }
  function arrows(r, canMove) {
    var vis = visibleSiblings(r), i = vis.indexOf(r), n = vis.length;
    var dis = function (b) { return b || !canMove ? ' aria-disabled="true"' : ""; };
    return '<button type="button" class="ac-ib" data-act="up" aria-label="بالا بردن «' + esc(r.name) + '»"' + dis(i <= 0) + ">" + I.up + "</button>" +
      '<button type="button" class="ac-ib" data-act="down" aria-label="پایین بردن «' + esc(r.name) + '»"' + dis(i >= n - 1) + ">" + I.dn + "</button>";
  }
  function badges(r) {
    var p = r.parent_id !== null ? byId(r.parent_id) : null, out = "";
    if (r.system) out += '<span class="ac-bdg">' + I.lock + "سیستمی</span>";
    if (r.archived) out += '<span class="ac-bdg ac-arc">بایگانی</span>';
    else if (p && p.archived) out += '<span class="ac-bdg ac-hid">پنهان با گروه</span>';
    return out;
  }
  function cic(g, sm, extra) {
    return '<span class="ac-cic' + (sm ? " ac-sm" : "") + (extra || "") + '" style="background:' + esc(groupColor(g)) + '" aria-hidden="true">' + esc(badgeOf(g)) + "</span>";
  }
  function canDrag() { return !state.q && (!mobile() || state.reorder); }
  function kidRow(k) {
    var mob = mobile(), reorder = state.reorder, h = "";
    h += '<div class="ac-row ac-krow' + (k.archived ? " ac-arch" : "") + '" tabindex="-1" data-id="' + k.id + '">';
    if (canDrag()) h += '<button type="button" class="ac-ib ac-handle" data-act="drag" aria-label="کشیدن «' + esc(k.name) + '» برای جابه‌جایی">' + I.grip + "</button>";
    h += '<div class="ac-nm"' + (mob && !reorder ? ' data-act="edit"' : "") + "><b>" + esc(k.name) + badges(k) + "</b>" +
      (k.system && !mob ? '<span class="ac-slug"><bdi dir="ltr">' + esc(k.slug) + "</bdi></span>" : "") + "</div>";
    if (!reorder) h += '<span class="ac-cnt"><b>' + fa(k.spend_count) + "</b> خرج</span>";
    h += '<div class="ac-acts">';
    if (!mob || reorder) h += arrows(k, true);
    if (!mob) h += '<span class="ac-sep" aria-hidden="true"></span><button type="button" class="ac-ib" data-act="edit" aria-label="ویرایش «' + esc(k.name) + '»">' + I.edit + "</button>";
    if (!reorder) h += '<button type="button" class="ac-ib" data-act="menu" aria-haspopup="menu" aria-expanded="false" aria-label="گزینه‌های «' + esc(k.name) + '»">' + I.more + "</button>";
    h += "</div></div>";
    return h;
  }
  function groupCard(g) {
    var kids = sortSib(kidsOf(g.id)), vis = kids.filter(rowVisible), activeKids = kids.filter(function (k) { return !k.archived; });
    var total = kids.reduce(function (a, k) { return a + k.spend_count; }, g.spend_count);
    var coll = !!state.collapsed[g.id], mob = mobile(), reorder = state.reorder;
    var h = '<section class="ac-card ac-grp' + (coll ? " ac-coll" : "") + (g.archived ? " ac-garch" : "") + '" data-group="' + g.id + '" aria-label="' + esc(g.name) + '">';
    h += '<div class="ac-row ac-ghead" tabindex="-1" data-id="' + g.id + '">';
    if (canDrag()) h += '<button type="button" class="ac-ib ac-handle" data-act="drag" aria-label="کشیدن «' + esc(g.name) + '» برای جابه‌جایی">' + I.grip + "</button>";
    h += cic(g) + '<div class="ac-nm"><b>' + esc(g.name) + badges(g) + "</b>" +
      '<span class="ac-sub">' + fa(activeKids.length) + " زیردستهٔ فعال، " + fa(total) + " خرج" +
      (g.system && !mob ? ' ، <bdi class="ac-slug" dir="ltr">' + esc(g.slug) + "</bdi>" : "") + "</span></div>";
    h += '<div class="ac-acts">';
    if (!mob || reorder) h += arrows(g, true) + '<span class="ac-sep" aria-hidden="true"></span>';
    if (!reorder) {
      if (!mob) h += '<button type="button" class="ac-ib" data-act="edit" aria-label="ویرایش گروه «' + esc(g.name) + '»">' + I.edit + "</button>";
      else h += '<button type="button" class="ac-ib" data-act="edit" aria-label="ویرایش گروه «' + esc(g.name) + '»">' + I.edit + "</button>";
      h += '<button type="button" class="ac-ib" data-act="menu" aria-haspopup="menu" aria-expanded="false" aria-label="گزینه‌های «' + esc(g.name) + '»">' + I.more + "</button>";
    }
    h += '<button type="button" class="ac-ib ac-chev" data-act="collapse" aria-expanded="' + (!coll) + '" aria-label="' + (coll ? "باز کردن" : "بستن") + " «" + esc(g.name) + '»">' + I.chev + "</button>";
    h += "</div></div>";
    if (!coll) {
      if (!activeKids.length && state.filter !== "archived")
        h += '<p class="ac-empty-g">' + I.info + "<span>این گروه زیردستهٔ فعال ندارد، پس در انتخاب‌گر کاربر دیده نمی‌شود.</span></p>";
      h += '<ul class="ac-kids" data-parent="' + g.id + '">' + vis.map(function (k) { return "<li>" + kidRow(k) + "</li>"; }).join("") + "</ul>";
      if (!reorder && !g.archived) h += '<button type="button" class="ac-addkid" data-act="addkid" data-id="' + g.id + '">' + I.plus + "زیردسته در «" + esc(g.name) + "»</button>";
    }
    return h + "</section>";
  }
  function highlight(name, q) {
    var nq = norm(q);
    if (!nq) return esc(name);
    var map = [], ns = "";
    for (var i = 0; i < name.length; i++) {
      var ch = name[i];
      if (ch === "\u200c") continue;
      if (/\s/.test(ch)) { if (ns.slice(-1) === " " || !ns) continue; ch = " "; }
      ch = ch.replace("\u064a", "\u06cc").replace("\u0643", "\u06a9").toLowerCase();
      ns += ch; map.push(i);
    }
    var at = ns.indexOf(nq);
    if (at < 0) return esc(name);
    var s = map[at], e = map[at + nq.length - 1] + 1;
    return esc(name.slice(0, s)) + "<mark>" + esc(name.slice(s, e)) + "</mark>" + esc(name.slice(e));
  }
  function searchView() {
    var q = norm(state.q);
    var hits = rows.filter(function (r) {
      var p = r.parent_id !== null ? byId(r.parent_id) : null;
      return norm(r.name).indexOf(q) !== -1 || (p && norm(p.name).indexOf(q) !== -1);
    });
    if (!hits.length) {
      return '<div class="ac-card ac-state"><div class="ac-big">' + I.search + "</div><h2>نتیجه‌ای برای «" + esc(state.q) + "» نیست</h2>" +
        '<p>نام را کوتاه‌تر بنویسید یا دسته را بسازید.</p><div class="ac-row2"><button type="button" class="ac-btn" data-act="clearq">پاک کردن جستجو</button>' +
        '<button type="button" class="ac-btn ac-p" data-act="createq">ساخت «' + esc(state.q) + "»</button></div></div>";
    }
    return '<div class="ac-card"><ul class="ac-res" aria-label="نتیجهٔ جستجو">' + hits.map(function (r) {
      var p = r.parent_id !== null ? byId(r.parent_id) : null;
      return '<li><div class="ac-row ac-krow' + (r.archived ? " ac-arch" : "") + '" tabindex="-1" data-id="' + r.id + '">' + cic(p || r, true) +
        '<div class="ac-nm"><b>' + highlight(r.name, state.q) + badges(r) + '</b><span class="ac-path">' +
        (p ? highlight(p.name, state.q) + " ‹ " + highlight(r.name, state.q) : "گروه") + "</span></div>" +
        '<span class="ac-cnt"><b>' + fa(r.spend_count) + '</b> خرج</span><div class="ac-acts"><button type="button" class="ac-ib" data-act="edit" aria-label="ویرایش «' +
        esc(r.name) + '»">' + I.edit + '</button><button type="button" class="ac-ib" data-act="menu" aria-haspopup="menu" aria-expanded="false" aria-label="گزینه‌های «' +
        esc(r.name) + '»">' + I.more + "</button></div></div></li>";
    }).join("") + "</ul></div>";
  }
  function archivedView() {
    var list = rows.filter(function (r) { return r.archived; });
    if (!list.length) return '<div class="ac-card ac-state"><div class="ac-big">' + I.archive + "</div><h2>دستهٔ بایگانی‌شده‌ای نیست.</h2></div>";
    return '<div class="ac-card"><ul class="ac-res" aria-label="بایگانی">' + list.map(function (r) {
      var p = r.parent_id !== null ? byId(r.parent_id) : null;
      var canDel = !r.spend_count && !r.child_count && !hasLock(r, "delete");
      return '<li><div class="ac-row ac-krow ac-arch" tabindex="-1" data-id="' + r.id + '">' + cic(p || r, true) +
        '<div class="ac-nm"><b>' + esc(r.name) + badges(r) + '</b><span class="ac-path">' + (p ? esc(p.name) + " ‹ " + esc(r.name) : "گروه") + "</span></div>" +
        '<span class="ac-cnt"><b>' + fa(r.spend_count) + '</b> خرج</span><div class="ac-acts">' +
        '<button type="button" class="ac-btn ac-sm" data-act="restore">' + I.restore + "بازگردانی</button>" +
        '<button type="button" class="ac-ib" data-act="delete" aria-label="حذف «' + esc(r.name) + '»"' + (canDel ? "" : ' aria-disabled="true"') + ">" + I.trash + "</button>" +
        "</div></div></li>";
    }).join("") + "</ul></div>";
  }
  function emptyTable() {
    return '<div class="ac-card ac-state"><div class="ac-big">' + I.plus + "</div><h2>هنوز دسته‌ای نیست</h2>" +
      "<p>دسته‌های پیش‌فرض (" + fa(CFG.seed_groups) + " گروه و " + fa(CFG.seed_children) + " زیردسته) را بسازید یا از صفر شروع کنید.</p>" +
      '<div class="ac-row2"><button type="button" class="ac-btn ac-p" data-act="seed">ساخت دسته‌های پیش‌فرض</button>' +
      '<button type="button" class="ac-btn" data-act="new">دستهٔ جدید</button></div></div>';
  }
  function toolbar() {
    var c = counts(), seg = [["active", "فعال", c.active], ["archived", "بایگانی", c.archived], ["all", "همه", c.all]];
    var h = '<div class="ac-tools"><div class="ac-search">' + I.search +
      '<input type="search" data-ac-q placeholder="جستجوی نام دسته یا گروه" aria-label="جستجوی نام دسته یا گروه" value="' + esc(state.q) + '">' +
      (state.q ? '<button type="button" class="ac-clr" data-act="clearq" aria-label="پاک کردن جستجو">' + I.x + "</button>" : "") + "</div>" +
      '<div class="ac-seg" role="group" aria-label="وضعیت">' + seg.map(function (s) {
        return '<button type="button" data-filter="' + s[0] + '" aria-pressed="' + (state.filter === s[0] && !state.q) + '" aria-label="' + s[1] + " " + fa(s[2]) + '">' +
          s[1] + " " + fa(s[2]) + "</button>";
      }).join("") + "</div>";
    h += '<div class="ac-mob ac-mobtools"><button type="button" class="ac-btn" data-act="reorder" aria-pressed="' + state.reorder + '">' + I.sort +
      (state.reorder ? "پایان مرتب‌سازی" : "مرتب‌سازی") + '</button><button type="button" class="ac-btn" data-act="preview">' + I.eye + "پیش‌نمایش انتخاب‌گر</button></div>";
    return h + "</div>";
  }
  var lastFocus = null;
  function render(focusId) {
    drawMeta();
    var q = $("[data-ac-q]", root), hadQ = q && document.activeElement === q, caret = hadQ ? q.selectionStart : 0;
    var main;
    if (!rows.length) main = emptyTable();
    else if (state.q) main = searchView();
    else if (state.filter === "archived") main = archivedView();
    else main = groups().length ? sortSib(groups()).filter(rowVisible).map(groupCard).join("") : emptyTable();
    var note = !state.q && state.filter !== "archived" && rows.length && !mobile()
      ? '<p class="ac-note">' + I.info + "<span>با دکمه‌های بالا/پایین یا کشیدن جابه‌جا کنید؛ ترتیب همین‌جا برای همهٔ کاربران ذخیره می‌شود. زیردسته فقط داخل گروه خودش جابه‌جا می‌شود.</span></p>" : "";
    root.innerHTML = toolbar() + '<div class="ac-alert-slot" data-ac-alert></div><div class="ac-lay"><section class="ac-tree" aria-label="فهرست دسته‌ها">' + note + main +
      "</section><aside class=\"ac-card ac-pv ac-desk\" aria-label=\"پیش‌نمایش انتخاب‌گر کاربر\">" + previewHtml(null) + "</aside></div>";
    if (hadQ) { var nq = $("[data-ac-q]", root); nq.focus(); try { nq.setSelectionRange(caret, caret); } catch (e) {} }
    var id = focusId || lastFocus;
    lastFocus = null;
    if (id) { var el = $('[data-id="' + id + '"]', root); if (el) el.focus({ preventScroll: false }); }
    bindDrag();
  }

  /* ---------- picker preview (same rules as «ثبت خرج») ---------- */
  function previewHtml(draft) {
    var list = rows.map(function (r) { return draft && draft.id === r.id ? Object.assign({}, r, draft.values) : r; });
    if (draft && draft.id === null) list.push(Object.assign({ id: -1, archived: false, spend_count: 0, slug: null, sort_order: 1e9, child_count: 0 }, draft.values));
    var keep = null;
    if (state.pvMode === "edit") keep = list.find(function (r) { return r.parent_id !== null && r.archived; }) || null;
    var get = function (id) { return list.find(function (r) { return r.id === id; }); };
    var active = function (r) { return !r.archived; };
    var kids = list.filter(function (r) {
      if (r.parent_id === null) return false;
      var p = get(r.parent_id);
      return (keep && r.id === keep.id) || (active(r) && p && active(p));
    });
    var withKid = {}; kids.forEach(function (k) { withKid[k.parent_id] = 1; });
    var gs = sortSib(list.filter(function (r) {
      return r.parent_id === null && (((active(r) && withKid[r.id]) && r.slug !== "sms") || (keep && keep.parent_id === r.id));
    }));
    var sel = draft && draft.values.parent_id ? get(draft.values.parent_id) : (draft && draft.id !== null && get(draft.id) && get(draft.id).parent_id === null ? get(draft.id) : null);
    if (keep && !sel) sel = get(keep.parent_id);
    if (!sel || gs.indexOf(sel) === -1) sel = gs[0];
    var dirty = function (r) { return draft && (r.id === draft.id || r.id === -1) ? " ac-new" : ""; };
    var h = "<h2>پیش‌نمایش انتخاب‌گر کاربر</h2><p class=\"ac-note\">همان چیزی که هر کاربر در «ثبت خرج» می‌بیند؛ «پیامک»، دسته‌های بایگانی و گروه بی‌زیردسته پنهان‌اند.</p>";
    h += '<div class="ac-seg ac-pvseg" role="group" aria-label="حالت پیش‌نمایش"><button type="button" data-pv="new" aria-pressed="' + (state.pvMode === "new") + '">خرج تازه</button>' +
      '<button type="button" data-pv="edit" aria-pressed="' + (state.pvMode === "edit") + '">ویرایش خرج</button></div>';
    h += '<div class="ac-phone"><span class="ac-flabel">دسته</span><div class="ac-chips">' + gs.map(function (g) {
      return '<span class="ac-chip' + dirty(g) + '" aria-pressed="' + (g === sel) + '"><span class="ac-sw" style="background:' + esc(groupColor(g)) + '"></span>' + esc(g.name) + "</span>";
    }).join("") + "</div>";
    var sk = sel ? sortSib(kids.filter(function (k) { return k.parent_id === sel.id; })) : [];
    h += '<span class="ac-flabel">زیردسته</span><div class="ac-chips">' + (sk.length ? sk.map(function (k, i) {
      return '<span class="ac-chip' + dirty(k) + '" aria-pressed="' + (i === 0) + '">' + esc(k.name) + "</span>";
    }).join("") : '<span class="ac-note">زیردسته‌ای نیست</span>') + "</div>";
    if (sel) h += '<div class="ac-sprow">' + cic(sel) + '<div class="ac-t"><b>' + esc(sk[0] ? sk[0].name : sel.name) + "</b><span>" + esc(sel.name) + "، امروز</span></div></div>";
    h += "</div>";
    if (draft) h += '<p class="ac-pvfoot ac-dirty">' + I.info + "<span>تغییر ذخیره‌نشده با خط‌چین نشان داده شده؛ پیش‌نمایش چیزی ذخیره نمی‌کند.</span></p>";
    else h += '<p class="ac-pvfoot">' + I.info + "<span>پیش‌نمایش فقط نمایش است و چیزی ذخیره نمی‌کند.</span></p>";
    return h;
  }
  function refreshPreview(draft) { $$(".ac-pv", document).forEach(function (a) { a.innerHTML = previewHtml(draft); }); }

  /* ---------- ordering ---------- */
  var pending = false;
  function saveOrder(parentId, ids, before, label, movedId) {
    pending = true;
    return api("POST", "/reorder", { parent_id: parentId, ids: ids }).then(function (res) {
      pending = false;
      if (res.status === 200 && res.body.ok) {
        take(res); render(movedId);
        if (before) toast("ترتیب «" + label + "» ذخیره شد", function () { saveOrder(parentId, before, null, label, movedId); });
        else toast("ترتیب برگشت");
        return;
      }
      throw res;
    }).catch(function (res) {
      pending = false;
      if (before) applyOrder(before);
      render(movedId);
      var stale = res && res.status === 409;
      showAlert(stale ? ((res.body && res.body.error) || "ترتیب در صفحهٔ دیگری عوض شده؛ صفحه را تازه کنید.")
        : "ذخیرهٔ ترتیب «" + label + "» نشد؛ ترتیب قبلی برگشت.", stale ? reload : function () { if (before) moveTo(parentId, ids, before, label, movedId); });
    });
  }
  function applyOrder(ids) { ids.forEach(function (id, i) { var r = byId(id); if (r) r.sort_order = i; }); }
  function moveTo(parentId, ids, before, label, movedId) { applyOrder(ids); render(movedId); saveOrder(parentId, ids, before, label, movedId); }
  function move(r, delta) {
    if (pending) return;
    var full = siblings(r), vis = visibleSiblings(r), i = vis.indexOf(r), j = i + delta;
    if (j < 0 || j >= vis.length) return;
    var before = full.map(function (x) { return x.id; });
    var rest = full.filter(function (x) { return x !== r; }), anchor = vis[j], at = rest.indexOf(anchor) + (delta > 0 ? 1 : 0);
    rest.splice(at, 0, r);
    var ids = rest.map(function (x) { return x.id; });
    var p = r.parent_id !== null ? byId(r.parent_id) : null, label = p ? p.name : "گروه‌ها";
    moveTo(r.parent_id, ids, before, label, r.id);
    var pos = visibleSiblings(r).indexOf(r) + 1;
    announce(r.name + " به جایگاه " + fa(pos) + " از " + fa(vis.length) + (p ? " در " + p.name : " در گروه‌ها") + " رفت");
  }
  var drag = null;
  function bindDrag() {
    $$(".ac-handle", root).forEach(function (h) {
      var row = h.closest("[data-id]"), holder = row.parentElement.tagName === "LI" ? row.parentElement : row.closest(".ac-grp");
      h.addEventListener("pointerdown", function () { holder.setAttribute("draggable", "true"); });
      holder.addEventListener("dragstart", function (e) {
        var r = byId(+row.getAttribute("data-id"));
        drag = { r: r, holder: holder };
        holder.classList.add("ac-lift");
        e.dataTransfer.effectAllowed = "move";
        try { e.dataTransfer.setData("text/plain", String(r.id)); } catch (x) {}
      });
      holder.addEventListener("dragend", function () {
        holder.removeAttribute("draggable"); holder.classList.remove("ac-lift");
        $$(".ac-dropline", root).forEach(function (d) { d.remove(); });
        drag = null;
      });
      holder.addEventListener("dragover", function (e) {
        if (!drag) return;
        var r = byId(+row.getAttribute("data-id"));
        if (!r || r === drag.r || r.parent_id !== drag.r.parent_id) return;
        e.preventDefault();
        var box = holder.getBoundingClientRect(), after = e.clientY > box.top + box.height / 2;
        $$(".ac-dropline", root).forEach(function (d) { d.remove(); });
        var line = document.createElement("div"); line.className = "ac-dropline"; line.setAttribute("aria-hidden", "true");
        holder.parentNode.insertBefore(line, after ? holder.nextSibling : holder);
        drag.target = r; drag.after = after;
        if (e.clientY < 60) window.scrollBy(0, -12); else if (e.clientY > window.innerHeight - 60) window.scrollBy(0, 12);
      });
      holder.addEventListener("drop", function (e) {
        if (!drag || !drag.target) return;
        e.preventDefault();
        var r = drag.r, full = siblings(r), before = full.map(function (x) { return x.id; });
        var rest = full.filter(function (x) { return x !== r; }), at = rest.indexOf(drag.target) + (drag.after ? 1 : 0);
        rest.splice(at, 0, r);
        var ids = rest.map(function (x) { return x.id; });
        if (ids.join() === before.join()) return;
        var p = r.parent_id !== null ? byId(r.parent_id) : null;
        moveTo(r.parent_id, ids, before, p ? p.name : "گروه‌ها", r.id);
      });
    });
  }

  /* ---------- alert / reload ---------- */
  function showAlert(text, retry) {
    var slot = $("[data-ac-alert]", root);
    if (!slot) return;
    slot.innerHTML = '<div class="ac-alert" role="alert">' + I.warn + "<p>" + esc(text) + "</p>" + (retry ? '<button type="button" class="ac-btn ac-sm">دوباره</button>' : "") + "</div>";
    if (retry) $("button", slot).addEventListener("click", function () { slot.innerHTML = ""; retry(); });
  }
  var loadTimer = null;
  function reload() {
    clearTimeout(loadTimer);
    loadTimer = setTimeout(function () {
      root.setAttribute("aria-busy", "true");
      root.innerHTML = skeleton();
      announce("در حال بارگیری دسته‌ها…");
    }, 300);
    return fetch(API, { credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" } })
      .then(function (r) { if (!r.ok) throw r; return r.json(); })
      .then(function (j) { clearTimeout(loadTimer); root.removeAttribute("aria-busy"); rows = j.rows; render(); })
      .catch(function () {
        clearTimeout(loadTimer); root.removeAttribute("aria-busy");
        root.innerHTML = '<div class="ac-card ac-state ac-err"><div class="ac-big">' + I.warn + "</div><h2>دسته‌ها بارگیری نشد</h2>" +
          "<p>اتصال به سرور برقرار نشد. چیزی تغییر نکرده؛ دوباره امتحان کنید.</p><div class=\"ac-row2\"><button type=\"button\" class=\"ac-btn ac-p\" data-act=\"reload\">" + I.retry +
          'تلاش دوباره</button><a class="ac-btn" href="/admin/db">پایگاه داده</a></div></div>';
      });
  }
  function skeleton() {
    var g = "";
    for (var i = 0; i < 4; i++) {
      g += '<div class="ac-card ac-grp"><div class="ac-skrow ac-ghead"><span class="ac-sk" style="width:36px;height:36px;border-radius:50%"></span><span class="ac-sk" style="width:40%;height:16px"></span></div>';
      for (var j = 0; j < 3; j++) g += '<div class="ac-skrow"><span class="ac-sk" style="width:' + (50 - j * 8) + '%;height:14px"></span></div>';
      g += "</div>";
    }
    return '<div class="ac-lay"><section aria-busy="true">' + g + '</section><aside class="ac-card ac-pv ac-desk"><span class="ac-sk" style="height:220px"></span></aside></div>';
  }

  /* ---------- modal plumbing (sheets and dialogs) ---------- */
  var stack = [];
  function top() { return stack[stack.length - 1] || null; }
  function openModal(el, opener, first) {
    closeMenu();
    var scrim = document.createElement("div"); scrim.className = "ac-scrim";
    document.body.appendChild(scrim); document.body.appendChild(el);
    document.documentElement.classList.add("ac-locked");
    var m = { el: el, scrim: scrim, opener: opener || document.activeElement, busy: false };
    stack.push(m);
    scrim.addEventListener("click", function () { if (top() === m) closeModal(); });
    setTimeout(function () { var f = first || $("input,select,button:not([disabled])", el); if (f) f.focus(); }, 0);
    return m;
  }
  function closeModal(force) {
    var m = top();
    if (!m || (m.busy && !force)) return;
    stack.pop();
    m.el.remove(); m.scrim.remove();
    if (!stack.length) { document.documentElement.classList.remove("ac-locked"); refreshPreview(null); }
    if (m.opener && document.contains(m.opener)) m.opener.focus();
    else if (m.focusId) { var el = $('[data-id="' + m.focusId + '"]', root); if (el) el.focus(); }
  }
  document.addEventListener("keydown", function (e) {
    var modal = top();
    if (!modal) return;
    if (e.key === "Escape") { e.preventDefault(); closeModal(); return; }
    if (e.key === "Tab") {
      var f = $$('button:not([disabled]),input:not([disabled]),select:not([disabled]),a[href],[tabindex="0"]', modal.el).filter(function (x) { return x.offsetParent !== null; });
      if (!f.length) return;
      var a = f[0], z = f[f.length - 1];
      if (e.shiftKey && document.activeElement === a) { e.preventDefault(); z.focus(); }
      else if (!e.shiftKey && document.activeElement === z) { e.preventDefault(); a.focus(); }
    }
  });
  function dialog(opts) {
    var el = document.createElement("div");
    el.className = "ac-dlg"; el.setAttribute("role", "alertdialog"); el.setAttribute("aria-modal", "true");
    var hid = "ac-dlg-h" + Date.now();
    el.setAttribute("aria-labelledby", hid);
    el.innerHTML = '<h2 id="' + hid + '"><span class="ac-dlgic' + (opts.danger ? " ac-dng" : "") + '">' + (opts.icon || I.warn) + "</span>" + esc(opts.title) + "</h2>" + opts.body +
      '<div class="ac-acts2"><button type="button" class="ac-btn" data-safe>' + esc(opts.cancel || "انصراف") + "</button>" +
      (opts.ok ? '<button type="button" class="ac-btn ' + (opts.danger ? "ac-dngbtn" : "ac-p") + '" data-ok>' + esc(opts.ok) + "</button>" : "") + "</div>";
    var m = openModal(el, opts.opener, $("[data-safe]", el));
    $("[data-safe]", el).addEventListener("click", function () { closeModal(); });
    if (opts.ok) $("[data-ok]", el).addEventListener("click", function () {
      var b = $("[data-ok]", el);
      m.busy = true; b.disabled = true; b.innerHTML = '<span class="ac-spin" aria-hidden="true"></span>در حال انجام…'; b.setAttribute("aria-busy", "true");
      Promise.resolve(opts.onOk()).then(function () { m.busy = false; closeModal(true); }, function (msg) {
        m.busy = false; b.disabled = false; b.removeAttribute("aria-busy"); b.textContent = opts.ok;
        var p = $(".ac-dlgerr", el) || el.insertBefore(document.createElement("p"), $(".ac-acts2", el));
        p.className = "ac-dlgerr"; p.setAttribute("role", "alert"); p.textContent = msg || "انجام نشد؛ دوباره امتحان کنید.";
      });
    });
    return m;
  }

  /* ---------- archive / restore / delete ---------- */
  function errText(res) { return (res && res.body && res.body.error) || "اتصال به سرور برقرار نشد؛ دوباره امتحان کنید."; }
  function doArchive(r, opener) {
    return api("POST", "/" + r.id + "/archive").then(function (res) {
      if (res.status !== 200) return Promise.reject(errText(res));
      take(res); lastFocus = r.id; render();
      toast("«" + r.name + "» بایگانی شد", function () { doRestore(byId(r.id) || r); });
    }, function () { return Promise.reject(errText()); });
  }
  function doRestore(r, withParent) {
    return api("POST", "/" + r.id + "/restore", withParent ? { with_parent: true } : {}).then(function (res) {
      if (res.status === 409 && res.body.needs_parent_restore) {
        var p = byId(res.body.parent_id);
        dialog({ title: "گروه «" + (p ? p.name : "") + "» هم بایگانی است", ok: "بازگردانی هر دو",
          body: "<p>برای این‌که «" + esc(r.name) + "» در انتخاب‌گر دیده شود، گروهش هم باید بازگردانده شود. زیردسته‌های دیگرِ این گروه که فقط با گروه پنهان شده بودند هم برمی‌گردند.</p>",
          icon: I.restore, onOk: function () { return doRestore(r, true); } });
        return;
      }
      if (res.status !== 200) return Promise.reject(errText(res));
      take(res); lastFocus = r.id; render();
      toast("«" + r.name + "» بازگردانده شد", function () { doArchive(byId(r.id) || r); });
    }, function () { return Promise.reject(errText()); });
  }
  function askArchive(r, opener) {
    if (hasLock(r, "archive")) { dialog({ title: "«" + r.name + "» بایگانی نمی‌شود", body: "<p>این دستهٔ سیستمی برای ثبت خرج‌های پیامکی لازم است.</p>", cancel: "باشه", opener: opener }); return; }
    var active = r.parent_id === null ? sortSib(kidsOf(r.id)).filter(function (k) { return !k.archived; }) : [];
    if (!active.length) { doArchive(r, opener).catch(function (m) { showAlert(m); }); return; }
    dialog({
      title: "بایگانی گروه «" + r.name + "»؟", ok: "بایگانی گروه و " + fa(active.length) + " زیردسته", opener: opener,
      body: "<p>این زیردسته‌ها هم از انتخاب‌گر همهٔ کاربران پنهان می‌شوند:</p><div class=\"ac-chiplist\">" +
        active.map(function (k) { return '<span class="ac-bdg">' + esc(k.name) + "، " + fa(k.spend_count) + " خرج</span>"; }).join("") +
        '</div><ul class="ac-facts"><li>' + I.check + "<span>خرج‌های قبلی نام دسته‌شان را نگه می‌دارند.</span></li><li>" + I.restore +
        "<span>بازگردانی گروه دقیقاً همین زیردسته‌ها را برمی‌گرداند؛ زیردسته‌ای که جدا بایگانی شده، بایگانی می‌ماند.</span></li></ul>",
      onOk: function () { return doArchive(r, opener); }
    });
  }
  function askDelete(r, opener) {
    if (hasLock(r, "delete")) {
      dialog({ title: "«" + r.name + "» حذف نمی‌شود", cancel: "باشه", opener: opener, body: "<p>این دستهٔ سیستمی برای ثبت خرج‌های پیامکی لازم است و حذف یا بایگانی نمی‌شود.</p>" });
      return;
    }
    if (r.spend_count || r.child_count) {
      var why = [];
      if (r.spend_count) why.push(fa(r.spend_count) + " خرج");
      if (r.child_count) why.push(fa(r.child_count) + " زیردسته");
      dialog({
        title: "«" + r.name + "» حذف نمی‌شود", opener: opener, ok: r.archived ? null : "بایگانی «" + r.name + "»", cancel: r.archived ? "باشه" : "انصراف",
        body: "<p>این دسته " + why.join(" و ") + " دارد. حذف فقط برای دستهٔ بدون خرج و زیردسته است.</p>" +
          (r.archived ? "<p class=\"ac-muted\">این دسته الان هم بایگانی است و در انتخاب‌گر دیده نمی‌شود.</p>" :
          '<ul class="ac-facts"><li>' + I.archive + "<span>بایگانی آن را از انتخاب‌گر کاربران برمی‌دارد.</span></li><li>" + I.check +
          "<span>خرج‌های قبلی نام دسته را نگه می‌دارند.</span></li><li>" + I.restore + "<span>هر وقت بخواهید بازگردانده می‌شود.</span></li></ul>"),
        onOk: function () {
          var active = r.parent_id === null ? kidsOf(r.id).filter(function (k) { return !k.archived; }) : [];
          if (active.length) { setTimeout(function () { askArchive(byId(r.id), opener); }, 0); return; }
          return doArchive(r, opener);
        }
      });
      return;
    }
    dialog({
      title: "حذف «" + r.name + "»؟", ok: "حذف", danger: true, icon: I.trash, opener: opener,
      body: "<p>این دسته هیچ خرج و زیردسته‌ای ندارد. حذف برگشت ندارد.</p>",
      onOk: function () {
        return api("DELETE", "/" + r.id).then(function (res) {
          if (res.status !== 200) return Promise.reject(errText(res));
          take(res); render(); toast("«" + r.name + "» حذف شد");
        }, function () { return Promise.reject(errText()); });
      }
    });
  }

  /* ---------- row menu ---------- */
  var menu = null;
  function closeMenu() { if (menu) { menu.btn.setAttribute("aria-expanded", "false"); menu.el.remove(); menu = null; } }
  function openMenu(btn, r) {
    if (menu && menu.btn === btn) { closeMenu(); return; }
    closeMenu();
    var el = document.createElement("div"); el.className = "ac-menu"; el.setAttribute("role", "menu");
    var items = [["edit", I.edit, "ویرایش"]];
    if (r.parent_id === null && !r.archived) items.push(["addkid", I.plus, "زیردستهٔ تازه"]);
    items.push(r.archived ? ["restore", I.restore, "بازگردانی"] : ["archive", I.archive, "بایگانی"]);
    items.push(["delete", I.trash, "حذف…"]);
    el.innerHTML = items.map(function (it) {
      var locked = (it[0] === "archive" && hasLock(r, "archive")) || (it[0] === "delete" && hasLock(r, "delete"));
      return '<button type="button" role="menuitem" data-mact="' + it[0] + '"' + (locked ? ' aria-disabled="true"' : "") + ">" + it[1] + it[2] + (locked ? " (قفل)" : "") + "</button>";
    }).join("");
    btn.parentElement.appendChild(el);
    btn.setAttribute("aria-expanded", "true");
    menu = { el: el, btn: btn };
    $("button", el).focus();
    el.addEventListener("keydown", function (e) {
      var b = $$("button", el), i = b.indexOf(document.activeElement);
      if (e.key === "ArrowDown") { e.preventDefault(); b[(i + 1) % b.length].focus(); }
      if (e.key === "ArrowUp") { e.preventDefault(); b[(i - 1 + b.length) % b.length].focus(); }
      if (e.key === "Escape") { e.preventDefault(); closeMenu(); btn.focus(); }
    });
    el.addEventListener("click", function (e) {
      var b = e.target.closest("[data-mact]"); if (!b) return;
      var act = b.getAttribute("data-mact"); closeMenu();
      if (act === "edit") openSheet(r, btn);
      else if (act === "addkid") openSheet(null, btn, { parent_id: r.id });
      else if (act === "archive") askArchive(r, btn);
      else if (act === "restore") doRestore(r).catch(function (m) { showAlert(m); });
      else if (act === "delete") askDelete(r, btn);
    });
  }
  document.addEventListener("click", function (e) { if (menu && !menu.el.contains(e.target) && e.target.closest("[data-act=menu]") !== menu.btn) closeMenu(); });

  /* ---------- add / edit sheet ---------- */
  function openSheet(r, opener, preset) {
    var isNew = !r, isGroup0 = r ? r.parent_id === null : !(preset && preset.parent_id);
    var v = {
      name: r ? r.name : (preset && preset.name) || "",
      parent_id: r ? r.parent_id : (preset && preset.parent_id) || null,
      icon: r ? r.icon : "", color: r ? (r.color || r.shown_color || "") : CFG.palette[0].hex
    };
    var orig = JSON.stringify(v);
    var kind = isGroup0 ? "group" : "child";
    var el = document.createElement("div");
    el.className = "ac-sheet"; el.setAttribute("role", "dialog"); el.setAttribute("aria-modal", "true"); el.setAttribute("aria-labelledby", "ac-sh-h");
    var m;
    function title() {
      if (isNew) return kind === "group" ? "گروه تازه" : "زیردستهٔ تازه";
      return (r.parent_id === null ? "ویرایش گروه «" : "ویرایش «") + r.name + "»";
    }
    function groupOptions() {
      return sortSib(groups()).filter(function (g) { return (!g.archived || g.id === v.parent_id) && (!r || g.id !== r.id); });
    }
    function draw() {
      var g = kind === "group", parent = v.parent_id ? byId(v.parent_id) : null;
      var lockName = r && hasLock(r, "name"), lockParent = r && hasLock(r, "parent");
      var hasKids = r && r.parent_id === null && r.child_count > 0;
      var h = '<div class="ac-grab ac-mob" aria-hidden="true"></div><div class="ac-shh"><h2 id="ac-sh-h">' + esc(title()) + '</h2><button type="button" class="ac-ib" data-close aria-label="بستن">' + I.x + "</button></div>";
      h += '<div class="ac-shb"><p class="ac-topErr" role="alert" data-toperr hidden></p>';
      if (r && r.system) h += '<div class="ac-lockbox">' + I.lock + "<span>دستهٔ سیستمی برای خرج‌های پیامکی: شناسه، گروه، بایگانی و حذف قفل است" + (lockName ? "؛ نام هم قفل است، چون پیامک‌های کارمزد این دسته را پیدا می‌کنند" : "") + ". آیکن، رنگ و ترتیب را می‌شود عوض کرد.</span></div>";
      h += '<div class="ac-fld"><label for="ac-name">نام <span data-count>' + fa(v.name.length) + " از ۶۴</span></label>" +
        '<input id="ac-name" class="ac-inp' + (lockName ? " ac-lock" : "") + '" maxlength="64" value="' + esc(v.name) + '"' + (lockName ? " readonly" : "") +
        ' aria-describedby="ac-err-name" autocomplete="off"><p class="ac-errt" id="ac-err-name" data-err="name"></p></div>';
      if (isNew) {
        h += '<div class="ac-fld"><span class="ac-lb" id="ac-kind-l">نوع</span><div class="ac-seg ac-kind" role="radiogroup" aria-labelledby="ac-kind-l">' +
          '<button type="button" role="radio" data-kind="group" aria-checked="' + g + '">گروه</button><button type="button" role="radio" data-kind="child" aria-checked="' + !g + '">زیردسته</button></div></div>';
      } else if (g) {
        h += '<div class="ac-fld"><span class="ac-lb">نوع</span><div class="ac-inp ac-lock"><span>گروه' + (hasKids ? " (" + fa(r.child_count) + " زیردسته دارد)" : "") + "</span>" + I.lock + "</div>" +
          '<p class="ac-hint">' + I.info + "<span>" + (hasKids ? "گروهی که زیردسته دارد نمی‌تواند زیر گروه دیگری برود." : "گروه همان گروه می‌ماند؛ برای زیردسته، دستهٔ تازه بسازید.") + "</span></p></div>";
      }
      if (!g) {
        h += '<div class="ac-fld"><label for="ac-parent">گروه</label>';
        if (lockParent) h += '<div class="ac-inp ac-lock"><span>' + esc(parent ? parent.name : "") + "</span>" + I.lock + "</div>";
        else h += '<select id="ac-parent" class="ac-inp" aria-describedby="ac-err-parent_id ac-move-warn">' + groupOptions().map(function (o) {
          return '<option value="' + o.id + '"' + (o.id === v.parent_id ? " selected" : "") + ">" + esc(o.name) + (o.archived ? " (بایگانی)" : "") + "</option>";
        }).join("") + "</select>";
        var moving = r && v.parent_id !== r.parent_id;
        h += '<p class="ac-errt" id="ac-err-parent_id" data-err="parent_id"></p><p class="ac-warnt" id="ac-move-warn"' + (moving && r.spend_count ? "" : " hidden") + ">" + I.warn +
          "<span>" + (r ? fa(r.spend_count) : "") + " خرج قبلی هم با این زیردسته به گروه تازه می‌رود و نمودارهای ماه‌های قبل عوض می‌شود.</span></p></div>";
        h += '<div class="ac-inherit">' + cic(parent, true) + "<span>آیکن و رنگ از گروه «" + esc(parent ? parent.name : "") + "» می‌آید.</span>" +
          (parent ? '<button type="button" class="ac-link" data-editgroup="' + parent.id + '">ویرایش گروه</button>' : "") + "</div>";
      } else {
        h += '<div class="ac-fld"><span class="ac-lb" id="ac-icon-l">آیکن <span>روی همهٔ خرج‌های این گروه</span></span><div class="ac-icgrid" role="radiogroup" aria-labelledby="ac-icon-l" data-radios="icon">' +
          '<button type="button" role="radio" class="ac-icb" data-val="" aria-checked="' + (!v.icon) + '" aria-label="حرف اول نام" tabindex="' + (!v.icon ? 0 : -1) + '">' + esc(firstLetter(v.name) || "ح") + "</button>" +
          CFG.icons.map(function (ic) {
            var on = v.icon === ic.icon;
            return '<button type="button" role="radio" class="ac-icb" data-val="' + esc(ic.icon) + '" aria-checked="' + on + '" aria-label="' + esc(ic.name) + '" tabindex="' + (on ? 0 : -1) + '">' + esc(ic.icon) + "</button>";
          }).join("") + '</div><p class="ac-errt" data-err="icon"></p></div>';
        var sw = swatch(v.color);
        h += '<div class="ac-fld"><span class="ac-lb" id="ac-color-l">رنگ <span>فقط رنگ‌هایی که آیکن سفید رویشان خواناست</span></span><div class="ac-swgrid" role="radiogroup" aria-labelledby="ac-color-l" data-radios="color">' +
          CFG.palette.map(function (p) {
            var on = v.color === p.hex;
            return '<button type="button" role="radio" class="ac-swb" style="background:' + p.hex + '" data-val="' + p.hex + '" aria-checked="' + on + '" aria-label="' + esc(p.name) + "، کنتراست " + faDec(p.contrast.toFixed(1)) + ' به ۱" tabindex="' + (on || (!sw && p === CFG.palette[0]) ? 0 : -1) + '">' + (on ? I.check : "") + "</button>";
          }).join("") + '</div><p class="ac-cr">' + (sw ? I.check + "<span>آیکن سفید روی «" + esc(sw.name) + "»: <b>" + faDec(sw.contrast.toFixed(2)) + " به ۱</b> (حداقل ۴٫۵)</span>" :
          "<span>یک رنگ انتخاب کنید.</span>") + '</p><p class="ac-errt" data-err="color"></p></div>';
      }
      var pg = g ? { name: v.name || "گروه", icon: v.icon, color: v.color } : parent;
      h += '<div class="ac-fld"><span class="ac-lb">پیش‌نمایش ' + (JSON.stringify(v) !== orig ? '<span class="ac-bdg ac-dr">تغییر ذخیره‌نشده</span>' : "") + "</span>" +
        '<div class="ac-mini">' + cic(pg) + '<div class="ac-t"><b>' + esc(g ? "یک خرج" : v.name || "زیردسته") + "</b><span>" + esc(pg ? pg.name : "") + "، امروز</span></div>" +
        '<span class="ac-chip ac-new" aria-pressed="true"><span class="ac-sw" style="background:' + esc(groupColor(pg)) + '"></span>' + esc(pg ? pg.name : "") + "</span></div></div>";
      if (r) {
        h += '<dl class="ac-kv"><dt>استفاده</dt><dd>' + (g ? fa(kidsOf(r.id).reduce(function (a, k) { return a + k.spend_count; }, r.spend_count)) + " خرج در " + fa(r.child_count) + " زیردسته" : fa(r.spend_count) + " خرج") + "</dd>" +
          (r.slug ? '<dt>شناسهٔ سیستمی</dt><dd><bdi class="ac-slug" dir="ltr">' + esc(r.slug) + "</bdi></dd>" : "") +
          "<dt>دستهٔ آماده</dt><dd>" + (r.is_seed ? "بله" : "خیر") + "</dd></dl>";
        h += '<div class="ac-danger">' + (r.archived
          ? '<button type="button" class="ac-btn" data-dz="restore">' + I.restore + "بازگردانی</button>"
          : '<button type="button" class="ac-btn ac-warnbtn" data-dz="archive"' + (hasLock(r, "archive") ? " disabled" : "") + ">" + I.archive + "بایگانی</button>") +
          '<button type="button" class="ac-btn ac-dngbtn" data-dz="delete"' + (hasLock(r, "delete") ? " disabled" : "") + ">" + I.trash + "حذف…</button></div>";
      }
      h += "</div>";
      h += '<div class="ac-shf"><button type="button" class="ac-btn ac-p ac-lg" data-save>ذخیره</button><button type="button" class="ac-btn ac-lg" data-close>انصراف</button></div>';
      var focusSel = document.activeElement && el.contains(document.activeElement) ? (document.activeElement.id ? "#" + document.activeElement.id : null) : null;
      el.innerHTML = h;
      if (focusSel && $(focusSel, el)) { var fe = $(focusSel, el); fe.focus(); if (fe.setSelectionRange) try { fe.setSelectionRange(fe.value.length, fe.value.length); } catch (e) {} }
      refreshPreview({ id: r ? r.id : null, values: kind === "group" ? { name: v.name, parent_id: null, icon: v.icon, color: v.color } : { name: v.name, parent_id: v.parent_id } });
    }
    function setErr(fields, top) {
      $$("[data-err]", el).forEach(function (p) { var k = p.getAttribute("data-err"); p.textContent = (fields && fields[k]) || ""; });
      var name = $("#ac-name", el);
      if (fields && fields.name) name.setAttribute("aria-invalid", "true"); else name.removeAttribute("aria-invalid");
      var t = $("[data-toperr]", el); t.hidden = !top; t.textContent = top || "";
    }
    function busy(on) {
      m.busy = on; el.classList.toggle("ac-saving", on);
      $$("input,select,.ac-shb button,[data-close]", el).forEach(function (x) { x.disabled = on; });
      var b = $("[data-save]", el);
      b.disabled = on;
      if (on) { b.setAttribute("aria-busy", "true"); b.innerHTML = '<span class="ac-spin" aria-hidden="true"></span>در حال ذخیره…'; }
      else { b.removeAttribute("aria-busy"); b.textContent = "ذخیره"; }
    }
    function payload(confirm) {
      var p = { name: v.name };
      if (isNew) { p.parent_id = kind === "group" ? null : v.parent_id; }
      else {
        p.version = r.version;
        if (v.parent_id !== r.parent_id) p.parent_id = v.parent_id;
      }
      if (kind === "group") {
        if (isNew || v.icon !== r.icon) p.icon = v.icon;
        if (isNew || v.color !== (r.color || r.shown_color || "")) p.color = v.color;
      }
      if (confirm != null) { p.confirm_move = true; p.confirm_spend_count = confirm; }
      return p;
    }
    function askMove(count, onYes) {
      var to = byId(v.parent_id);
      dialog({
        title: "جابه‌جایی «" + r.name + "» به «" + (to ? to.name : "") + "»؟", ok: "جابه‌جا کن",
        body: "<p>" + fa(count) + " خرج قبلیِ همهٔ کاربران با این زیردسته به گروه «" + esc(to ? to.name : "") + "» می‌رود. خرج‌ها همان دسته را نگه می‌دارند، ولی نمودار ماه‌های قبل به‌حساب گروه تازه می‌آید.</p>",
        onOk: function () { setTimeout(onYes, 0); }
      });
    }
    function save(confirmCount) {
      if (!v.name.trim()) { setErr({ name: "نام دسته را بنویسید." }); $("#ac-name", el).focus(); return; }
      if (!isNew && confirmCount == null && v.parent_id !== r.parent_id && r.spend_count) {
        var seen = r.spend_count;
        askMove(seen, function () { save(seen); });
        return;
      }
      busy(true); setErr(null, null);
      var req = isNew ? api("POST", "", payload()) : api("PATCH", "/" + r.id, payload(confirmCount));
      req.then(function (res) {
        busy(false);
        if (res.status === 200 && res.body.ok) {
          take(res); var id = res.body.id; closeModal(true); render(id); toast("ذخیره شد"); return;
        }
        if (res.status === 422) { setErr(res.body.fields, null); var f = $("[aria-invalid=true]", el) || $("#ac-name", el); f.focus(); return; }
        if (res.status === 409 && res.body.reason === "needs_confirm") {
          var fresh = res.body.spend_count;  /* the count changed since the page loaded: ask again with the server's number */
          r.spend_count = fresh;
          askMove(fresh, function () { save(fresh); });
          return;
        }
        setErr(null, errText(res));
      }, function () { busy(false); setErr(null, "ذخیره نشد؛ اتصال به سرور برقرار نشد. چیزی که نوشتید سر جایش مانده است."); });
    }
    draw();
    m = openModal(el, opener, $("#ac-name", el));
    m.focusId = r ? r.id : null;
    el.addEventListener("input", function (e) {
      if (e.target.id === "ac-name") {
        v.name = e.target.value; $("[data-count]", el).textContent = fa(v.name.length) + " از ۶۴";
        setErr(null, null);
        refreshPreview({ id: r ? r.id : null, values: kind === "group" ? { name: v.name, parent_id: null, icon: v.icon, color: v.color } : { name: v.name, parent_id: v.parent_id } });
        var mini = $(".ac-mini .ac-t b", el); if (mini && kind !== "group") mini.textContent = v.name || "زیردسته";
      }
    });
    el.addEventListener("change", function (e) { if (e.target.id === "ac-parent") { v.parent_id = +e.target.value; draw(); $("#ac-parent", el).focus(); } });
    el.addEventListener("click", function (e) {
      var t = e.target.closest("button"); if (!t || t.disabled) return;
      if (t.hasAttribute("data-close")) { closeModal(); return; }
      if (t.hasAttribute("data-save")) { save(null); return; }
      if (t.hasAttribute("data-kind")) {
        kind = t.getAttribute("data-kind");
        if (kind === "child" && !v.parent_id) { var first = groupOptions()[0]; v.parent_id = first ? first.id : null; }
        if (kind === "group") v.parent_id = null;
        draw(); $('[data-kind="' + kind + '"]', el).focus(); return;
      }
      var radios = t.closest("[data-radios]");
      if (radios) { v[radios.getAttribute("data-radios")] = t.getAttribute("data-val"); var key = radios.getAttribute("data-radios"); draw(); var nb = $('[data-radios="' + key + '"] [aria-checked=true]', el); if (nb) nb.focus(); return; }
      if (t.hasAttribute("data-editgroup")) { var gid = +t.getAttribute("data-editgroup"); closeModal(true); openSheet(byId(gid), null); return; }
      var dz = t.getAttribute("data-dz");
      if (dz) {
        closeModal(true);
        if (dz === "archive") askArchive(r, null); else if (dz === "restore") doRestore(r).catch(function (msg) { showAlert(msg); }); else askDelete(r, null);
      }
    });
    el.addEventListener("keydown", function (e) {
      var radios = e.target.closest && e.target.closest("[data-radios],.ac-kind");
      if (!radios || ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].indexOf(e.key) === -1) return;
      e.preventDefault();
      var b = $$("button", radios), i = b.indexOf(e.target), step = (e.key === "ArrowLeft" || e.key === "ArrowDown") ? 1 : -1;
      b[(i + step + b.length) % b.length].click();
    });
  }

  /* ---------- mobile preview ---------- */
  function openPreview(opener) {
    var el = document.createElement("div");
    el.className = "ac-dlg ac-pvd"; el.setAttribute("role", "dialog"); el.setAttribute("aria-modal", "true"); el.setAttribute("aria-label", "پیش‌نمایش انتخاب‌گر");
    el.innerHTML = '<div class="ac-shh"><h2>پیش‌نمایش انتخاب‌گر</h2><button type="button" class="ac-ib" data-close aria-label="بستن">' + I.x + '</button></div><div class="ac-pv">' + previewHtml(null) + "</div>";
    openModal(el, opener, $("[data-close]", el));
    el.addEventListener("click", function (e) { if (e.target.closest("[data-close]")) closeModal(); });
  }

  /* ---------- events ---------- */
  root.addEventListener("input", function (e) {
    if (!e.target.matches("[data-ac-q]")) return;
    if (!state.q && e.target.value) state.scroll = window.scrollY;
    state.q = e.target.value;
    render();
    if (!state.q) window.scrollTo(0, state.scroll);
    var n = state.q ? $$(".ac-res li", root).length : 0;
    if (state.q) announce(n ? fa(n) + " نتیجه" : "نتیجه‌ای نیست");
  });
  root.addEventListener("click", function (e) {
    var pv = e.target.closest("[data-pv]");
    if (pv) { state.pvMode = pv.getAttribute("data-pv"); $$(".ac-pv").forEach(function (a) { a.innerHTML = previewHtml(null); }); return; }
    var f = e.target.closest("[data-filter]");
    if (f) { state.filter = f.getAttribute("data-filter"); state.q = ""; render(); $('[data-filter="' + state.filter + '"]', root).focus(); return; }
    var t = e.target.closest("[data-act]");
    if (!t || t.getAttribute("aria-disabled") === "true") return;
    var act = t.getAttribute("data-act"), rowEl = t.closest("[data-id]"), r = rowEl ? byId(+rowEl.getAttribute("data-id")) : null;
    if (act === "up" || act === "down") move(r, act === "up" ? -1 : 1);
    else if (act === "edit") openSheet(r, t);
    else if (act === "menu") openMenu(t, r);
    else if (act === "collapse") { var gid = +t.closest("[data-group]").getAttribute("data-group"); state.collapsed[gid] = !state.collapsed[gid]; render(); var c = $('[data-group="' + gid + '"] [data-act=collapse]', root); if (c) c.focus(); }
    else if (act === "addkid") openSheet(null, t, { parent_id: +t.getAttribute("data-id") });
    else if (act === "clearq") { state.q = ""; render(); window.scrollTo(0, state.scroll); $("[data-ac-q]", root).focus(); }
    else if (act === "createq") openSheet(null, t, { name: state.q });
    else if (act === "restore") doRestore(r).catch(function (m) { showAlert(m); });
    else if (act === "delete") askDelete(r, t);
    else if (act === "reorder") { state.reorder = !state.reorder; render(); $("[data-act=reorder]", root).focus(); }
    else if (act === "preview") openPreview(t);
    else if (act === "new") openSheet(null, t);
    else if (act === "reload") reload();
    else if (act === "seed") api("POST", "/seed").then(function (res) { if (res.status === 200) { take(res); render(); toast("دسته‌های پیش‌فرض ساخته شد"); } else showAlert(errText(res)); }, function () { showAlert(errText()); });
  });
  root.addEventListener("keydown", function (e) {
    if (!e.altKey || (e.key !== "ArrowUp" && e.key !== "ArrowDown")) return;
    var rowEl = e.target.closest && e.target.closest("[data-id]");
    if (!rowEl || state.q) return;
    e.preventDefault();
    move(byId(+rowEl.getAttribute("data-id")), e.key === "ArrowUp" ? -1 : 1);
  });
  newBtn.hidden = false;
  newBtn.addEventListener("click", function () { openSheet(null, newBtn); });
  if (mq.addEventListener) mq.addEventListener("change", function () { render(); });
  render();
  W_export();
  function W_export() { window.AdminCategories = { norm: norm, highlight: highlight, previewHtml: previewHtml }; }
})();
