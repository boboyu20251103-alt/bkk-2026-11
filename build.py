#!/usr/bin/env python3
"""曼谷行程 2026-11：行程.toml → index.html（單檔，CSS+少量 JS 內嵌）

只用標準庫。有錯就 exit 1，不產出半套。
憑證（PNR／確認碼／機票號／卡號）不進這條管線——它們只留在 vault 的 01。
"""

import html
import sys
import tomllib
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOML = ROOT.parent / "曼谷行程-2026-11" / "行程.toml"
LANG = ROOT.parent / "曼谷行程-2026-11" / "lang.toml"
PREP = ROOT.parent / "曼谷行程-2026-11" / "prep.toml"
OUT = ROOT / "index.html"

CATS = ["大麻", "餐廳", "酒吧", "按摩", "購物", "景點", "交通", "住宿", "其他"]
PAYS = ["免", "現金", "信用卡", "兩者", "未查"]
RESERVES = ["免預約", "現場購票", "需預約", "已訂"]
WD = "一二三四五六日"


def fail(msg):
    print(f"✗ build 失敗：{msg}", file=sys.stderr)
    sys.exit(1)


def minutes(t):
    """'10:50' → 650；'約 00:30'/'~12:15' → 解析出數字；'睡飽' → None（排最後）"""
    digits = "".join(ch for ch in t if ch.isdigit() or ch == ":")
    if ":" not in digits:
        return None
    h, _, m = digits.partition(":")
    try:
        v = int(h) * 60 + int(m or 0)
    except ValueError:
        return None
    return v + (1440 if v < 5 * 60 else 0)  # 宵夜 00:30 排當天最後


def esc(s):
    return html.escape(str(s), quote=True)


