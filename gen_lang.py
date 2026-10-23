# -*- coding: utf-8 -*-
"""06-泰語對照表.md → lang.toml（腳本產生，不打字）"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent

SRC = ROOT.parent / '曼谷行程-2026-11' / '06-泰語對照表.md'
DST = ROOT.parent / '曼谷行程-2026-11' / 'lang.toml'

# (原文標題前綴, 顯示名, 欄位, 要不要排除子區)
SECS = [
    ('一、最常用',              '最常用',            ['zh', 'en', 'th', 'roman'], None),
    ('二、取得處方',            '取得處方 PT33（診所）', ['zh', 'en', 'th'],  None),
    ('三、買花與食用型',        '買花（D1／D4）',      ['zh', 'en'],        {'B'}),
    ('四、餐廳與海鮮',          '餐廳與海鮮',         ['zh', 'en', 'th'],  None),
    ('四之二、南部泰菜',        '南部泰菜（D3 備案 Jaan）', ['zh', 'en', 'th', 'roman'], None),
    ('四之三、老城街頭小吃',    '老城街頭小吃（D2）',   ['zh', 'en', 'th', 'roman'], None),
    ('四之四、宵夜與深夜點餐',  '宵夜與深夜點餐',      ['zh', 'en', 'th', 'roman'], None),
    ('五、叫車與交通',          '叫車與交通',         ['zh', 'en', 'th'],  None),
    ('六、按摩與 SPA',          '按摩與 SPA',         ['zh', 'en', 'th'],  None),
    ('七、酒吧與夜生活',        '酒吧與夜生活',       ['zh', 'en'],        None),
    ('七之二、中國城酒吧',      '中國城酒吧（D2）',    ['zh', 'en', 'th', 'roman'], None),
    ('七之三、酒吧與 Sing Sing', '酒吧與 Sing Sing',    ['zh', 'en', 'th', 'roman'], None),
    ('八、購物與退稅',          '購物與退稅',         ['zh', 'en'],        None),
    ('九、遇到問題',            '遇到問題',           ['zh', 'en', 'th'],  None),
    ('十、住宿',                '住宿',              ['zh', 'en'],        None),
    ('十一、泰拳與購物',        '泰拳與購物（B 計畫）', ['zh', 'en', 'th', 'roman'], None),
]

def toml_str(s):
    s = re.sub(r'[\x00-\x1f]', ' ', s.strip())
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

def cells(line):
    return [c.strip() for c in line.strip().strip('|').split('|')]

text = open(SRC, encoding='utf-8').read()
parts = re.split(r'(?m)^## (.+)$', text)
sections = {}
for i in range(1, len(parts), 2):
    sections[parts[i].strip()] = parts[i + 1]

NOTES = {
    '最常用': '一次秀完的自我介紹：We are tourists from Taiwan. Our English is limited. Please speak slowly or type it out for us. Thank you.',
    '取得處方 PT33（診所）': '醫師可以拒絕開方。有服藥、心血管或精神病史要老實說，這會影響能不能開方。',
    '買花（D1／D4）': '品種只是參考，店內不一定有，THC% 要現場問。',
    '餐廳與海鮮': '海鮮按重量計價，點之前一定先問總價。',
    '南部泰菜（D3 備案 Jaan）': '南部菜辣度真的高；完全去辣有時做不到，真的受不了就配白飯、別點咖哩。',
    '老城街頭小吃（D2）': 'Kor Panich 只收現金；Pad Thai 付款方式未查到，都帶小鈔。',
    '宵夜與深夜點餐': '主要靠 7-Eleven 與 Grab Food。',
    '叫車與交通': '夜間一律用 Grab 或 Bolt，上車前對車牌，不在路邊喊價。',
    '按摩與 SPA': '',
    '酒吧與夜生活': '帶護照：酒吧夜店常查證件，兩人都帶（影本備用）。',
    '中國城酒吧（D2）': '⚠ 是中國城 Yaowarat 旁的 Soi Nana，不是 Sukhumvit 的 Soi Nana，跟司機講清楚。',
    '酒吧與 Sing Sing': '帶護照正本（20 歲以上）；酒類稅與服務費通常另加，結帳前確認。',
    '購物與退稅': '退稅規則見「準備」分頁的「退稅 P.P.10」。',
    '遇到問題': '緊急電話見「準備」分頁的「緊急電話」。',
    '住宿': '',
    '泰拳與購物（B 計畫）': 'B 計畫才用得到。',
}

out = []
for prefix, disp, cols, drop in SECS:
    body = next((b for t, b in sections.items() if t.startswith(prefix)), None)
    if body is None:
        print(f'⚠ 找不到節：{prefix}'); continue
    # 子區（**A. ...**）切分；drop 裡的字母整段略過
    subs = re.split(r'(?m)^\*\*([A-Z])\.', body)
    keep = []
    for i in range(1, len(subs), 2):
        if subs[i] not in (drop or set()):
            keep.append(subs[i + 1])
    bodies = keep if keep else [body]

    rows, notes = [], []
    for b in bodies:
        for line in b.splitlines():
            line = line.rstrip()
            if not line.startswith('|'):
                t = line.strip().strip('>').strip()
                if t and t != '---' and not t.startswith('#'):
                    notes.append(t)
                continue
            cs = cells(line)
            if len(cs) < len(cols):
                continue
            cs = cs[:len(cols)]
            if all(set(c) <= set('-: ') for c in cs):
                continue
            if cs[0].lower() in ('情境', '中文', '項目'):
                continue
            if all(not c or c == '—' for c in cs):
                continue
            row = {k: v for k, v in zip(cols, cs) if v and v != '—'}
            if row.get('en') or row.get('th'):
                rows.append(row)
    out.append((disp, cols, rows, notes))

with open(DST, 'w', encoding='utf-8') as f:
    f.write('# 泰語對照表 —— 由 06-泰語對照表.md 產生，不要手改\n')
    f.write('# 用法：把手機螢幕亮給對方看英文那行。男生說 ครับ（khrap），女生說 ค่ะ（kha）。\n')
    f.write('# ⚠ 自編近似發音，沒有母語者校對；念不準就亮手機。\n\n')
    for disp, cols, rows, notes in out:
        f.write(f'[[lang]]\nsec = {toml_str(disp)}\n')
        if NOTES.get(disp):
            f.write(f'note = {toml_str(NOTES[disp])}\n')
        f.write('rows = [\n')
        for r in rows:
            f.write('  { ' + ', '.join(f'{k} = {toml_str(v)}' for k, v in r.items()) + ' },\n')
        f.write(']\n\n')

total = sum(len(r) for _, _, r, _ in out)
print(f'✓ {len(out)} 節 / {total} 列')
for disp, _, rows, _ in out:
    print(f'  {disp}: {len(rows)}')
