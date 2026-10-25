#!/usr/bin/env python3
"""曼谷行程 2026-11：data/*.toml → index.html（單檔，CSS／JS 內嵌）＋ sw.js

只用標準庫（tomllib）。有錯就 exit 1，不產出半套。

隱私防線（三道）：
  1. 資料層：住宿只允許 landmark 欄位；出現 addr/tel/geo/host 等欄位就失敗。
  2. 私密字串：從 data/private.local（git-ignored）或環境變數 BKK_PRIVATE 讀入，
     出現在 data/*.toml 或產出的 HTML 就失敗。私密字串本身永遠不寫進 repo。
  3. 通用規則：13 碼票號、卡號、16 碼以上訂單號、英數混合訂位代號、住宿門牌、座標…
"""

import html
import json
import os
import re
import sys
import tomllib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
TRIP = DATA / "trip.toml"
LANG = DATA / "lang.toml"
PRIVATE = DATA / "private.local"
ASSETS = ROOT / "assets"
OUT = ROOT / "index.html"
SW = ROOT / "sw.js"

BKK = timezone(timedelta(hours=7))
WD = "一二三四五六日"

# 分類 → CSS class
CATS = {"大麻": "weed", "餐廳": "food", "酒吧": "bar", "按摩": "spa", "購物": "shop",
        "景點": "sight", "交通": "move", "住宿": "stay", "其他": "other"}
# 預算分類 → 顏色 class
BCATS = {"餐飲": "food", "酒吧": "bar", "購物": "shop", "按摩": "spa", "交通": "move",
         "大麻": "weed", "食品": "weed", "門票": "sight", "SIM": "other", "預備": "other"}
BCAT_DEFAULT = {"餐廳": "餐飲", "酒吧": "酒吧", "大麻": "大麻", "按摩": "按摩", "購物": "購物",
                "景點": "門票", "交通": "交通", "住宿": "交通", "其他": "餐飲"}
RESERVES = {"none", "walkin", "ask", "optional", "need", "booked"}
PAYS = {"cash", "card", "both", "online", "unknown", "none"}
MODES = {"grab", "bts", "walk", "moto", "plane", "none"}
MEALS = ["早", "午", "晚", "宵夜"]
MUST_DEFAULT = {"餐廳": "必吃", "酒吧": "必喝", "購物": "必買", "大麻": "必買", "其他": "必吃"}
HOME_FORBIDDEN = {"addr", "area", "tel", "geo", "host", "addr_th", "th", "door", "wifi", "code", "price"}
PRIVATE_KEYS = {"pnr", "confirm", "confirmation", "ticket", "card", "door", "door_code", "wifi", "booking_ref", "seat"}


def fail(msg):
    print(f"✗ build 失敗：{msg}", file=sys.stderr)
    sys.exit(1)


def warn(msg):
    print(f"⚠ {msg}", file=sys.stderr)


def esc(s):
    return html.escape(str(s), quote=True)


def minutes(t):
    """'10:50' → 650；05:00 前算當天最後（+1440）。"""
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", t or "")
    if not m:
        return None
    v = int(m[1]) * 60 + int(m[2])
    return v + (1440 if v < 5 * 60 else 0)


def thb(n):
    return f"฿{round(n):,}"


# ───────────────────────── 隱私防線 ─────────────────────────
GENERIC = [
    ("13 碼機票號", re.compile(r"(?<!\d)\d{3}[-\s]?\d{3}[-\s]?\d{7}(?!\d)")),
    ("13 碼機票號", re.compile(r"(?<!\d)\d{3}-\d{10}(?!\d)")),
    ("卡號", re.compile(r"(?<!\d)(?:\d{4}[-\s]){3}\d{4}(?!\d)")),
    ("15 碼以上訂單號", re.compile(r"(?<!\d)\d{15,19}(?!\d)")),
    ("卡號末四碼", re.compile(r"(?:尾號|末四碼|ending in)\s*\d{4}", re.I)),
    ("訂位代號／確認碼", re.compile(r"(?:PNR|訂位代號|確認碼|訂單號|booking\s*(?:number|ref|code)|confirmation\s*(?:code|no))\W{0,8}[A-Z0-9]{5,}", re.I)),
    ("英數混合 6 碼代號", re.compile(r"(?<![A-Za-z0-9#&;_-])(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{6}(?![A-Za-z0-9_-])")),
    ("英數混合 10 碼代號", re.compile(r"(?<![A-Za-z0-9#&;_-])(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{10}(?![A-Za-z0-9_-])")),
    ("住宿門牌", re.compile(r"\d{2,4}/\d{1,3}\s*,?\s*(?:Soi\s*)?Thong\s*-?\s*Lor?\b", re.I)),
    ("住宿門牌", re.compile(r"Thong\s*-?\s*Lor?\s*(?:Soi\s*)?21\D{0,20}\d{2,4}/\d{1,3}", re.I)),
    ("住宿座標", re.compile(r"13\.7\d{3,}\s*,\s*100\.5\d{3,}")),
    ("門鎖密碼", re.compile(r"(?:門鎖|門禁|door|keypad|鍵盤)\D{0,12}(?:密碼|code|pin)\D{0,8}\d{4,}", re.I)),
    ("房東書面同意大麻（與事實不符）", re.compile(r"房東[^。；\n]{0,20}(?:同意|允許|許可)[^。；\n]{0,12}大麻")),
]
# 已知會誤判的合法字串（例如 TG637 是 5 碼，不會中；這裡留給未來）
ALLOW = set()


def load_private():
    """私密字串：環境變數 BKK_PRIVATE（換行或 || 分隔）＋ data/private.local（每行一個，# 開頭是註解）。"""
    items = []
    env = os.environ.get("BKK_PRIVATE", "")
    items += [x.strip() for x in re.split(r"\n|\|\|", env) if x.strip()]
    if PRIVATE.exists():
        for line in PRIVATE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                items.append(line)
    if not items:
        if os.environ.get("BKK_PRIVATE_SKIP") == "1":
            warn("沒有私密字串清單（BKK_PRIVATE_SKIP=1）：只跑通用規則")
        else:
            fail(f"找不到私密字串清單。建立 {PRIVATE.relative_to(ROOT)}（每行一個：PNR、票號、確認碼、門牌…），"
                 "或設環境變數 BKK_PRIVATE；真的要跳過請設 BKK_PRIVATE_SKIP=1")
    return items


def guard(text, where, private):
    hits = []
    for s in private:
        pat = re.compile(r"(?<![0-9A-Za-z])" + re.escape(s) + r"(?![0-9A-Za-z])", re.I)
        if pat.search(text):
            hits.append("私密字串（見 private.local 第 %d 項）" % (private.index(s) + 1))
    for name, pat in GENERIC:
        for m in pat.finditer(text):
            if m.group(0) in ALLOW:
                continue
            ctx = text[max(0, m.start() - 30):m.end() + 10].replace("\n", " ")
            hits.append(f"{name}：…{ctx}…")
    if hits:
        fail(f"{where} 含有不能公開的內容，拒絕建置：\n  - " + "\n  - ".join(dict.fromkeys(hits)))