def load():
    if not TOML.exists():
        fail(f"找不到 {TOML}")
    try:
        data = tomllib.loads(TOML.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        fail(f"TOML 語法錯誤：{e}")

    meta = data.get("meta") or fail("缺 [meta]")
    if meta.get("schema") != 1:
        fail(f"meta.schema = {meta.get('schema')!r}，build.py 只認 1")
    for k in ("title", "start"):
        if k not in meta:
            fail(f"[meta] 缺 {k}")

    days = data.get("day", [])
    places = {p["id"]: p for p in data.get("place", []) if "id" in p}
    if len(places) != len(data.get("place", [])):
        fail("[[place]] 有缺 id 或 id 重複")

    seen = set()
    for d in days:
        did = d.get("id")
        if did in seen:
            fail(f"day.id 重複：{did}")
        seen.add(did)
        for k in ("date", "theme", "stop"):
            if k not in d:
                fail(f"[{did}] 缺 {k}")
        if not d["stop"]:
            fail(f"[{did}] 沒有任何 stop")
        for s in d["stop"]:
            for k in ("time", "icon", "name", "what"):
                if k not in s:
                    fail(f"[{did}] 有一站缺 {k}：{s}")
            pid = s.get("place")
            if pid and pid not in places:
                fail(f"[{did}] stop.place = {pid!r} 沒有對應的 [[place]]")
            dest = s.get("dest")
            if dest and dest not in places:
                fail(f"[{did}] stop.dest = {dest!r} 沒有對應的 [[place]]")

    for pid, p in places.items():
        for k in ("name", "icon", "cat", "reserve", "pay", "what"):
            if not p.get(k):
                fail(f"[place {pid}] 缺 {k}")
        if p["cat"] not in CATS:
            fail(f"[place {pid}] cat={p['cat']!r} 不在 {CATS}")
        if p["pay"] not in PAYS:
            fail(f"[place {pid}] pay={p['pay']!r} 不在 {PAYS}")
        if p["reserve"] not in RESERVES:
            fail(f"[place {pid}] reserve={p['reserve']!r} 不在 {RESERVES}")

    used = {s.get("place") for d in days for s in d["stop"]} - {None}
    for pid in places.keys() - used:
        print(f"⚠ 孤兒卡（沒有任何 stop 引用）：{pid}", file=sys.stderr)

    return meta, days, places, _extra(LANG, "lang"), _extra(PREP, "prep")

def _extra(path, key):
    """選用檔（lang.toml／prep.toml）：不存在就回空清單，不讓 build 掛掉。"""
    if not path.exists():
        print(f"⚠ 沒有 {path.name}，略過", file=sys.stderr)
        return []
    try:
        return tomllib.loads(path.read_text(encoding="utf-8")).get(key, [])
    except tomllib.TOMLDecodeError as e:
        fail(f"{path.name} 語法錯誤：{e}")


# ── 渲染 ───────────────────────────────────────────
def day_label(d):
    dt = d["date"]
    return f"{dt.month}/{dt.day}（{WD[dt.weekday()]}）"


def map_href(p):
    """優先用坐標，沒坐標用英文地址；都沒有 → None"""
    if p.get("geo"):
        return f'https://www.google.com/maps/search/?api=1&query={esc(p["geo"])}'
    if p.get("addr"):
        from urllib.parse import quote
        return f'https://www.google.com/maps/search/?api=1&query={quote(p["addr"])}'
    return None

def render_stop(s, places):
    pid = s.get("place")
    card = places.get(pid) if pid else None
    dest_pid = s.get("dest")
    dest = places.get(dest_pid) if dest_pid else None
    badges = []
    if card:
        badges.append(f'<a class="star" href="#place-{esc(pid)}" data-place="{esc(pid)}" aria-label="看完整介紹">★</a>')
        if card["pay"] == "現金":
            badges.append("💵")
    elif s.get("cash"):
        badges.append("💵")
    if s.get("cost_thb"):
        note = f"（{esc(s['cost_note'])}）" if s.get("cost_note") else ""
        badges.append(f'<span class="cost">฿{s["cost_thb"]:,}{note}</span>')

    name = esc(s["name"])
    if card:
        name = f'<a href="#place-{esc(pid)}" data-place="{esc(pid)}">{name}</a>'
    # 🚕 搭車：目的地有卡片就同樣開彈窗（地址／地圖都在卡片裡），不再另外展開
    elif s["icon"] == "🚕" and dest:
        name = f'<a href="#place-{esc(dest_pid)}" data-place="{esc(dest_pid)}">{name}</a>'

    # watch：這家店有注意事項 → 標題旁一個 ❗，點開卡片才看細節
    if card and card.get("watch"):
        badges.append(f'<a class="warnmark" href="#place-{esc(pid)}" data-place="{esc(pid)}" aria-label="有注意事項">❗</a>')

    return f"""      <li class="stop">
        <div class="t">{esc(s['time'])}</div>
        <div class="body">
          <p class="nm"><span class="ico">{esc(s['icon'])}</span>{name} {' '.join(badges)}</p>
          <p class="what">{esc(s['what'])}</p>
          {f'<p class="next">{esc(s["next"])}</p>' if s.get('next') else ''}
        </div>
      </li>"""


def render_day(d, places):
    iso = d["date"].isoformat()
    warns = "".join(f"<li>{esc(w)}</li>" for w in d.get("warn", []))
    pack = " · ".join(esc(x) for x in d.get("pack", []))
    backups = "".join(
        f"<li><b>{esc(b['cond'])}</b> → {esc(b['act'])}</li>" for b in d.get("backup", [])
    )
    stops = sorted(d["stop"], key=lambda s: (minutes(s["time"]) is None, minutes(s["time"]) or 0))
    return f"""  <details class="day" data-date="{iso}">
    <summary><span class="dlabel">{esc(d['id'])}</span> {esc(day_label(d))}<br><small>{esc(d['theme'])}</small></summary>
    <p class="area">{esc(d.get('area',''))}</p>
    {f'<ul class="warn">{warns}</ul>' if warns else ''}
    {f'<p class="pack">🎒 出門前：{pack}</p>' if pack else ''}
    <ol class="timeline">
{chr(10).join(render_stop(s, places) for s in stops)}
    </ol>
    {f'<details class="sub"><summary>備案</summary><ul>{backups}</ul></details>' if backups else ''}
    {f'<details class="sub"><summary>下雨怎麼辦</summary><p>{esc(d["rain"])}</p></details>' if d.get('rain') else ''}
  </details>"""


def render_place(p):
    # watch：特別注意事項，最顯眼（紅框）
    watch = ""
    if p.get("watch"):
        items = p["watch"] if isinstance(p["watch"], list) else [p["watch"]]
        watch = '<ul class="watch">' + "".join(f"<li>{esc(x)}</li>" for x in items) + "</ul>"
    sections = [
        ("點什麼", "order"),
        ("先知道", "know"),
        ("資訊", "info"),
    ]
    def blk(label, f):
        val = p.get(f)
        if not val:
            return ""
        # 資訊欄常用「｜」分段，在手機上換行後｜會落到行首 → 拆成一條一行
        parts = [x.strip() for x in val.split("｜") if x.strip()]
        if len(parts) > 1:
            body = "<ul>" + "".join(f"<li>{esc(x)}</li>" for x in parts) + "</ul>"
        else:
            body = f"<p>{esc(val)}</p>"
        return f'<section class="blk"><h4>{esc(label)}</h4>{body}</section>'
    blocks = "".join(blk(label, f) for label, f in sections)
    # 地址與地圖：卡片本身就帶，彈窗與「地點」頁都看得到
    addrbits = []
    if p.get("addr"):
        addrbits.append(f'<p class="addr-en">{esc(p["addr"])}</p>')
    mh = map_href(p)
    if mh:
        addrbits.append(f'<a class="btn-map" href="{mh}" target="_blank" rel="noopener">📍 開地圖</a>')
    addr = f'<section class="blk addr"><h4>地址</h4>{"".join(addrbits)}</section>' if addrbits else ""
    empty = '' if (blocks or addr) else '<p class="empty">― 內容待補 ―</p>'
    tags = " ".join(
        f'<span class="tag">{esc(x)}</span>'
        for x in (p['cat'], p['reserve'], p['pay']) if x
    )
    return f"""  <article class="place" id="place-{esc(p['id'])}">
    <header class="ph"><div class="icw">{esc(p['icon'])}</div>
      <div><h3>{esc(p['name'])}</h3><p class="tagrow">{tags}</p></div></header>
    <p class="what">{esc(p['what'])}</p>
    {watch}
    {blocks}{addr}{empty}
  </article>"""


def render_lang(lang):
    # 第一節「最常用」預設展開，其他收起：手機上要先看到最常用的那幾句
    """泰語對照表：每節一個 details，表格三欄（中文／英文／泰文＋拼音）。"""
    out = []
    for i, s in enumerate(lang):
        rs = s.get("rows", [])
        # 整節都沒有泰文（例如「買花」）就不要留一個空欄，表格會看起來像壞掉
        has_th = any(r.get("th", "").strip() for r in rs)
        def _t(v):
            # lang.toml 會有 markdown 的 ** 強調，直接上頁會變字面星號
            return esc(str(v or "").replace("**", ""))
        def row(r):
            cells = (f'<td class="lz">{_t(r.get("zh"))}</td>'
                     f'<td class="le">{_t(r.get("en"))}</td>')
            if has_th:
                cells += ('<td class="lt">{}{}</td>'.format(
                    _t(r.get("th")),
                    f'<i class="ro">{esc(r["roman"])}</i>' if r.get("roman") else ""))
            return f"<tr>{cells}</tr>"
        rows = "".join(row(r) for r in rs)
        head = "<th>中文</th><th>英文（亮給對方）</th>" + ("<th>泰文</th>" if has_th else "")
        note = f'<p class="lnote">{esc(s["note"])}</p>' if s.get("note") else ""
        out.append(
            f'<details class="lsec"{" open" if i == 0 else ""}><summary>{esc(s["sec"])}</summary>{note}'
            f'<table class="ltbl"><thead><tr>{head}</tr></thead>'
            f'<tbody>{rows}</tbody></table></details>'
        )
    return "\n".join(out)

def render_prep(prep):
    out = []
    for b in prep:
        rows = "".join(f"<li>{esc(x)}</li>" for x in b.get("rows", []))
        lead = f'<p class="plead">{esc(b["lead"])}</p>' if b.get("lead") else ""
        out.append(f'<section class="pblk"><h3>{esc(b["title"])}</h3>{lead}<ul>{rows}</ul></section>')
    return "\n".join(out)

def build_html(meta, days, places, lang, prep, stamp):
    by_cat = {c: [p for p in places.values() if p["cat"] == c] for c in CATS}
    place_blocks = "\n".join(
        f'<section class="catblock"><h2 id="cat-{esc(c)}">{esc(c)}</h2>\n'
        + "\n".join(render_place(p) for p in ps)
        + "</section>"
        for c, ps in by_cat.items()
        if ps
    )
    cats_present = [c for c in CATS if by_cat[c]]
    place_nav = (
        '<nav class="chipbar">'
        + "".join(f'<a class="chip" href="#cat-{esc(c)}">{esc(c)}<b>{len(by_cat[c])}</b></a>'
                  for c in cats_present)
        + "</nav>"
    ) if len(cats_present) > 1 else ""
    day_blocks = "\n".join(render_day(d, places) for d in days)
    out_items = "".join(f"<li>{esc(x)}</li>" for x in meta.get("out", []))
    lang_blocks = render_lang(lang)
    prep_blocks = render_prep(prep)
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>曼谷 2026-11 行程</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Ctext y='14' font-size='14'%3E%F0%9F%8C%BF%3C/text%3E%3C/svg%3E">
<meta name="theme-color" content="#f6f5f2" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#141317" media="(prefers-color-scheme: dark)">
<style>
:root {{
  --bg:#f6f5f2; --fg:#1b1a18; --dim:#5c5852; --mute:#7a746c;
  --line:#e5e1d9; --soft:#efece6; --card:#fff;
  --accent:#a85a2f; --on-accent:#fff;
  --warn:#b94a2f; --warnbg:#fdeee7; --warnln:#f0b89f;
  --radius:12px;
}}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#141317; --fg:#ece9e3;
           --line:#2b2830; --soft:#1c1a1f; --card:#1f1d23;
           --dim:#b0aaa1; --mute:#948d84;
           --accent:#e49268; --on-accent:#1a110a;
           --warn:#f0a083; --warnbg:#2d1d17; --warnln:#8a4a30;
           color-scheme: dark; }}
}}
* {{ box-sizing:border-box; }}
html {{ -webkit-text-size-adjust:100%; text-size-adjust:100%; }}
body {{ margin:0; background:var(--bg); color:var(--fg);
  font:16px/1.6 system-ui,-apple-system,"Noto Sans TC","PingFang TC",sans-serif;
  padding-left:max(16px,env(safe-area-inset-left,0px));
  padding-right:max(16px,env(safe-area-inset-right,0px));
  padding-block:0 40px; max-width:720px; margin-inline:auto; }}
