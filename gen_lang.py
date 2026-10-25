# -*- coding: utf-8 -*-
"""06-泰語對照表.md → data/lang.toml（腳本產生，不打字）

來源：vault 的 06-泰語對照表.md（找得到才跑；找不到就保留 repo 裡現有的 data/lang.toml）。
輸出：data/lang.toml（進 repo，build.py 只讀這份）。

隱私：住宿門牌那一列一律換成巷口地標，不輸出門牌。
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DST = ROOT / 'data' / 'lang.toml'

# 依序找 vault；可用環境變數 BKK_LANG_SRC 指定
CANDIDATES = [
    os.environ.get('BKK_LANG_SRC', ''),
    str(Path.home() / 'bangkok-trip-2026' / 'omp.pi' / '06-泰語對照表.md'),
    str(ROOT.parent / 'bangkok-trip-2026' / 'omp.pi' / '06-泰語對照表.md'),
]
SRC = next((Path(p) for p in CANDIDATES if p and Path(p).is_file()), None)
if SRC is None:
    print(f'⚠ 找不到 06-泰語對照表.md（試過 {[c for c in CANDIDATES if c]}），保留現有 {DST.name}')
    sys.exit(0)

THAI = re.compile('[ก-ฺเ-๛]')
# 英數混合 6–12 碼（訂位代號、確認碼）
CODE = re.compile(r'\b(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{6,12}\b')

# (原文標題前綴, 顯示名, 欄位, 要排除的子區)
SECS = [
    ('一、最常用',              '最常用',               ['zh', 'en', 'th', 'roman'], None),
    ('二、取得處方',            '取得處方 PT33（診所）', ['zh', 'en', 'th'],          None),
    ('三、買花與食用型',        '買花與合法食品',        ['zh', 'en', 'th'],          None),
    ('四、餐廳與海鮮',          '餐廳與海鮮',           ['zh', 'en', 'th'],          None),
    ('四之二、南部泰菜',        '南部泰菜',             ['zh', 'en', 'th', 'roman'], None),
    ('四之三、老城街頭小吃',    '老城街頭小吃',          ['zh', 'en', 'th', 'roman'], None),
    ('四之四、宵夜與深夜點餐',  '宵夜與深夜點餐',        ['zh', 'en', 'th', 'roman'], None),
    ('五、叫車與交通',          '叫車與交通',           ['zh', 'en', 'th'],          None),
    ('六、按摩與 SPA',          '按摩與 SPA',           ['zh', 'en', 'th'],          None),
    ('七、酒吧與夜生活',        '酒吧與夜生活',          ['zh', 'en'],                None),
    ('七之二、中國城酒吧',      '中國城酒吧',           ['zh', 'en', 'th', 'roman'], None),
    ('七之三、酒吧與 Sing Sing', '高空酒吧與 Sing Sing',  ['zh', 'en', 'th', 'roman'], None),
    ('八、購物與退稅',          '購物與退稅',           ['zh', 'en'],                None),
    ('九、遇到問題',            '遇到問題',             ['zh', 'en', 'th'],          None),
    ('十、住宿',                '住宿',                ['zh', 'en'],                None),
    ('十一、泰拳與購物',        '泰拳與殺價（備案）',     ['zh', 'en', 'th', 'roman'], None),
]

NOTES = {
    '最常用': '一次秀完的自我介紹：We are tourists from Taiwan. Our English is limited. Please speak slowly or type it out for us. Thank you.',
    '取得處方 PT33（診所）': '醫師可以拒絕開方。有服藥、心血管或精神病史要老實說，這會影響能不能開方。',
    '買花與合法食品': '花要先有 PT33 處方。食品只買包裝上有 13 碼 อย. 登記號、每包 THC ≤ 1.6 mg 的；不要問「最強的」。',
    '餐廳與海鮮': '海鮮按重量計價，點之前一定先問總價。',
    '南部泰菜': '南部菜辣度真的高；完全去辣有時做不到。',
    '老城街頭小吃': 'Kor Panich 只收現金；Pad Thai Fai Ta Lu 付款方式未查到，都帶小鈔。',
    '宵夜與深夜點餐': '主要靠 7-Eleven 與 Grab Food。',
    '叫車與交通': '夜間一律用 Grab 或 Bolt，上車前對車牌，不在路邊喊價。',
    '酒吧與夜生活': '帶護照：酒吧夜店常查證件，兩人都帶。',
    '中國城酒吧': '⚠ Teens of Thailand 在中國城 Yaowarat 旁的 Soi Nana，不是 Sukhumvit 的 Soi Nana，跟司機講清楚。',
    '高空酒吧與 Sing Sing': '帶護照正本（20 歲以上）；酒類稅與服務費通常另加，結帳前確認。',
    '購物與退稅': '退稅規則見「救急」分頁的「錢與退稅」。',
    '遇到問題': '緊急電話見「救急」分頁。',
    '泰拳與殺價（備案）': '只有選泰拳備案時才用得到。',
}

# 住宿那列：只給巷口地標，絕不輸出門牌
HOME_ROW = {'zh': '回住宿（到巷口）', 'en': 'To Thong Lo Soi 21, near BTS Thong Lo, please.',
            'th': 'ไปทองหล่อ ซอย 21 ใกล้ BTS ทองหล่อครับ'}


def toml_str(s):
    s = re.sub(r'[\x00-\x1f]', ' ', s.strip())
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def clean(c):
    c = c.replace('**', '').replace('`', '').strip()
    return re.sub(r'\s+', ' ', c)


def cells(line):
    return [clean(c) for c in line.strip().strip('|').split('|')]


text = SRC.read_text(encoding='utf-8')
parts = re.split(r'(?m)^## (.+)$', text)
sections = {parts[i].strip(): parts[i + 1] for i in range(1, len(parts), 2)}

out = []
for prefix, disp, cols, drop in SECS:
    body = next((b for t, b in sections.items() if t.startswith(prefix)), None)
    if body is None:
        print(f'⚠ 找不到節：{prefix}')
        continue
    subs = re.split(r'(?m)^\*\*([A-Z])\.', body)
    bodies = [subs[i + 1] for i in range(1, len(subs), 2) if subs[i] not in (drop or set())] or [body]

    rows = []
    for b in bodies:
        for line in b.splitlines():
            line = line.rstrip()
            if not line.startswith('|') or '~~' in line:
                continue
            cs = cells(line)
            if len(cs) < 2:
                continue
            cs = (cs + [''] * len(cols))[:len(cols)]
            if all(set(c) <= set('-: ') for c in cs):
                continue
            if cs[0].lower() in ('情境', '中文', '項目', 'english'):
                continue
            row = {k: v for k, v in zip(cols, cs) if v and v != '—'}
            # 第三欄有時是中文說明而不是泰文：沒有泰文字就丟掉
            if 'th' in row and not THAI.search(row['th']):
                row.pop('th')
            if 'roman' in row and THAI.search(row['roman']):
                row.pop('roman')
            if not (row.get('en') or row.get('th')):
                continue
            joined = ' '.join(row.values())
            if re.search(r'\d+/\d+\s*Thong', joined) or row.get('zh') == '回住宿':
                row = dict(HOME_ROW)
            elif CODE.search(joined) or re.search(r'booking number|confirmation|door code is', joined, re.I):
                print(f'⚠ 略過含訂單／密碼的列（隱私）：{row.get("zh", "")}')
                continue
            rows.append(row)
    out.append((disp, rows))

DST.parent.mkdir(exist_ok=True)
with open(DST, 'w', encoding='utf-8') as f:
    f.write('# 泰語對照表 —— 由 gen_lang.py 從 vault 06-泰語對照表.md 產生，不要手改\n')
    f.write('# 男生說 ครับ（khrap），女生說 ค่ะ／คะ（kha）。⚠ 自編近似發音，沒有母語者校對；念不準就亮手機。\n\n')
    for disp, rows in out:
        f.write(f'[[lang]]\nsec = {toml_str(disp)}\n')
        if NOTES.get(disp):
            f.write(f'note = {toml_str(NOTES[disp])}\n')
        f.write('rows = [\n')
        for r in rows:
            f.write('  { ' + ', '.join(f'{k} = {toml_str(v)}' for k, v in r.items()) + ' },\n')
        f.write(']\n\n')

total = sum(len(r) for _, r in out)
print(f'✓ {SRC} → {DST.relative_to(ROOT)}：{len(out)} 節 / {total} 列')