def scan_keys(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in PRIVATE_KEYS:
                fail(f"{path}.{k}：不允許的私密欄位名稱")
            scan_keys(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            scan_keys(v, f"{path}[{i}]")


# ───────────────────────── 讀檔＋驗證 ─────────────────────────
def read_toml(path):
    if not path.exists():
        fail(f"找不到 {path.relative_to(ROOT)}")
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        fail(f"{path.name} 語法錯誤：{e}")


def load():
    data = read_toml(TRIP)
    lang = read_toml(LANG).get("lang", [])
    scan_keys(data, "trip")
    meta = data.get("meta") or fail("缺 [meta]")
    if meta.get("schema") != 2:
        fail(f"meta.schema = {meta.get('schema')!r}，build.py 只認 2")
    for k in ("title", "start", "end", "budget_twd", "twd_thb", "rate_src", "edible_thc_max_mg", "reserve_thb"):
        if k not in meta:
            fail(f"[meta] 缺 {k}")

    plist = data.get("place", [])
    places = {p["id"]: p for p in plist if "id" in p}
    if len(places) != len(plist):
        fail("[[place]] 有缺 id 或 id 重複")
    for pid, p in places.items():
        for k in ("name", "cat", "icon", "what"):
            if not p.get(k):
                fail(f"[place {pid}] 缺 {k}")
        if p["cat"] not in CATS:
            fail(f"[place {pid}] cat={p['cat']!r} 不在 {list(CATS)}")
        if p.get("pay", "unknown") not in PAYS:
            fail(f"[place {pid}] pay={p['pay']!r}")
        if p.get("reserve", "none") not in RESERVES:
            fail(f"[place {pid}] reserve={p['reserve']!r}")
        if p["cat"] == "住宿":
            bad = HOME_FORBIDDEN & set(p)
            if bad:
                fail(f"[place {pid}] 住宿不可有欄位 {sorted(bad)}（只用 landmark_th／landmark_en）")
            if not p.get("landmark_th") or not p.get("landmark_en"):
                fail(f"[place {pid}] 住宿缺 landmark_th／landmark_en")

    days = data.get("day", [])
    if len(days) != (meta["end"] - meta["start"]).days + 1:
        fail(f"day 數量 {len(days)} 和 meta.start～end 不符")
    seen = set()
    for i, d in enumerate(days):
        did = d.get("id")
        if not did or did in seen:
            fail(f"day.id 缺或重複：{did}")
        seen.add(did)
        if d.get("date") != meta["start"] + timedelta(days=i):
            fail(f"[{did}] date={d.get('date')} 順序不對")
        for k in ("title", "area", "stop", "spend"):
            if k not in d:
                fail(f"[{did}] 缺 {k}")
        for k in d["spend"]:
            if k not in BCATS:
                fail(f"[{did}] spend 分類 {k!r} 不在 {list(BCATS)}")
        last = -1
        for j, s in enumerate(d["stop"]):
            where = f"[{did} stop {j + 1}]"
            pid = s.get("place")
            if pid and pid not in places:
                fail(f"{where} place={pid!r} 沒有對應的 [[place]]")
            p = places.get(pid, {})
            for k in ("time", "what"):
                if not s.get(k):
                    fail(f"{where} 缺 {k}")
            if not (s.get("name") or p.get("name")):
                fail(f"{where} 缺 name")
            t = minutes(s["time"])
            if t is None:
                fail(f"{where} time={s['time']!r} 要是 HH:MM")
            if t < last:
                fail(f"{where} 時間 {s['time']} 比上一站早")
            last = t
            s["_t"] = t
            cat = s.get("cat") or p.get("cat")
            if cat not in CATS:
                fail(f"{where} cat={cat!r}")
            if s.get("mode", "none") not in MODES:
                fail(f"{where} mode={s.get('mode')!r}")
            if s.get("pay", p.get("pay", "none")) not in PAYS:
                fail(f"{where} pay 不對")
            if s.get("reserve", p.get("reserve", "none")) not in RESERVES:
                fail(f"{where} reserve 不對")
            if s.get("meal") and s["meal"] not in MEALS:
                fail(f"{where} meal={s['meal']!r} 不在 {MEALS}")
            if s.get("bcat") and s["bcat"] not in BCATS:
                fail(f"{where} bcat={s['bcat']!r}")
            if not (s.get("q") or p.get("q")):
                fail(f"{where} 沒有 Google Maps 查詢字串（q）")
            r = s.get("reserve", p.get("reserve", "none"))
            if r == "need" and not s.get("book_by"):
                fail(f"{where} 需預約但沒有 book_by")

    used = {s.get("place") for d in days for s in d["stop"]} - {None}
    for pid, p in places.items():
        if pid not in used and not p.get("backup"):
            warn(f"地點 {pid} 沒有任何一站引用，也沒標 backup")
        if p["cat"] != "住宿" and not p.get("th") and pid in used:
            warn(f"地點 {pid} 沒有泰文店名（給司機看會顯示英文）")

    mx = meta["edible_thc_max_mg"]
    for e in data.get("edible", []):
        mg = e.get("thc_mg_per_pack")
        e["_bad"] = bool(e.get("illegal")) or (mg is not None and mg > mx)
        if not e["_bad"] and mg is None:
            fail(f"[edible {e.get('name')}] 合法品一定要寫 thc_mg_per_pack")
    for s in data.get("strain", []):
        if s.get("shop") and s["shop"] not in places:
            fail(f"[strain {s.get('name')}] shop={s['shop']!r} 不存在")
        if s.get("type") not in ("indica", "sativa", "hybrid", "cbd"):
            fail(f"[strain {s.get('name')}] type 不對")
    for t in data.get("todo", []):
        for k in ("group", "text", "due"):
            if k not in t:
                fail(f"[todo] 缺 {k}：{t}")
    if not lang:
        fail("lang.toml 沒有任何 [[lang]]（先跑 gen_lang.py）")
    return meta, days, places, data, lang


# ───────────────────────── 小元件 ─────────────────────────
SVG = {
    "nav": '<svg aria-hidden="true"><use href="#i-nav"/></svg>',
    "show": '<svg aria-hidden="true"><use href="#i-show"/></svg>',
    "tel": '<svg aria-hidden="true"><use href="#i-tel"/></svg>',
    "map": '<svg aria-hidden="true"><use href="#i-map"/></svg>',
    "chev": '<svg class="chev" aria-hidden="true"><use href="#i-chev"/></svg>',
    "exp": '<svg class="exp" aria-hidden="true"><use href="#i-exp"/></svg>',
}
SPRITE = '<svg width="0" height="0" style="position:absolute" aria-hidden="true"><symbol id="i-nav" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11l18-8-8 18-2-8-8-2z"/></symbol><symbol id="i-show" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="5" y="2" width="14" height="20" rx="3"/><path d="M9 7h6M9 11h6M9 15h3"/></symbol><symbol id="i-tel" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z"/></symbol><symbol id="i-map" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 21s-7-6.3-7-12a7 7 0 0 1 14 0c0 5.7-7 12-7 12z"/><circle cx="12" cy="9" r="2.5"/></symbol><symbol id="i-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></symbol><symbol id="i-exp" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></symbol></svg>'
MODE_ICON = {"grab": "🚕", "bts": "🚆", "walk": "🚶", "moto": "🛵", "plane": "✈️", "none": "•"}
TRAVEL = {"grab": "driving", "moto": "driving", "bts": "transit", "walk": "walking", "plane": "driving", "none": "driving"}


def maps_search(q):
    return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(q)


def maps_dir(q, mode="grab"):
    return f"https://www.google.com/maps/dir/?api=1&destination={quote_plus(q)}&travelmode={TRAVEL.get(mode, 'driving')}"


def tel_href(t):
    digits = re.sub(r"[^\d+]", "", t)
    if digits.startswith("0") and not digits.startswith("00"):
        digits = "+66" + digits[1:]
    return "tel:" + digits


def pay_chip(pay, note=""):
    t = {"cash": ("cash", "💵 只收現金"), "card": ("pay", "💳 可刷卡"), "both": ("pay", "💳／💵 都可"),
         "online": ("pay", "💳 線上付款"), "unknown": ("unk", "付款未驗 · 帶現金"), "none": None}[pay]
    if not t:
        return ""
    title = f' title="{esc(note)}"' if note else ""
    return f'<span class="chip {t[0]}"{title}>{t[1]}</span>'


def reserve_chip(r, note="", by=None):
    if r == "need":
        lab = f"需預約 · {by.month}/{by.day} 前" if by else "需預約"
        return f'<span class="chip need" data-by="{by.isoformat() if by else ""}">🔴 {esc(lab)}</span>'
    if r == "booked":
        return f'<span class="chip booked">✓ {esc(note or "已訂")}</span>'
    if r == "optional":
        return '<span class="chip walkin">可訂位（選訂）</span>'
    if r == "ask":
        return '<span class="chip ask">先問 · 再出發</span>'
    if r == "walkin":
        return '<span class="chip walkin">免訂 · 現場</span>'
    return ""


def must_items(lst, default_kind):
    out = []
    for m in lst or []:
        mm = re.match(r"^(必吃|必買|必喝|必做|必看)：(.+)$", m)
        out.append((mm[1], mm[2]) if mm else (default_kind, m))
    return out


def musts_html(lst, kind, cat, key=None):
    items = must_items(lst, kind)
    if not items:
        return ""
    cc = CATS.get(cat, "other")
    if key:
        bs = "".join(f'<button class="must" data-k="{esc(k)}" data-mk="{esc(key)}-{i}" aria-pressed="false">{esc(v)}</button>'
                     for i, (k, v) in enumerate(items))
    else:
        bs = "".join(f'<span class="must" data-k="{esc(k)}">{esc(v)}</span>' for k, v in items)
    return f'<div class="musts cat cat-{cc}">{bs}</div>'


def watch_html(lst):
    if not lst:
        return ""
    lis = "".join(f"<li>{esc(w)}</li>" for w in lst)
    return f'<div class="callout warn"><span class="ci" aria-hidden="true">❗</span><ul>{lis}</ul></div>'


# ───────────────────────── 給司機看 ─────────────────────────
def show_entry(p):
    if p["cat"] == "住宿":
        return {"th": p["landmark_th"], "en": p["landmark_en"], "ok": bool(p.get("th_ok", False)),
                "zh": "回住宿：到巷口就好（完整地址看 Airbnb App）", "map": maps_search(p["q"])}
    th = p.get("th", "")
    return {"th": th, "en": p.get("en") or p["name"], "ok": bool(th) and p.get("th_ok", True),
            "zh": p["name"] + (("｜" + p["area"]) if p.get("area") else ""), "map": maps_search(p["q"])}


# ───────────────────────── 渲染：一站 ─────────────────────────
def stop_fields(s, places):
    p = places.get(s.get("place"), {})
    cat = s.get("cat") or p["cat"]
    f = {
        "name": s.get("name") or p.get("name"),
        "sub": s.get("sub") or sub_of(p, s.get("name") or p.get("name")),
        "cat": cat, "cc": CATS[cat], "icon": s.get("icon") or p.get("icon") or "📌",
        "what": s["what"], "leg": s.get("leg", ""), "mode": s.get("mode", "none"),
        "pay": s.get("pay", p.get("pay", "none")), "pay_note": s.get("pay_note", p.get("pay_note", "")),
        "reserve": s.get("reserve", p.get("reserve", "none")),
        "reserve_note": s.get("reserve_note", p.get("reserve_note", "")),
        "by": s.get("book_by"), "cost": s.get("cost", 0), "leg_thb": s.get("leg_thb", 0),
        "q": s.get("q") or p.get("q"), "tel": p.get("tel", "") if cat != "住宿" else "",
        "place": s.get("place") or "", "mustdo": s.get("mustdo", p.get("mustdo", False)),
        "must": s.get("must") if "must" in s else p.get("must", []),
        "must_kind": s.get("must_kind") or p.get("must_kind") or MUST_DEFAULT.get(cat, "必吃"),
        "watch": (s.get("watch") or []) + (p.get("watch") or []),
        "dur": s.get("dur", ""), "label": s.get("label") or s["time"], "t": s["_t"],
        "meal": s.get("meal", ""), "hours": p.get("hours", ""),
    }
    if cat == "交通":
        f["must"] = s.get("must", [])
    return f


def sub_of(p, name):
    """原文店名（英文），跟中文名重複時不顯示。"""
    en = (p.get("en") or "").split(",")[0].strip()
    if not en or en.lower() in name.lower() or name.lower() in en.lower() or en.split()[0].rstrip(":").lower() == name.split()[0].lower():
        return ""
    return en


def chips_html(f):
    c = []
    if f["mustdo"]:
        c.append('<span class="chip mustdo">★ 必去</span>')
    c.append(reserve_chip(f["reserve"], f["reserve_note"], f["by"]))
    c.append(pay_chip(f["pay"], f["pay_note"]))
    if f["cost"]:
        c.append(f'<span class="chip cost">{thb(f["cost"])}</span>')
    if f["dur"]:
        c.append(f'<span class="chip">⏱ {esc(f["dur"])}</span>')
    if f["watch"]:
        c.append(f'<span class="chip need">❗ 注意 {len(f["watch"])}</span>')
    return '<div class="chips">' + "".join(x for x in c if x) + "</div>"


def stop_html(did, i, f):
    sid = f"s-{did}-{i}"
    more = []
    if f["reserve_note"]:
        more.append(f"<p><b>預約：</b>{esc(f['reserve_note'])}</p>")
    if f["pay_note"]:
        more.append(f"<p><b>付款：</b>{esc(f['pay_note'])}</p>")
    if f["hours"]:
        more.append(f"<p><b>營業：</b>{esc(f['hours'])}</p>")
    more.append(watch_html(f["watch"]))
    btns = [f'<a class="btn primary grow" href="{esc(maps_dir(f["q"], f["mode"] if f["mode"] != "none" else "grab"))}" target="_blank" rel="noopener">{SVG["nav"]}導航</a>',
            f'<a class="btn grow" href="{esc(maps_search(f["q"]))}" target="_blank" rel="noopener">{SVG["map"]}地圖</a>']
    if f["place"]:
        btns.append(f'<button class="btn grow" data-show="{esc(f["place"])}">{SVG["show"]}給司機看</button>')
    if f["tel"]:
        btns.append(f'<a class="btn" href="{esc(tel_href(f["tel"]))}" aria-label="打電話給 {esc(f["name"])}">{SVG["tel"]}</a>')
    if f["place"] and f["cat"] not in ("住宿",):
        btns.append(f'<a class="btn" href="#place-{esc(f["place"])}" data-goplace="{esc(f["place"])}">完整地點卡 →</a>')
    more.append('<div class="st-btns">' + "".join(btns) + "</div>")
    name = esc(f["name"]) + (f' <span style="font-weight:600;color:var(--ink3);font-size:var(--fs-sm)">{esc(f["sub"])}</span>' if f["sub"] else "")
    leg = ""
    if f["leg"]:
        extra = f" · {thb(f['leg_thb'])}" if f["leg_thb"] and "฿" not in f["leg"] else ""
        leg = f'<li class="leg" data-for="{sid}"><span class="rail"></span><p>{MODE_ICON[f["mode"]]} {esc(f["leg"])}{extra}</p></li>'
    musts = musts_html(f["must"], f["must_kind"], f["cat"])
    return leg + (
        f'<li class="stop cat-{f["cc"]}" id="{sid}" data-t="{f["t"]}" data-i="{i}">'
        f'<div class="tm">{esc(f["label"])}</div>'
        f'<div class="card"><button class="st-head" aria-expanded="false" aria-controls="{sid}-m">'
        f'<span class="tile sm cat-{f["cc"]}" aria-hidden="true">{f["icon"]}</span>'
        f'<span><span class="st-name" style="display:block">{name}</span>'
        f'<span class="st-what" style="display:block">{esc(f["what"])}</span>{chips_html(f)}{musts}</span>{SVG["chev"]}</button>'
        f'<div class="st-more" id="{sid}-m">{"".join(more)}</div></div></li>'
    )


# ───────────────────────── 渲染：一天 ─────────────────────────
def day_html(d, idx, n, places, meta):
    did = d["id"]
    dt = d["date"]
    fs = [stop_fields(s, places) for s in d["stop"]]
    plan = sum(d["spend"].values())
    rate = meta["twd_thb"]
    need = sum(1 for f in fs if f["reserve"] == "need")
    # 今天吃什麼
    meals = []
    for slot in MEALS:
        for i, f in enumerate(fs):
            if f["meal"] != slot:
                continue
            short = "宵" if slot == "宵夜" else slot
            alt = f["what"] if f["cat"] != "交通" else ""
            key = f"m-{f['place'] or did + str(i)}"
            go = (f'<a class="go" href="{esc(maps_dir(f["q"]))}" target="_blank" rel="noopener" aria-label="導航到 {esc(f["name"])}">{SVG["nav"]}</a>'
                  if f["cat"] != "交通" else "<span></span>")
            meals.append(
                f'<div class="meal{" night" if slot == "宵夜" else ""}" data-t="{f["t"]}">'
                f'<span class="slot">{short}<small>{esc(f["label"] if re.match(r"^~?\d", f["label"]) else f["label"][:2])}</small></span>'
                f'<div><h4>{esc(f["name"])}</h4>{musts_html(f["must"], f["must_kind"], "餐廳" if slot != "宵夜" else "酒吧", key=key)}'
                f'<p class="alt">{esc(alt)}</p></div>{go}</div>')
    notes = "".join(f"<li>{esc(x)}</li>" for x in d.get("notes", []))
    pack = "".join(f'<button class="pk" aria-pressed="false" data-pk="{did}-{i}"><span class="bx" aria-hidden="true">✓</span>{esc(x)}</button>'
                   for i, x in enumerate(d.get("pack", [])))
    stops = "".join(stop_html(did, i, f) for i, f in enumerate(fs))
    acc = ""
    for lab, key in (("☂️ 下雨怎麼辦", "rain"), ("🔋 體力不足", "tired"), ("🔁 其他備案", "more")):
        if d.get(key):
            acc += f'<details class="acc"><summary>{lab}</summary><div class="acc-body"><ul>{"".join(f"<li>{esc(x)}</li>" for x in d[key])}</ul></div></details>'
    spend_parts = " ＋ ".join(f"{k} {v:,}" for k, v in d["spend"].items())
    return f'''
<div class="dayview" id="day-{did}" data-day="{did}" data-date="{dt.isoformat()}" data-plan="{plan}">
  <div class="cols"><div>
    <p class="eyebrow">第 {idx + 1} 天 · 共 {n} 天</p>
    <div class="h-day"><span class="dn">D{idx + 1}</span><span class="dd">{dt.month}/{dt.day} 週{WD[dt.weekday()]}</span></div>
    <p class="theme">{esc(d["title"])}</p>
    <p class="area">{esc(d["area"])}</p>
    <p class="one">{esc(d.get("one", ""))}</p>
    <div class="daysum"><span>今天預估 <b>{thb(plan)}</b>（NT${round(plan / rate):,}）</span>{f'<span>需預約 <b>{need}</b> 處</span>' if need else ''}</div>
    <div class="hero-slot"></div>
    <div class="today-spend" hidden aria-label="今天花費"><span>今天已記</span><span class="b" role="img" aria-label="今天花費占計畫比例"><i style="width:0%"></i></span><span class="ts-v"><b>฿0</b> / {plan:,}</span><button class="add" type="button" aria-label="記一筆花費">＋</button></div>
    <h2 class="sec-title">今天吃什麼</h2>
    <div class="meals">{"".join(meals)}</div>
    <h2 class="sec-title">今天注意</h2>
    <div class="callout warn" role="note"><span class="ci" aria-hidden="true">⚠</span><ul>{notes}</ul></div>
    <div class="pack" aria-label="出門帶（點一下打勾）">{pack}</div>
  </div>
  <div>
    <h2 class="sec-title">時間軸</h2>
    <button class="show-done" type="button" hidden></button>
    <ol class="tl">{stops}</ol>
    {acc}
    <p class="demo">當日預估 {thb(plan)}：{esc(spend_parts)}（฿，兩人）</p>
  </div></div>
</div>'''


# ───────────────────────── 渲染：地點 ─────────────────────────
def place_html(pid, p, uses):
    cc = CATS[p["cat"]]
    chips = [f'<span class="chip cat-tag">{esc(p["cat"])}</span>']
    if p.get("backup"):
        chips.append('<span class="chip backup">備案</span>')
    if p.get("mustdo"):
        chips.append('<span class="chip mustdo">★ 必去</span>')
    if p["cat"] != "住宿":
        by = None
        for (_, _, f) in uses:
            if f["by"]:
                by = f["by"]
        chips.append(reserve_chip(p.get("reserve", "none"), p.get("reserve_note", ""), by))
        chips.append(pay_chip(p.get("pay", "unknown"), p.get("pay_note", "")))
    used = " · ".join(f"{lab} {f['label']}" for lab, _, f in uses[:3])
    kv = []
    if p.get("order"):
        kv.append(("做什麼", esc(p["order"])))
    if p.get("hours"):
        kv.append(("營業", esc(p["hours"])))
    if p.get("price"):
        kv.append(("價位", esc(p["price"])))
    if p.get("reserve_note"):
        kv.append(("預約", esc(p["reserve_note"])))
    if p.get("pay_note"):
        kv.append(("付款", esc(p["pay_note"])))
    if p.get("tel"):
        kv.append(("電話", f'<a href="{esc(tel_href(p["tel"]))}">{esc(p["tel"])}</a>'))
    if p.get("web"):
        kv.append(("網站", esc(p["web"])))
    kvh = "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in kv)
    if p["cat"] == "住宿":
        addr = (f'<div class="addr"><p class="eyebrow">給司機看（只到巷口）</p>'
                f'<p class="th" lang="th">{esc(p["landmark_th"])}{"" if p.get("th_ok") else "<span class=tbd>待核對</span>"}</p>'
                f'<p class="en">{esc(p["landmark_en"])}</p><p class="none">完整地址看 Airbnb App</p></div>')
    else:
        th = p.get("th")
        thl = (f'<p class="th" lang="th">{esc(th)}{"" if p.get("th_ok", True) else "<span class=tbd>待核對</span>"}</p>' if th
               else '<p class="none">泰文店名：待核對（給司機看英文或直接用 Grab）</p>')
        addr = f'<div class="addr"><p class="eyebrow">地址 · 給司機看</p>{thl}<p class="en">{esc(p.get("en") or p["name"])}{(" · " + esc(p["area"])) if p.get("area") else ""}</p></div>'
    btns = [f'<a class="btn primary grow" href="{esc(maps_dir(p["q"]))}" target="_blank" rel="noopener">{SVG["nav"]}導航</a>',
            f'<button class="btn grow" data-show="{esc(pid)}">{SVG["show"]}給司機看</button>',
            f'<a class="btn" href="{esc(maps_search(p["q"]))}" target="_blank" rel="noopener" aria-label="在 Google 地圖查看 {esc(p["name"])}">{SVG["map"]}</a>']
    if p.get("tel"):
        btns.append(f'<a class="btn" href="{esc(tel_href(p["tel"]))}" aria-label="打電話給 {esc(p["name"])}">{SVG["tel"]}</a>')
    kind = p.get("must_kind") or MUST_DEFAULT.get(p["cat"], "必吃")
    sub = sub_of(p, p["name"])
    return f'''<article class="card place cat cat-{cc}" id="place-{esc(pid)}" data-cat="{esc(p["cat"])}">
  <div class="pl-head"><span class="tile" aria-hidden="true">{p["icon"]}</span><div><h3>{esc(p["name"])}</h3>{f'<p class="local">{esc(sub)}</p>' if sub else ''}{f'<p class="pl-used">行程：{esc(used)}</p>' if used else ''}</div></div>
  <div class="chips">{"".join(c for c in chips if c)}</div>
  <p class="what">{esc(p["what"])}</p>
  {musts_html(p.get("must"), kind, p["cat"], key="p-" + pid)}
  {watch_html(p.get("watch"))}
  {f'<dl class="kv">{kvh}</dl>' if kvh else ''}
  {addr}
  <div class="st-btns">{"".join(btns)}</div>
</article>'''


def weed_html(data, places, meta):
    mx = meta["edible_thc_max_mg"]
    tlab = {"indica": ("ind", "Indica"), "sativa": ("sat", "Sativa"), "hybrid": ("hyb", "Hybrid"), "cbd": ("cbd", "CBD")}
    strains = []
    for s in data.get("strain", []):
        cls, lab = tlab[s["type"]]
        shop = places[s["shop"]]["name"] if s.get("shop") else "現場問"
        lv = s.get("thc_level", 2)
        fx = "".join(f'<span class="up">{esc(x)}</span>' for x in s.get("fx_up", [])) + \
             "".join(f'<span class="down">{esc(x)}</span>' for x in s.get("fx_down", []))
        strains.append(f'''<article class="card strain">
  <div class="strain-top"><div><h3>{esc(s["name"])}</h3><p class="from">{esc(shop)} · {esc(s.get("price", ""))}</p></div><span class="type {cls}">{esc(s.get("type_note") or lab)}</span></div>
  <div class="meter"><span>THC</span><span class="bar" role="img" aria-label="THC {esc(["", "低", "中", "高"][lv])}"><i class="l{lv}"></i></span><span class="val">{esc(["", "低", "中", "高"][lv])}</span></div>
  <p class="thct">{esc(s.get("thc_text", ""))}</p>
  <div class="fx">{fx}</div>
  <p class="who"><b>什麼時候：</b>{esc(s.get("when", ""))}</p>
</article>''')
    edibles = []
    for e in data.get("edible", []):
        shop = places[e["shop"]]["name"] if e.get("shop") else ""
        mg = e.get("thc_mg_per_pack")
        if e["_bad"]:
            flag = f"✕ 違法・不買" + (f" · 每{e.get('unit', '包')}約 {mg:g} mg THC（上限 {mx:g} mg）" if mg else "")
            edibles.append(f'''<article class="card edible bad"><p class="ed-flag">{esc(flag)}</p><div class="ed-body"><h3>{esc(e["name"])}</h3>{f'<p class="from" style="font-size:var(--fs-xs);color:var(--ink3)">{esc(shop)}</p>' if shop else ''}<p class="ed-note">{esc(e.get("note", ""))}</p></div></article>''')
            continue
        pos = lambda v: min(v / 10 * 100, 100)
        edibles.append(f'''<article class="card edible ok"><p class="ed-flag">✓ 合法 · 每{esc(e.get("unit", "包"))} {mg:g} mg THC（上限 {mx:g} mg）</p>
<div class="ed-body"><h3>{esc(e["name"])}</h3><p class="from" style="font-size:var(--fs-xs);color:var(--ink3)">{esc(shop)} · {esc(e.get("price", ""))}</p>
<div class="dose" role="img" aria-label="劑量尺：1 包 {mg:g} mg、2 包 {2 * mg:g} mg、3 包 {3 * mg:g} mg">
<div class="dose-scale"><span class="track"></span><span class="pin" style="left:{pos(mg):.0f}%" data-l="1"></span><span class="pin" style="left:{pos(2 * mg):.0f}%" data-l="2"></span><span class="pin" style="left:{pos(3 * mg):.0f}%" data-l="3 包＝上限"></span></div>
<div class="dose-legend"><span>0</span><span>新手起步 2.5–5 mg</span><span>10 mg+</span></div></div>
<ol class="steps">
<li><b>買之前</b><span>包裝上要有 <strong>13 碼 อย. 登記號</strong>、THC 標示、批號、效期；沒有就不買</span></li>
<li><b>D1 晚</b><span>1 包（{mg:g} mg），<strong>等滿 2 小時</strong>再判斷；不要因為「還沒感覺」追加</span></li>
<li><b>D5 晚</b><span>D1 沒感覺就 2 包（{2 * mg:g} mg），<strong>22:00 前在住宿吃完</strong></span></li>
<li><b>上限</b><span>一晚最多 3 包（{3 * mg:g} mg）</span></li>
<li><b>30–120 分</b><span>才開始有感，持續 4–8 小時</span></li>
<li><b>不要</b><span>配大量酒、出門前吃；只在住宿吃。吃的那晚不喝或只喝一杯</span></li>
<li><b>11/6</b><span>SkyFlyers 搭乘前不碰酒和大麻</span></li>
<li><b>太茫</b><span>喝水、吃東西、躺下休息，幾小時會退；嚴重打 1669</span></li>
<li><b>離境</b><span>剩下的 11/7 起床丟掉，不帶出泰國</span></li>
</ol><p class="ed-note">{esc(e.get("note", ""))}</p></div></article>''')
    return f'''<div class="weedx" data-cat="大麻" id="weed">
  <h2 class="sec-title">大麻 · 規則、品種、合法食品</h2>
  <div class="legal"><span aria-hidden="true">⚖️</span><span><b>先看規則：</b>買花要泰國執業者開的 <b>PT33 處方</b>（20 歲以上、護照正本）。食品只有 Thai FDA（อย.）登記、<b>每包 THC ≤ {mx:g} mg</b> 的合法；50 mg 軟糖、THC 油、vape 都違法。<b>只在住宿陽台用</b>，不在公共場所；<b>不帶出泰國</b>，11/7 離境前丟掉。</span></div>
  <p class="eyebrow" style="margin-top:12px">品種（男友用花；THC% 店家菜單沒列，現場問）</p>
  {"".join(strains)}
  <p class="who" style="margin-top:4px"><b>用法：</b>一口 → 等 15 分 → 再決定；跟酒同一天就先喝完、回陽台才用；用完不騎車。</p>
  <p class="eyebrow" style="margin-top:12px">合法食品（女友不吸菸；PT33 不涵蓋食品，她不一定要看診）</p>
  {"".join(edibles)}
</div>'''


# ───────────────────────── 渲染：7 天＋預算 ─────────────────────────
def budget_html(meta, days):
    rate = meta["twd_thb"]
    budget_thb = meta["budget_twd"] * rate
    cats = {}
    for d in days:
        for k, v in d["spend"].items():
            cats[k] = cats.get(k, 0) + v
    daily = sum(cats.values())
    cats["預備"] = meta["reserve_thb"]
    total = daily + meta["reserve_thb"]
    left = budget_thb - total
    order = sorted(cats.items(), key=lambda kv: -kv[1])
    stack = "".join(f'<i class="cat cat-{BCATS[k]}" style="flex:{v}" title="{esc(k)} {thb(v)}"></i>' for k, v in order)
    legend = "".join(f'<span class="cat cat-{BCATS[k]}">{esc(k)}<b>{v:,}<small>NT${round(v / rate):,}</small></b></span>' for k, v in order)
    mx = max(sum(d["spend"].values()) for d in days)
    bars = []
    for i, d in enumerate(days):
        p = sum(d["spend"].values())
        bars.append(f'<div class="dbar future" data-day="{d["id"]}" data-plan="{p}"><span>D{i + 1}</span><span class="b"><i style="width:{p / mx * 100:.1f}%"></i><u style="width:0%"></u></span><span class="v">計 {thb(p)}<small class="act"></small></span></div>')
    rd = meta["rate_src"]
    stamp_rate = f"1 TWD = {rate} THB（{esc(rd)}）"
    return f'''<article class="card budget" aria-label="預算摘要">
  <div class="bg-top">
    <div><p class="eyebrow">計畫花費（兩人）</p><p class="big">{thb(total)}</p><p class="bg-sub">NT${round(total / rate):,} · 預算 NT${meta["budget_twd"]:,}（{thb(budget_thb)}）· {total / budget_thb * 100:.0f}%</p></div>
    <p class="left">預估還剩<b>{thb(left)}</b>NT${round(left / rate):,}</p>
  </div>
  <div class="stack" role="img" aria-label="分類占比：{esc("、".join(f"{k} {v:,}" for k, v in order))}">{stack}</div>
  <div class="legend">{legend}</div>
  <p class="eyebrow" style="margin-top:18px">每天（฿；斜線＝計畫，實心＝已記帳）</p>
  <div class="days-bars">{"".join(bars)}</div>
  <p class="demo">{esc(meta["budget_note"])} 匯率 {stamp_rate}。每日小計 {thb(daily)} ＋ 預備／小費 {thb(meta["reserve_thb"])}。</p>
  <div id="spend-sum" class="today-spend" style="margin-top:12px"><span>已記帳</span><span class="b"><i style="width:0%"></i></span><span><b id="spend-total">฿0</b> <span id="spend-twd"></span></span><button class="add" type="button" aria-label="記一筆花費">＋</button></div>
  <details class="acc"><summary>🧾 記帳明細（只存在這支手機）</summary><div class="acc-body"><ul class="spend-list" id="spend-list"></ul>
  <div class="rowbtns"><button class="btn" type="button" id="spend-export">複製（貼給對方）</button><button class="btn" type="button" id="spend-import">貼上匯入</button><button class="btn" type="button" id="spend-clear">全部清除</button></div>
  <p>記帳只存在這支手機的瀏覽器，不會上傳；換手機、清除瀏覽資料就會不見。建議只由一人記。</p></div></details>
</article>'''


def overview_html(days, places):
    out = []
    for i, d in enumerate(days):
        fs = [stop_fields(s, places) for s in d["stop"]]
        need = sum(1 for f in fs if f["reserve"] == "need")
        star = [f["name"] for f in fs if f["mustdo"]]
        late = any(f["t"] >= 23 * 60 and f["cat"] in ("酒吧", "餐廳") for f in fs) or any(f["t"] >= 21 * 60 + 30 and f["cat"] == "酒吧" for f in fs)
        chips = []
        if need:
            chips.append(f'<span class="chip need">需預約 {need}</span>')
        for s in star:
            chips.append(f'<span class="chip mustdo">★ {esc(s)}</span>')
        if late:
            chips.append('<span class="chip cat-tag cat-bar">🌙 大夜</span>')
        p = sum(d["spend"].values())
        dt = d["date"]
        out.append(f'<li><button type="button" data-goto="{d["id"]}"><span class="d">D{i + 1}<small>{dt.month}/{dt.day} 週{WD[dt.weekday()]}</small></span>'
                   f'<span><span class="t" style="display:block">{esc(d["title"])}</span><span class="a" style="display:block">{esc(d["area"])}</span><span class="chips">{"".join(chips)}</span></span>'
                   f'<span class="amt"><b>{thb(p)}</b>計畫</span></button></li>')
    return '<ol class="ov">' + "".join(out) + "</ol>"


def todo_html(todos):
    groups = {"late": "🔴 原排 10/20–10/24 已逾期，今天就訂", "week": "🟠 本週", "bkk": "🟢 到曼谷才做"}
    out = []
    for g, lab in groups.items():
        items = sorted((t for t in todos if t["group"] == g), key=lambda t: t["due"])
        if not items:
            continue
        lis = []
        for t in items:
            tid = re.sub(r"\W+", "", t["text"])[:24]
            op = f' data-open="{t["open"].isoformat()}"' if t.get("open") else ""
            note = f'<span>{esc(t["note"])}</span>' if t.get("note") else ""
            lis.append(f'<li data-due="{t["due"].isoformat()}"{op}><button class="tk" type="button" aria-pressed="false" data-td="{esc(tid)}" aria-label="完成：{esc(t["text"])}">✓</button>'
                       f'<span class="tx"><b>{esc(t.get("icon", ""))} {esc(t["text"])}</b><span>{esc(t.get("how", ""))}</span>{note}</span>'
                       f'<span class="due ok">{t["due"].month}/{t["due"].day} 前</span></li>')
        out.append(f'<p class="todo-h">{lab}</p><ul class="todo">{"".join(lis)}</ul>')
    return "".join(out)


# ───────────────────────── 渲染：泰語 ─────────────────────────
def lang_html(lang):
    out = []
    n = 0
    for sec in lang:
        lis = []
        for r in sec["rows"]:
            n += 1
            th = r.get("th", "")
            lis.append(f'<li><button class="ph" type="button" data-th="{esc(th)}" data-ro="{esc(r.get("roman", ""))}" data-zh="{esc(r.get("zh", ""))}" data-en="{esc(r.get("en", ""))}">'
                       f'<span class="zh">{esc(r.get("zh", ""))}</span>'
                       + (f'<span class="th" lang="th">{esc(th)}</span>' if th else "")
                       + (f'<span class="ro">{esc(r["roman"])}</span>' if r.get("roman") else "")
                       + (f'<span class="en" lang="en">{esc(r.get("en", ""))}</span>' if r.get("en") else "")
                       + SVG["exp"] + "</button></li>")
        note = f'<p class="lang-note">{esc(sec["note"])}</p>' if sec.get("note") and not sec["note"].startswith("一次秀完") else ""
        out.append(f'<section class="lsec"><h3 class="lang-sec">{esc(sec["sec"])}</h3>{note}<ul class="phr">{"".join(lis)}</ul></section>')
    return "".join(out), n


# ───────────────────────── 組裝 ─────────────────────────
def build():
    private = load_private()
    for f in sorted(DATA.glob("*.toml")):
        guard(f.read_text(encoding="utf-8"), f"data/{f.name}", private)
    meta, days, places, data, lang = load()

    rate = meta["twd_thb"]
    css = (ASSETS / "style.css").read_text(encoding="utf-8")
    js = (ASSETS / "app.js").read_text(encoding="utf-8")
    now = datetime.now(BKK)
    stamp = now.strftime("%Y-%m-%d %H:%M")
    ver = now.strftime("%Y%m%d%H%M")

    # 反查：地點 → 用在哪幾站
    uses = {pid: [] for pid in places}
    stops_js = {}
    for i, d in enumerate(days):
        arr = []
        for j, s in enumerate(d["stop"]):
            f = stop_fields(s, places)
            if f["place"]:
                uses[f["place"]].append((f"D{i + 1}", j, f))
            arr.append({"t": f["t"], "l": f["label"], "n": f["name"], "s": f["sub"], "c": f["cc"], "ic": f["icon"],
                        "w": f["what"], "leg": f["leg"], "m": f["mode"], "q": f["q"], "p": f["place"],
                        "tel": tel_href(f["tel"]) if f["tel"] else "", "mv": f["cat"] == "交通" and f["mode"] in ("grab", "bts", "moto", "walk"),
                        "nav": maps_dir(f["q"], f["mode"] if f["mode"] != "none" else "grab"), "id": f"s-{d['id']}-{j}"})
        stops_js[d["id"]] = arr

    show = {pid: show_entry(p) for pid, p in places.items()}
    day_views = "".join(day_html(d, i, len(days), places, meta) for i, d in enumerate(days))
    strip = "".join(f'<button class="dchip" type="button" data-day="{d["id"]}">D{i + 1}<b>{d["date"].day}</b></button>' for i, d in enumerate(days))

    # 地點排序：行程用到的依首次出現順序，備案在後
    order = []
    for d in days:
        for s in d["stop"]:
            pid = s.get("place")
            if pid and pid not in order and places[pid]["cat"] != "住宿":
                order.append(pid)
    order += [pid for pid in places if pid not in order and places[pid]["cat"] != "住宿"]
    cat_count = {}
    for pid in order:
        cat_count[places[pid]["cat"]] = cat_count.get(places[pid]["cat"], 0) + 1
    filters = f'<button class="fchip" type="button" aria-pressed="true" data-f="">全部 {len(order)}</button>' + "".join(
        f'<button class="fchip cat cat-{CATS[c]}" type="button" aria-pressed="false" data-f="{c}"><span class="dot"></span>{c} {cat_count[c]}</button>'
        for c in CATS if c in cat_count)
    place_cards = "".join(place_html(pid, places[pid], uses[pid]) for pid in order if places[pid]["cat"] != "大麻")
    weed_cards = "".join(place_html(pid, places[pid], uses[pid]) for pid in order if places[pid]["cat"] == "大麻")
    lang_body, nphr = lang_html(lang)

    home = next(p for p in places.values() if p["cat"] == "住宿")
    calls = "".join(
        f'<a class="call{"" if c.get("main") else " alt"}{" wide" if len(c["num"]) > 12 else ""}" href="tel:{esc(c["tel"])}"><b>{esc(c["num"])}</b><span>{esc(c["label"])}</span></a>'
        for c in data.get("call", []))
    rules = "".join(f'<li><span><b>{esc(r["t"])}</b><span>{esc(r["d"])}</span></span></li>' for r in data.get("rule", []))
    infos = "".join(f'<details class="acc" open><summary>{esc(x["t"])}</summary><div class="acc-body"><ul>{"".join(f"<li>{esc(i)}</li>" for i in x["items"])}</ul></div></details>'
                    for x in data.get("info", []))
    conds = "".join(f'<div><dt>{esc(c["k"])}</dt><dd>{esc(c["v"])}</dd></div>' for c in data.get("cond", []))
    bcat_opts = [k for k in BCATS if k != "預備"]

    boot = {
        "start": meta["start"].isoformat(), "end": meta["end"].isoformat(), "rate": rate, "budget": meta["budget_twd"],
        "days": [{"id": d["id"], "date": d["date"].isoformat(), "plan": sum(d["spend"].values()), "n": i + 1}
                 for i, d in enumerate(days)],
        "stops": stops_js, "show": show, "ver": ver,
    }
    boot_json = json.dumps(boot, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    tabs = [("today", "今天", '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'),
            ("trip", "7 天", '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>'),
            ("places", "地點", '<path d="M12 21s-7-6.3-7-12a7 7 0 0 1 14 0c0 5.7-7 12-7 12z"/><circle cx="12" cy="9" r="2.5"/>'),
            ("lang", "泰語", '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>'),
            ("sos", "救急", '<path d="M12 3l9 16H3z"/><path d="M12 10v4M12 17v.5"/>')]
    tabbar = "".join(
        f'<button class="tab{" sos" if v == "sos" else ""}" role="tab" type="button" aria-selected="{"true" if v == "today" else "false"}" aria-controls="view-{v}" data-v="{v}">'
        f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">{ic}</svg>{lab}</button>'
        for v, lab, ic in tabs)

    page = f'''<!doctype html>
<html lang="zh-Hant-TW">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="曼谷 11 月">
<title>曼谷 11 月行程</title>
<meta name="theme-color" content="#f5f2ec" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#111113" media="(prefers-color-scheme: dark)">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Crect width='16' height='16' rx='4' fill='%23a94b16'/%3E%3Ctext x='8' y='12' font-size='10' text-anchor='middle' fill='white' font-family='sans-serif'%3EB%3C/text%3E%3C/svg%3E">
<script>document.documentElement.classList.add('js');try{{var t=localStorage.getItem('theme');if(t)document.documentElement.dataset.theme=t}}catch(e){{}}</script>
<style>
{css}
</style>
</head>
<body>
{SPRITE}
<header class="topbar"><div class="wrap">
  <div class="tb-title"><b id="tb-day">{esc(meta["title"])}</b><span id="tb-sub">曼谷 11/1–11/7</span></div>
  <button class="backtoday" id="backtoday" type="button" hidden>回到今天</button>
  <span class="net" id="net" title="連線狀態">線上</span>
  <button class="iconbtn" id="theme" type="button" aria-label="切換深淺色"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg></button>
</div></header>

<main class="wrap">
<section class="view active" id="view-today" aria-labelledby="t-today">
  <h1 class="sr" id="t-today">今天</h1>
  <nav class="daystrip" aria-label="選擇日期">{strip}</nav>
  <div id="pretrip" hidden style="margin-bottom:24px">
    <div class="count"><b id="cd">0</b><div><p>天後出發</p><p style="opacity:.9;font-weight:500">11/1（日）TG637 07:55 桃園 T1 → 10:50 曼谷</p></div></div>
    <h2 class="sec-title">待辦（依截止日）</h2>
    <div id="pre-todo"></div>
    <p class="eyebrow" style="margin-top:20px">行程預覽 · 點上方日期切換</p>
  </div>
  <div id="ended" class="callout info" hidden style="margin-bottom:16px"><span class="ci">🏁</span><span>旅程結束了。下面是最後一天的行程；預算頁可以看記帳結算。</span></div>
  {day_views}
</section>

<section class="view" id="view-trip" aria-labelledby="t-trip">
  <h2 class="sec-title" id="t-trip">預算 · 兩人 NT${meta["budget_twd"]:,}（不含機票、住宿）</h2>
  {budget_html(meta, days)}
  <h2 class="sec-title">7 天總覽（點一天看細節）</h2>
  {overview_html(days, places)}
  <details class="acc" id="todo-acc"><summary>📝 行前待辦與訂位</summary><div class="acc-body">{todo_html(data.get("todo", []))}</div></details>
  <details class="acc"><summary>🌦 這週的外部條件</summary><div class="acc-body"><dl class="cond">{conds}</dl></div></details>
</section>

<section class="view" id="view-places" aria-labelledby="t-places">
  <h2 class="sec-title" id="t-places">地點</h2>
  <div class="filters" role="group" aria-label="分類篩選">{filters}</div>
  <div class="places">{place_cards}
  {weed_cards}
  {weed_html(data, places, meta)}</div>
</section>

<section class="view" id="view-lang" aria-labelledby="t-lang">
  <h2 class="sec-title" id="t-lang">泰語 · 點一句放大給對方看</h2>
  <input class="search" id="q" type="search" placeholder="搜尋：多少錢、廁所、不辣、處方…" aria-label="搜尋句子">
  <div class="note">我是<span class="seg" role="group" aria-label="說話者性別"><button type="button" aria-pressed="true" data-g="m">男 ครับ</button><button type="button" aria-pressed="false" data-g="f">女 ค่ะ</button></span>句尾自動換</div>
  <p class="lang-note" style="margin-top:6px">共 {nphr} 句。⚠ 拼音是自編近似音、女生版是自動轉換，都沒有母語者校對；念不準就直接亮手機。</p>
  <ul class="phr"><li><button class="ph intro" type="button" data-th="" data-ro="" data-zh="自我介紹（一次秀完）" data-en="We are tourists from Taiwan. Our English is limited. Please speak slowly or type it out for us. Thank you."><span class="zh">自我介紹（一次秀完）</span><span class="en" style="font-size:var(--fs-md);color:var(--ink)">We are tourists from Taiwan. Our English is limited. Please speak slowly or type it out for us. Thank you.</span>{SVG["exp"]}</button></li></ul>
  <div id="phr-all">{lang_body}</div>
  <p class="noresult" id="noresult" hidden>找不到，換個字試試。</p>
</section>

<section class="view" id="view-sos" aria-labelledby="t-sos">
  <h2 class="sec-title" id="t-sos">緊急電話 · 點了直接撥</h2>
  <div class="sos-grid">{calls}</div>
  <h2 class="sec-title">回住宿 · 給司機看</h2>
  <article class="card home cat cat-stay">
    <div class="pl-head"><span class="tile" aria-hidden="true">🏠</span><div><h3 style="font-size:var(--fs-lg)">回住宿</h3><p class="local">{esc(home["landmark_en"])}</p></div></div>
    <p class="th" lang="th">{esc(home["landmark_th"])}</p>
    <p class="en" style="font-size:var(--fs-xs);color:var(--ink2);margin-top:4px">{esc(home["landmark_en"])}{"" if home.get("th_ok") else " · 泰文待核對"}</p>
    <div class="st-btns"><button class="btn primary grow" type="button" data-show="{esc(home["id"])}">{SVG["show"]}給司機看</button><a class="btn grow" href="{esc(maps_dir(home["q"]))}" target="_blank" rel="noopener">{SVG["nav"]}導航到巷口</a></div>
    <p class="demo">只給到巷口，下車後步行。完整地址看 Airbnb App，網頁不放。</p>
  </article>
  <h2 class="sec-title">大麻紅線</h2>
  <ol class="rules">{rules}</ol>
  <h2 class="sec-title">錢、交通、帶回台灣</h2>
  {infos}
</section>

<p class="stamp">更新於 {stamp}（曼谷時間）· <span id="sw-state">單檔可離線</span></p>
</main>

<nav class="tabbar" role="tablist" aria-label="主要分頁"><div class="wrap">{tabbar}</div></nav>

<dialog class="show" id="show" aria-label="給對方看">
  <div class="show-in">
    <div class="lab"><span id="sh-lab">กรุณาพาไปที่นี่ · 請帶我到這裡</span><button type="button" id="sh-x">關閉</button></div>
    <div class="show-main"><p class="big" lang="th" id="sh-th"></p><p class="mid" id="sh-en"></p><p class="small" id="sh-zh"></p></div>
    <div class="foot"><a id="sh-map" href="#" target="_blank" rel="noopener">開地圖</a><button type="button" class="ghost" id="sh-copy">複製</button></div>
  </div>
</dialog>

<dialog class="sheet" id="spend-dlg" aria-label="記一筆花費">
  <form method="dialog" id="spend-form">
    <h2>記一筆（兩人合計）</h2>
    <label>金額（฿）<input inputmode="decimal" id="sp-amt" autocomplete="off" placeholder="例如 450" required></label>
    <div class="catpick" role="radiogroup" aria-label="分類">{"".join(f'<label><input type="radio" name="sp-cat" value="{esc(k)}"{" checked" if k == "餐飲" else ""}><span>{esc(k)}</span></label>' for k in bcat_opts)}</div>
    <label>哪一天<select id="sp-day">{"".join(f'<option value="{d["id"]}">D{i + 1} {d["date"].month}/{d["date"].day}</option>' for i, d in enumerate(days))}</select></label>
    <label>備註<input type="text" id="sp-note" autocomplete="off" placeholder="例如 Here Hai"></label>
    <div class="btns"><button class="btn grow" value="cancel" type="button" id="sp-cancel">取消</button><button class="btn primary grow" value="ok" id="sp-ok">存檔</button></div>
  </form>
</dialog>

<script id="boot" type="application/json">{boot_json}</script>
<script>
{js}
</script>
</body>
</html>
'''
    # 結構檢查
    for tag in ("section", "dialog", "details", "ol", "ul", "article"):
        o, c = len(re.findall(rf"<{tag}[\s>]", page)), page.count(f"</{tag}>")
        if o != c:
            fail(f"<{tag}> 開 {o} 關 {c}，HTML 結構壞了")
    guard(page, "產出的 index.html", private)

    sw = SW_TMPL.replace("{{VER}}", ver)
    guard(sw, "sw.js", private)

    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(page, encoding="utf-8")
    tmp.replace(OUT)
    SW.write_text(sw, encoding="utf-8")

    total = sum(sum(d["spend"].values()) for d in days) + meta["reserve_thb"]
    nstops = sum(len(d["stop"]) for d in days)
    print(f"✓ index.html {len(page.encode()) / 1024:.0f} KB · {len(days)} 天 {nstops} 站 · {len(order)} 地點 · {nphr} 句泰語 · "
          f"計畫 {thb(total)} / 預算 {thb(meta['budget_twd'] * rate)} · 版本 {ver}")


SW_TMPL = """// 離線：導覽請求 network-first（有網路一律拿最新版），斷線才回快取。版本 {{VER}}
const C = 'bkk-{{VER}}';
self.addEventListener('install', e => { self.skipWaiting(); e.waitUntil(caches.open(C).then(c => c.add('./')).catch(() => {})); });
self.addEventListener('activate', e => e.waitUntil(
  caches.keys().then(ks => Promise.all(ks.filter(k => k !== C).map(k => caches.delete(k)))).then(() => self.clients.claim())
));
self.addEventListener('fetch', e => {
  if (e.request.mode !== 'navigate') return;
  e.respondWith(
    fetch(e.request, { cache: 'no-store' })
      .then(r => { if (r.ok) { const cp = r.clone(); caches.open(C).then(c => c.put('./', cp)); } return r; })
      .catch(() => caches.match('./').then(r => r || new Response('離線中，且沒有快取的版本。', { status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8' } })))
  );
});
"""

if __name__ == "__main__":
    build()