h1 {{ font-size:1.35rem; margin:20px 0 2px; }}
h2 {{ font-size:1.05rem; margin:22px 0 8px; }}
h3 {{ font-size:1rem; margin:0 0 4px; }}
.sub2,.dim {{ color:var(--dim); font-size:.85rem; }}
.stamp {{ color:var(--dim); font-size:.75rem; margin:0 0 12px; }}
nav {{ display:flex; gap:6px; position:sticky; top:0; z-index:5;
  background:var(--bg); padding-block:8px; border-bottom:1px solid var(--line);
  margin-inline:calc(-1 * max(16px,env(safe-area-inset-left,0px)));
  padding-inline:max(16px,env(safe-area-inset-left,0px)); }}
nav button {{ flex:1; padding:11px 4px; font:inherit; font-size:.9rem; font-weight:500; cursor:pointer;
  background:transparent; color:var(--dim); border:0; border-bottom:2px solid transparent;
  min-height:44px; }}
nav button[aria-selected="true"] {{ color:var(--accent); border-bottom-color:var(--accent); font-weight:600; }}
section[hidden] {{ display:none; }}
details {{ background:var(--card); border:1px solid var(--line); border-radius:var(--radius);
  padding:12px 14px; margin:12px 0; }}
summary {{ cursor:pointer; font-weight:600; list-style:none;
  padding:4px 0; min-height:32px; display:flex; align-items:center; }}
summary::-webkit-details-marker {{ display:none; }}
summary::before {{ content:"▸"; color:var(--mute); display:inline-block; width:18px;
  font-size:.9em; }}
details[open] > summary::before {{ transform:rotate(90deg); }}
.dlabel {{ color:var(--accent); letter-spacing:.02em; margin-right:.34em; }}
.area {{ color:var(--dim); font-size:.85rem; margin:8px 0; }}
ul.warn {{ background:var(--warnbg); border-left:3px solid var(--warn); border-radius:6px;
  list-style:none; padding:10px 12px 10px 14px; margin:10px 0; font-size:.9rem; color:var(--fg);
  text-wrap:pretty; }}
ul.warn li {{ padding:2px 0; text-wrap:balance; }}
ul.warn li::before {{ content:"⚠ "; color:var(--warn); margin-right:4px; }}
.pack {{ font-size:.86rem; background:var(--soft); border-radius:8px; padding:8px 12px;
  color:var(--dim); }}
ol.timeline {{ list-style:none; padding:0; margin:10px 0 0; }}
li.stop {{ display:grid; grid-template-columns:52px 1fr; gap:14px; padding:0 0 18px;
  position:relative; min-width:0; align-items:start; }}
/* 貫穿的軸線 */
li.stop::before {{ content:""; position:absolute; left:60px; top:20px; bottom:0;
  width:2px; background:var(--line); pointer-events:none; }}
li.stop:last-child::before {{ display:none; }}
/* 節點：實心圓，對齊首行 */
li.stop::after {{ content:""; position:absolute; left:56px; top:7px; width:10px; height:10px;
  border-radius:50%; background:var(--accent); pointer-events:none; }}
.t {{ font-variant-numeric:tabular-nums; font-weight:600; font-size:.86rem; color:var(--dim);
  padding-top:1px; text-align:right; }}
.body {{ padding-left:6px; min-width:0; }}
.body p {{ margin:0; }}
.nm {{ font-weight:600; font-size:.98rem; line-height:1.5; text-wrap:balance; }}
.nm a {{ color:var(--fg); text-decoration:underline dashed var(--line); text-underline-offset:3px;
  text-decoration-thickness:1px; text-decoration-skip-ink:auto; }}
.nm > * + * {{ margin-left:6px; }}
.what {{ font-size:.9rem; color:var(--dim); margin-top:5px !important; line-height:1.55; }}
.next {{ font-size:.82rem; color:var(--mute); margin-top:5px !important; }}
.star {{ text-decoration:none; color:var(--accent); font-size:.9rem;
  display:inline-flex; align-items:center; justify-content:center;
  min-width:28px; min-height:28px; margin:-4px 0; }}
.warnmark {{ text-decoration:none; font-size:.8rem; line-height:1;
  background:var(--warnbg); border:1px solid var(--warnln); border-radius:6px;
  display:inline-flex; align-items:center; justify-content:center;
  min-width:28px; min-height:28px; margin:-4px 0; }}
.cost {{ color:var(--accent); font-size:.78rem; font-weight:600; }}
.ico {{ margin-right:2px; }}
details.sub {{ background:transparent; border:0; padding:0; margin:8px 0 0 62px; }}
details.sub summary {{ font-weight:400; font-size:.9rem; color:var(--dim);
  padding:6px 0; min-height:36px; }}
.addr-en {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.86rem;
  margin:0 0 8px; padding:8px 10px; background:var(--soft); border-radius:8px;
  line-height:1.5; word-break:break-word; user-select:all; -webkit-user-select:all; }}
.btn-map {{ display:inline-flex; align-items:center; justify-content:center;
  min-height:44px; padding:10px 18px; border-radius:10px; font-size:.9rem;
  font-weight:600; text-decoration:none; background:var(--accent);
  color:var(--on-accent); }}
.to {{ color:var(--dim); font-size:.8rem; font-weight:400; }}
.place {{ background:var(--card); border:1px solid var(--line); border-radius:var(--radius);
  padding:14px 16px; margin:12px 0; scroll-margin-top:64px; }}
.place .ph {{ display:flex; gap:12px; align-items:flex-start; margin-bottom:8px; }}
.place .icw {{ font-size:1.6rem; line-height:1; flex-shrink:0;
  background:var(--soft); width:44px; height:44px; border-radius:12px;
  display:flex; align-items:center; justify-content:center; }}
.place h3 {{ font-size:1.05rem; margin:2px 0 4px; }}
.place .tagrow {{ margin:0; display:flex; flex-wrap:wrap; gap:4px; }}
.place .tag {{ font-size:.72rem; color:var(--dim); background:var(--soft);
  padding:2px 8px; border-radius:999px; }}
.place .what {{ font-size:.92rem; color:var(--fg); margin:8px 0; line-height:1.6; }}
.place .blk {{ margin-top:12px; padding-top:10px; border-top:1px solid var(--line); }}
.place .blk h4 {{ font-size:.75rem; margin:0 0 4px; color:var(--mute);
  letter-spacing:.1em; text-transform:none; font-weight:600; }}
.place .blk p {{ font-size:.9rem; margin:0; line-height:1.65; }}
/* info 裡的「｜」在手機上會落到行首，改成一條一行的清單 */
.place .blk ul {{ margin:0; padding-left:16px; font-size:.9rem; line-height:1.6; }}
.place .blk ul li {{ margin:2px 0; }}
.empty {{ color:var(--mute); font-size:.82rem; text-align:center; margin:14px 0 4px; }}
ul.watch {{ list-style:none; padding:10px 12px 10px 14px; margin:10px 0;
  background:var(--warnbg); border-left:3px solid var(--warn); border-radius:6px;
  font-size:.88rem; }}
ul.watch li {{ padding:2px 0; }}
ul.watch li::before {{ content:"❗ "; color:var(--warn); margin-right:2px; }}
ul.watch.sm {{ margin:6px 0 0; padding:6px 10px 6px 12px; font-size:.84rem; }}
ul {{ padding-left:20px; }}
.catblock h2 {{ font-size:.78rem; color:var(--mute); letter-spacing:.1em;
  text-transform:none; margin:20px 0 6px; padding:0 2px; font-weight:600;
  scroll-margin-top:64px; }}
/* 地點分頁：7 個分類的快速跳轉 */
.chipbar {{ display:flex; flex-wrap:wrap; gap:6px; margin:14px 0 2px; }}
.chip {{ font-size:.82rem; padding:7px 12px; border:1px solid var(--line);
  border-radius:999px; color:var(--dim); text-decoration:none; background:var(--card);
  display:inline-flex; align-items:center; gap:5px; min-height:34px; }}
.chip b {{ color:var(--mute); font-weight:500; font-size:.76rem; }}
@media print {{ details {{ break-inside:avoid; }} details:not([open]) > *:not(summary) {{ display:block; }} }}
dialog#place-dlg {{ max-width:min(560px,94vw); width:94vw; border:0; border-radius:14px;
  background:var(--card); color:var(--fg); padding:22px 20px 18px;
  font-size:1rem; max-height:86vh; overflow:auto;
  overscroll-behavior:contain; }}
dialog#place-dlg::backdrop {{ background:rgba(0,0,0,.66); }}
.dlg-x {{ position:absolute; top:10px; right:10px; width:40px; height:40px;
  display:flex; align-items:center; justify-content:center; border:0; border-radius:50%;
  background:var(--soft); color:var(--dim); font-size:1.1rem; line-height:1; cursor:pointer;
  z-index:2; }}
.dlg-x:active {{ background:var(--line); }}
dialog#place-dlg article {{ margin:0; padding:0; border:0; background:transparent; }}
dialog#place-dlg article .ph {{ display:flex; gap:12px; align-items:center;
  margin-bottom:10px; padding-bottom:10px; border-bottom:1px solid var(--line); }}
dialog#place-dlg article h3 {{ margin:0; font-size:1.15rem; }}
dialog#place-dlg article .what {{ font-size:.95rem; line-height:1.65; }}
dialog#place-dlg article .blk h4 {{ font-size:.78rem; }}
dialog#place-dlg article .blk p {{ font-size:.95rem; line-height:1.75; }}
dialog#place-dlg article .tag {{ font-size:.76rem; }}
.dlg-close {{ margin-top:20px; }}.dlg-close button {{ width:100%; padding:13px 24px; border-radius:12px; border:0;
  background:var(--accent); color:var(--on-accent); font-weight:600; font-size:1rem;
  cursor:pointer; min-height:48px; }}
.dlg-close button:focus {{ outline:none; }}
.dlg-close button:focus-visible {{ box-shadow:0 0 0 3px var(--accent); outline:2px solid var(--bg); }}
/* 準備 */
.outlist {{ margin:0 0 8px; padding-left:20px; font-size:.9rem; line-height:1.7; }}
.pblk {{ background:var(--card); border:1px solid var(--line); border-radius:var(--radius);
  padding:12px 16px; margin:12px 0; }}
.pblk h3 {{ font-size:.98rem; margin:0 0 4px; color:var(--accent); }}
.plead {{ font-size:.86rem; color:var(--dim); margin:0 0 6px; line-height:1.6; }}
.pblk ul {{ margin:0; padding-left:20px; font-size:.9rem; line-height:1.7; }}
.pblk li {{ margin:3px 0; }}
/* 泰語 */
details.lsec {{ padding:10px 12px; }}
.lnote {{ font-size:.84rem; color:var(--dim); margin:6px 0; line-height:1.6;
  background:var(--soft); border-radius:8px; padding:6px 10px; }}
.ltbl {{ width:100%; border-collapse:collapse; margin-top:6px; font-size:.86rem; }}
.ltbl th {{ text-align:left; font-size:.72rem; color:var(--mute); font-weight:600;
  padding:4px 6px 6px; border-bottom:1px solid var(--line); }}
.ltbl td {{ padding:7px 6px; border-bottom:1px solid var(--soft); vertical-align:top;
  line-height:1.5; }}
.ltbl tr:last-child td {{ border-bottom:0; }}
.ltbl .lz {{ width:30%; color:var(--dim); }}
.ltbl .le {{ width:37%; font-weight:600; font-size:.98rem; }}
.ltbl .lt {{ width:33%; }}
.ltbl th:last-child:nth-child(2),.ltbl td:last-child:nth-child(2) {{ width:70%; }}
.ltbl .ro {{ display:block; font-style:normal; font-size:.74rem; color:var(--mute); margin-top:3px; }}
</style>
</head>
<body>

<h1>{esc(meta['title'])}</h1>
<p class="sub2">{esc(meta.get('subtitle',''))}</p>
<p class="stamp">建置 {esc(stamp)}</p>

<nav role="tablist">
  <button role="tab" data-view="today" aria-selected="true">今日</button>
  <button role="tab" data-view="days" aria-selected="false">行程</button>
  <button role="tab" data-view="places" aria-selected="false">地點</button>
  <button role="tab" data-view="prep" aria-selected="false">準備</button>
  <button role="tab" data-view="lang" aria-selected="false">泰語</button>
</nav>

<section id="view-today"><p id="today-note" class="dim" hidden></p><div id="today-days">
{day_blocks}
</div></section>
<section id="view-days" hidden><div id="all-days"></div></section>
<section id="view-places" hidden>
{place_nav}
{place_blocks}
</section>
<section id="view-prep" hidden>
  <h2>每天出門前</h2>
  <ul class="outlist">{out_items}</ul>
{prep_blocks}
</section>
<section id="view-lang" hidden>
  <p class="dim">把手機螢幕亮給對方看英文那行。男生說 ครับ（khrap），女生說 ค่ะ（kha）。</p>
{lang_blocks}
</section>

<dialog id="place-dlg"><button class="dlg-x" aria-label="關閉">✕</button>
<article id="place-dlg-body"></article>
<form method="dialog" class="dlg-close"><button>關閉</button></form></dialog>

<script>
// 靜態 HTML 已含全部日期卡；這裡只把「不是今天」的搬到「行程」分頁。
// 沒有 JS 時：「今日」顯示全部日期（仍然可讀），分頁切換失效但內容都在。
const cards = [...document.querySelectorAll('#today-days details.day')];
const todayISO = new Date().toLocaleDateString('en-CA', {{timeZone:'Asia/Bangkok'}});
const hit = cards.find(d => d.dataset.date === todayISO);
const pick = hit || cards.filter(d => d.dataset.date < todayISO).pop() || cards[0];
if (pick) {{
  cards.filter(d => d !== pick).forEach(d => document.getElementById('all-days').append(d));
  pick.open = true;
  if (!hit) {{
    const n = document.getElementById('today-note');
    n.textContent = '今天不在旅程期間，先看 ' + pick.querySelector('.dlabel').textContent + '。';
    n.hidden = false;
  }}
}}
function showView(v) {{
  document.querySelectorAll('button[role=tab]').forEach(x => x.setAttribute('aria-selected', x.dataset.view === v));
  ['today','days','places','prep','lang'].forEach(k => document.getElementById('view-' + k).hidden = k !== v);
}}
document.querySelectorAll('button[role=tab]').forEach(b => b.onclick = () => showView(b.dataset.view));
// 時間軸的 ★ 或店名 → 彈窗顯示地點卡（不切頁）
const dlg = document.getElementById('place-dlg');
const dlgBody = document.getElementById('place-dlg-body');
document.querySelectorAll('a[data-place]').forEach(a => a.onclick = e => {{
  e.preventDefault();
  const src = document.getElementById('place-' + a.dataset.place);
  if (!src) return;
  dlgBody.innerHTML = src.innerHTML;
  dlg.showModal();
  // 點 ❗ 進來的，直接把紅色那段滾到看得見的位置
  if (a.classList.contains('warnmark')) {{
    const w = dlgBody.querySelector('.watch');
    if (w) dlg.scrollTop = w.getBoundingClientRect().top
      - dlg.getBoundingClientRect().top + dlg.scrollTop - 12;
  }} else {{
    dlg.scrollTop = 0;
  }}
}});
dlg.addEventListener('click', e => {{ if (e.target === dlg) dlg.close(); }});
dlg.querySelector('.dlg-x').onclick = () => dlg.close();
</script>
</body>
</html>
"""


def main():
    meta, days, places, lang, prep = load()
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    OUT.write_text(build_html(meta, days, places, lang, prep, stamp), encoding="utf-8")
    kb = OUT.stat().st_size / 1024
    stops = sum(len(d["stop"]) for d in days)
    nrows = sum(len(s.get("rows", [])) for s in lang)
    print(f"✓ build ok · {len(days)} 天 / {stops} 站 / {len(places)} 卡 · "
          f"{len(prep)} 準備節 / {len(lang)} 泰語節（{nrows} 句） · {kb:.0f} KB · 建置於 {stamp}")


if __name__ == "__main__":
    main()
