(() => {
  'use strict';
  const B = JSON.parse(document.getElementById('boot').textContent);
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  };
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = n => '฿' + Math.round(n).toLocaleString('en-US');
  const twd = n => 'NT$' + Math.round(n / B.rate).toLocaleString('en-US');
  const hhmm = m => { m = ((m % 1440) + 1440) % 1440; return String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0'); };

  // ── 1. 時間：一律用曼谷時間；?now=2026-11-03T15:00 可模擬（測試用）
  const qs = new URLSearchParams(location.search);
  const nowDate = () => {
    const q = qs.get('now');
    if (q) { const d = new Date(q.length <= 16 ? q + ':00+07:00' : q); if (!isNaN(d)) return d; }
    return new Date();
  };
  const bkkParts = d => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Bangkok', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
    .formatToParts(d).reduce((o, p) => (o[p.type] = p.value, o), {});
  const addDays = (iso, n) => { const t = new Date(iso + 'T00:00:00Z'); t.setUTCDate(t.getUTCDate() + n); return t.toISOString().slice(0, 10); };
  const dayDiff = (a, b) => Math.round((Date.parse(b + 'T00:00:00Z') - Date.parse(a + 'T00:00:00Z')) / 864e5);

  function clock() {
    const p = bkkParts(nowDate());
    const iso = `${p.year}-${p.month}-${p.day}`;
    let min = (+p.hour) * 60 + (+p.minute), eff = iso;
    if (+p.hour < 5) { eff = addDays(iso, -1); min += 1440; } // 05:00 前算前一天
    let mode = 'trip';
    if (eff < B.start) mode = 'pre'; else if (eff > B.end) mode = 'after';
    const day = B.days.find(d => d.date === eff);
    return { iso, eff, min, mode, day };
  }

  let C = clock();
  let selected = null; // 使用者手動選的天

  // ── 2. 預約期限、待辦期限
  function deadlines() {
    $$('.chip.need[data-by]').forEach(c => {
      const by = c.dataset.by; if (!by) return;
      if (!c.dataset.orig) c.dataset.orig = c.textContent;
      if (C.iso > by) { c.textContent = '🔴 逾期未訂 · 今天就訂'; c.classList.add('late'); }
      else if (C.iso === by) { c.textContent = '🔴 今天要訂'; c.classList.add('late'); }
      else { c.textContent = c.dataset.orig; c.classList.remove('late'); }
    });
    $$('.todo li[data-due]').forEach(li => {
      const due = li.dataset.due, op = li.dataset.open, el = $('.due', li);
      const md = s => (+s.slice(5, 7)) + '/' + (+s.slice(8, 10));
      el.className = 'due';
      if (op && C.iso < op) { el.textContent = md(op) + ' 開放'; el.classList.add('ok'); }
      else if (C.iso > due) el.textContent = '已逾期';
      else if (C.iso === due) el.textContent = '今天';
      else if (dayDiff(C.iso, due) <= 2) { el.textContent = md(due) + ' 前'; el.classList.add('soon'); }
      else { el.textContent = md(due) + ' 前'; el.classList.add('ok'); }
    });
  }

  // ── 3. 今天：選天、hero、已過站
  const ICON = { grab: '🚕', bts: '🚆', walk: '🚶', moto: '🛵', plane: '✈️', none: '•' };
  const SVG = Object.fromEntries(['nav','show','tel','map'].map(k => [k, `<svg aria-hidden="true"><use href="#i-${k}"/></svg>`]));

  function heroHtml(id, now) {
    const S = B.stops[id];
    let nx = S.findIndex(s => s.t > now && !s.mv);
    if (nx < 0) nx = S.findIndex(s => s.t > now);
    if (nx < 0) {
      const di = B.days.findIndex(d => d.id === id), nd = B.days[di + 1];
      const tip = nd ? `明天 D${nd.n} 第一站 ${B.stops[nd.id][0].l}：${esc(B.stops[nd.id][0].n)}` : '回家路上小心。';
      const last = S[S.length - 1];
      const curTxt = now - last.t < 90 ? `<b>現在：${esc(last.n)}</b>這是今天最後一站。` : '<b>今天的行程走完了</b>';
      return `<article class="hero" aria-label="下一站"><div class="hero-end">${curTxt}${tip}</div></article>`;
    }
    const s = S[nx];
    let mv = null;
    for (let i = 0; i < nx; i++) if (S[i].mv && S[i].t > now) { mv = S[i]; break; }
    const diff = s.t - now;
    const lab = diff > 90 ? `下一站 · ${s.l}` : `下一站 · ${diff} 分鐘後`;
    let transit = '';
    if (mv) transit = `<div class="hero-transit">${ICON[mv.m]} <span><b>${mv.l} ${esc(mv.n)}</b> · ${esc(mv.leg || mv.w)}</span></div>`;
    else if (s.leg) transit = `<div class="hero-transit">${ICON[s.m]} <span><b>怎麼去</b> · ${esc(s.leg)}</span></div>`;
    const third = s.tel ? `<a class="act" href="${esc(s.tel)}">${SVG.tel}打電話</a>`
      : s.p ? `<a class="act" href="#place-${esc(s.p)}" data-goplace="${esc(s.p)}">${SVG.map}地點卡</a>`
      : `<a class="act" href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(s.q)}" target="_blank" rel="noopener">${SVG.map}地圖</a>`;
    const showBtn = s.p ? `<button class="act" type="button" data-show="${esc(s.p)}">${SVG.show}給司機看</button>`
      : `<a class="act" href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(s.q)}" target="_blank" rel="noopener">${SVG.map}地圖</a>`;
    const after = S.slice(nx + 1).find(x => !x.mv);
    return `<article class="hero" aria-label="下一站">
      <div class="hero-top"><span class="pulse" aria-hidden="true"></span><span>${lab}</span></div>
      <div class="hero-body"><span class="tile cat-${s.c}" aria-hidden="true">${s.ic}</span><div>
        <p class="when">${/^~?\d/.test(s.l) ? `<b class="tnum">${esc(s.l)}</b> 開始` : `<b>${esc(s.l)}</b> · 約 ${hhmm(s.t)}`}</p>
        <h2>${esc(s.n)}</h2>${s.s ? `<p class="sub">${esc(s.s)}</p>` : ''}
        <p class="sub">${esc(s.w)}</p>${(($('#' + s.id + ' .chips') || {}).outerHTML) || ''}</div></div>
      ${transit}
      <div class="actions"><a class="act primary" href="${esc(s.nav)}" target="_blank" rel="noopener">${SVG.nav}導航</a>${showBtn}${third}</div>
    </article>${after ? `<p class="later">之後 <b class="tnum">${esc(after.l)}</b> ${esc(after.n)}</p>` : ''}`;
  }

  const showDone = {};
  function paintDay(v, live) {
    const id = v.dataset.day;
    const tl = $('.tl', v), tog = $('.show-done', v);
    $$('.nowline', tl).forEach(n => n.remove());
    $('.hero-slot', v).innerHTML = '';
    const stops = $$('.stop', tl);
    stops.forEach(s => s.classList.remove('done', 'current'));
    $$('.meal', v).forEach(m => m.classList.remove('past', 'now-meal'));
    if (!live) {
      stops.forEach(s => { s.hidden = false; const l = $(`.leg[data-for="${s.id}"]`, tl); if (l) l.hidden = false; });
      tog.hidden = true; return;
    }
    const now = C.min;
    let cur = null;
    stops.forEach(s => { if (+s.dataset.t <= now) cur = s; });
    stops.forEach(s => {
      const t = +s.dataset.t;
      if (t <= now && s !== cur) s.classList.add('done');
    });
    if (cur) {
      const nxt = stops[stops.indexOf(cur) + 1];
      if (nxt) cur.classList.add('current'); else cur.classList.add('done');
    }
    // now 線：插在最後一個 t<=now 的站之後
    const line = document.createElement('li');
    line.className = 'nowline'; line.setAttribute('aria-label', '現在時間');
    line.innerHTML = `<span class="tnum">${hhmm(now)}</span><i></i>`;
    if (cur) {
      const nxt = stops[stops.indexOf(cur) + 1];
      const anchor = nxt ? ($(`.leg[data-for="${nxt.id}"]`, tl) || nxt) : null;
      tl.insertBefore(line, anchor);
    } else tl.insertBefore(line, tl.firstChild);
    // 已過的站預設收起
    const done = stops.filter(s => s.classList.contains('done'));
    const apply = () => {
      done.forEach(s => { s.hidden = !showDone[id]; const l = $(`.leg[data-for="${s.id}"]`, tl); if (l) l.hidden = !showDone[id]; });
      tog.textContent = showDone[id] ? '收起已過的站 ▴' : `顯示已過的 ${done.length} 站 ▾`;
    };
    tog.hidden = !done.length;
    tog.onclick = () => { showDone[id] = !showDone[id]; apply(); };
    apply();
    // 餐
    const meals = $$('.meal', v);
    let nowMeal = null;
    meals.forEach(m => { if (+m.dataset.t <= now) nowMeal = m; });
    meals.forEach(m => { if (+m.dataset.t < now && m !== nowMeal) m.classList.add('past'); });
    const firstFuture = meals.find(m => +m.dataset.t > now);
    // 正在吃（開始後 90 分內）優先，否則下一餐
    if (nowMeal && now - +nowMeal.dataset.t < 90) nowMeal.classList.add('now-meal');
    else { if (nowMeal) nowMeal.classList.add('past'); if (firstFuture) firstFuture.classList.add('now-meal'); }
    $('.hero-slot', v).innerHTML = heroHtml(id, now);
  }

  function render() {
    C = clock();
    const liveId = C.mode === 'trip' && C.day ? C.day.id : null;
    const defId = liveId || (C.mode === 'pre' ? B.days[0].id : B.days[B.days.length - 1].id);
    const id = selected || defId;
    $$('.dayview').forEach(v => {
      const on = v.dataset.day === id;
      v.classList.toggle('on', on);
      paintDay(v, on && v.dataset.day === liveId);
      $('.today-spend', v).hidden = C.mode === 'pre';
    });
    $$('.dchip').forEach(c => {
      const d = B.days.find(x => x.id === c.dataset.day);
      c.classList.toggle('past', C.mode !== 'pre' && d.date < C.eff);
      if (d.id === liveId) c.setAttribute('aria-current', 'date'); else c.removeAttribute('aria-current');
      c.classList.toggle('sel', c.dataset.day === id && id !== liveId);
      c.setAttribute('aria-pressed', c.dataset.day === id);
    });
    $('#pretrip').hidden = C.mode !== 'pre';
    $('#ended').hidden = C.mode !== 'after';
    const d = B.days.find(x => x.id === id);
    const wd = '日一二三四五六'[new Date(d.date + 'T00:00:00Z').getUTCDay()];
    if (C.mode === 'pre') {
      const n = dayDiff(C.eff, B.start);
      $('#cd').textContent = n;
      $('#tb-day').textContent = `還有 ${n} 天`;
      $('#tb-sub').textContent = selected ? `看 D${d.n} · ${+d.date.slice(5, 7)}/${+d.date.slice(8)}` : '曼谷 11/1–11/7';
    } else {
      $('#tb-day').textContent = `D${d.n} · ${+d.date.slice(5, 7)}/${+d.date.slice(8)} 週${wd}`;
      $('#tb-sub').textContent = C.mode === 'after' ? '旅程結束' : (id === liveId ? '今天 · 曼谷 ' + hhmm(C.min) : '不是今天');
    }
    $('#backtoday').hidden = !selected || selected === defId;
    deadlines();
    paintSpend();
  }

  // 日期條、總覽、回到今天
  document.addEventListener('click', e => {
    const c = e.target.closest('.dchip');
    if (c) { selected = c.dataset.day; render(); return; }
    const g = e.target.closest('[data-goto]');
    if (g) { selected = g.dataset.goto; goTab('today'); render(); return; }
  });
  $('#backtoday').onclick = () => { selected = null; render(); };

  // ── 4. 站點展開
  document.addEventListener('click', e => {
    const h = e.target.closest('.st-head'); if (!h) return;
    const li = h.closest('.stop'); const o = li.classList.toggle('open'); h.setAttribute('aria-expanded', o);
  });

  // ── 5. 打勾類（出門帶、必吃必買、待辦）：只存在這支手機
  const ticks = store.get('bkk-ticks', {});
  const syncTicks = () => {
    $$('[data-pk],[data-mk],[data-td]').forEach(b => {
      const k = b.dataset.pk ? 'pk-' + b.dataset.pk : b.dataset.mk ? 'mk-' + b.dataset.mk : 'td-' + b.dataset.td;
      b.setAttribute('aria-pressed', !!ticks[k]);
      if (b.dataset.td) b.closest('li').classList.toggle('done', !!ticks[k]);
    });
  };
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-pk],[data-mk],[data-td]'); if (!b) return;
    const k = b.dataset.pk ? 'pk-' + b.dataset.pk : b.dataset.mk ? 'mk-' + b.dataset.mk : 'td-' + b.dataset.td;
    if (ticks[k]) delete ticks[k]; else ticks[k] = 1;
    store.set('bkk-ticks', ticks); syncTicks();
  });
  // 行前模式：把待辦搬一份到「今天」
  const todoSrc = $('#todo-acc .acc-body');
  if (todoSrc) $('#pre-todo').innerHTML = todoSrc.innerHTML;
  if (clock().mode === 'pre') $('#todo-acc').open = true;

  // ── 6. 分頁
  const tabs = $$('.tab');
  function goTab(v, keepScroll) {
    if (!$('#view-' + v)) v = 'today';
    $$('.view').forEach(s => s.classList.toggle('active', s.id === 'view-' + v));
    tabs.forEach(t => t.setAttribute('aria-selected', t.dataset.v === v));
    try { sessionStorage.setItem('tab', v); } catch (e) {}
    if (!keepScroll) scrollTo(0, 0);
  }
  tabs.forEach(t => t.onclick = () => goTab(t.dataset.v));
  let startTab = qs.get('tab') || (location.hash.match(/^#(today|trip|places|lang|sos)$/) || [])[1];
  if (!startTab) { try { startTab = sessionStorage.getItem('tab'); } catch (e) {} }
  goTab(startTab || 'today');

  // 「完整地點卡」→ 地點分頁
  document.addEventListener('click', e => {
    const a = e.target.closest('[data-goplace]'); if (!a) return;
    e.preventDefault();
    filter('');
    goTab('places', true);
    const el = document.getElementById('place-' + a.dataset.goplace);
    if (el) el.scrollIntoView({ block: 'start' });
  });

  // ── 7. 地點篩選
  const fchips = $$('.fchip');
  function filter(c) {
    fchips.forEach(f => f.setAttribute('aria-pressed', f.dataset.f === c));
    $$('#view-places [data-cat]').forEach(el => el.hidden = !!c && el.dataset.cat !== c);
  }
  fchips.forEach(f => f.onclick = () => filter(f.dataset.f));

  // ── 8. 給司機看（全螢幕）
  const dlg = $('#show');
  let cur = null, wake = null;
  const openShow = o => {
    cur = o;
    $('#sh-lab').textContent = o.lab;
    const big = $('#sh-th');
    big.textContent = o.big; big.lang = o.bigLang; big.style.whiteSpace = 'pre-line';
    $('#sh-en').textContent = o.mid; $('#sh-zh').textContent = o.small;
    const m = $('#sh-map'); m.hidden = !o.map; if (o.map) m.href = o.map;
    if (dlg.showModal) dlg.showModal(); else dlg.setAttribute('open', '');
    try { if (navigator.wakeLock) navigator.wakeLock.request('screen').then(w => wake = w).catch(() => {}); } catch (e) {}
  };
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-show]'); if (!b) return;
    const s = B.show[b.dataset.show]; if (!s) return;
    openShow({
      lab: 'กรุณาพาไปที่นี่ · 請帶我到這裡',
      big: s.th || s.en, bigLang: s.th ? 'th' : 'en',
      mid: s.th ? s.en : '（沒有核對過的泰文：請司機看英文，或直接用 Grab）',
      small: s.zh + (s.th && !s.ok ? ' · 泰文待核對' : ''), map: s.map, copy: s.th || s.en
    });
  });
  $('#sh-x').onclick = () => dlg.close ? dlg.close() : dlg.removeAttribute('open');
  dlg.addEventListener('close', () => { try { wake && wake.release(); } catch (e) {} wake = null; });
  $('#sh-copy').onclick = () => { try { navigator.clipboard.writeText(cur.copy); $('#sh-copy').textContent = '已複製'; setTimeout(() => $('#sh-copy').textContent = '複製', 1500); } catch (e) {} };

  // ── 9. 泰語：男女句尾、搜尋、放大
  const Q = /(ไหม|มั้ย|อะไร|ที่ไหน|เท่าไหร่|กี่|หรือยัง|ไหน|ยังไง|หรือเปล่า|ใคร|เมื่อไหร่)/;
  const femTh = th => th.split('ครับ').map((seg, i, a) => i === a.length - 1 ? seg : seg + (Q.test(seg.split(/[\/,，]/).pop()) ? 'คะ' : 'ค่ะ')).join('').replace(/ผม/g, 'ฉัน');
  const femRo = ro => ro.replace(/\bkhrap\b/g, 'kha').replace(/\bphom\b/g, 'chan');
  let g = store.get('bkk-g', 'm');
  const renderPh = () => {
    $$('.seg button').forEach(x => x.setAttribute('aria-pressed', x.dataset.g === g));
    $$('#phr-all .ph').forEach(b => {
      const th = $('.th', b), ro = $('.ro', b);
      if (th) th.textContent = g === 'f' ? femTh(b.dataset.th) : b.dataset.th;
      if (ro) ro.textContent = g === 'f' ? femRo(b.dataset.ro) : b.dataset.ro;
    });
  };
  $$('.seg button').forEach(s => s.onclick = () => { g = s.dataset.g; store.set('bkk-g', g); renderPh(); });
  renderPh();
  document.addEventListener('click', e => {
    const b = e.target.closest('.ph'); if (!b) return;
    const th = $('.th', b) ? $('.th', b).textContent : '';
    const ro = $('.ro', b) ? $('.ro', b).textContent : '';
    openShow({ lab: b.dataset.zh, big: th || b.dataset.en, bigLang: th ? 'th' : 'en',
      mid: th ? [ro, b.dataset.en].filter(Boolean).join(' · ') : '', small: '', map: '', copy: th || b.dataset.en });
  });
  const qIn = $('#q');
  qIn.addEventListener('input', () => {
    const q = qIn.value.trim().toLowerCase();
    let any = false;
    $$('#phr-all .lsec').forEach(sec => {
      let n = 0;
      $$('li', sec).forEach(li => {
        const b = $('.ph', li);
        const hit = !q || (b.dataset.zh + ' ' + b.dataset.en + ' ' + b.dataset.ro + ' ' + b.dataset.th).toLowerCase().includes(q);
        li.hidden = !hit; if (hit) n++;
      });
      sec.hidden = !n; if (n) any = true;
    });
    $('#noresult').hidden = any;
  });

  // ── 10. 深淺色
  const root = document.documentElement;
  if (qs.get('theme')) root.dataset.theme = qs.get('theme');
  $('#theme').onclick = () => {
    const dark = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    root.dataset.theme = dark ? 'light' : 'dark';
    try { localStorage.setItem('theme', root.dataset.theme); } catch (e) {}
  };

  // ── 11. 連線狀態
  const net = $('#net');
  const upd = () => { net.classList.toggle('off', !navigator.onLine); net.textContent = navigator.onLine ? '線上' : '離線中'; };
  addEventListener('online', upd); addEventListener('offline', upd); upd();

  // ── 12. 記帳（只存在這支手機）
  const SK = 'bkk-spend';
  const getSp = () => { const v = store.get(SK, []); return Array.isArray(v) ? v : []; };
  const setSp = v => store.set(SK, v);
  const budgetThb = B.budget * B.rate;
  function paintSpend() {
    const sp = getSp();
    const by = {}; let total = 0;
    sp.forEach(x => { by[x.d] = (by[x.d] || 0) + x.a; total += x.a; });
    $$('.dayview').forEach(v => {
      const a = by[v.dataset.day] || 0, p = +v.dataset.plan;
      const ts = $('.today-spend', v);
      $('.b i', ts).style.width = Math.min(100, a / p * 100) + '%';
      $('.ts-v', ts).innerHTML = `<b>${fmt(a)}</b> / ${fmt(p)}`;
    });
    const mx = Math.max(...B.days.map(d => d.plan));
    $$('.dbar').forEach(r => {
      const a = by[r.dataset.day] || 0, p = +r.dataset.plan;
      $('u', r).style.width = Math.min(100, a / mx * 100) + '%';
      r.classList.toggle('over', a > p);
      $('.act', r).textContent = a ? '已記 ' + fmt(a) : '';
    });
    $('#spend-total').textContent = fmt(total);
    $('#spend-twd').textContent = total ? `（${twd(total)}）· 預算 ${fmt(budgetThb)}` : `· 預算 ${fmt(budgetThb)}`;
    $('#spend-sum .b i').style.width = Math.min(100, total / budgetThb * 100) + '%';
    const list = $('#spend-list');
    list.innerHTML = sp.length ? sp.slice().reverse().map(x => {
      const d = B.days.find(y => y.id === x.d);
      return `<li><span class="chip">D${d ? d.n : '?'}</span><span>${esc(x.c)}${x.n ? ' · ' + esc(x.n) : ''}</span><b>${fmt(x.a)}</b><button class="x" type="button" data-del="${x.i}" aria-label="刪除這筆">✕</button></li>`;
    }).join('') : '<li style="grid-template-columns:1fr"><span>還沒有記帳。按 ＋ 記一筆。</span></li>';
  }
  const sheet = $('#spend-dlg');
  document.addEventListener('click', e => {
    if (e.target.closest('.add')) {
      const live = C.mode === 'trip' && C.day ? C.day.id : null;
      $('#sp-day').value = selected || live || B.days[0].id;
      $('#sp-amt').value = ''; $('#sp-note').value = '';
      if (sheet.showModal) sheet.showModal(); else sheet.setAttribute('open', '');
      setTimeout(() => $('#sp-amt').focus(), 50);
      return;
    }
    const del = e.target.closest('[data-del]');
    if (del) { setSp(getSp().filter(x => String(x.i) !== del.dataset.del)); paintSpend(); }
  });
  $('#sp-cancel').onclick = () => sheet.close();
  $('#spend-form').addEventListener('submit', e => {
    const a = parseFloat(String($('#sp-amt').value).replace(/[^\d.]/g, ''));
    if (!(a > 0)) { e.preventDefault(); $('#sp-amt').focus(); return; }
    const c = ($('input[name="sp-cat"]:checked') || {}).value || '餐飲';
    const sp = getSp(); sp.push({ i: Date.now(), d: $('#sp-day').value, a: Math.round(a), c, n: $('#sp-note').value.trim().slice(0, 60) });
    setSp(sp); paintSpend();
  });
  $('#spend-export').onclick = () => {
    const t = JSON.stringify(getSp());
    try { navigator.clipboard.writeText(t).then(() => alert('已複製，貼到對方手機的「貼上匯入」。'), () => prompt('複製這段文字：', t)); } catch (e) { prompt('複製這段文字：', t); }
  };
  $('#spend-import').onclick = () => {
    const t = prompt('貼上對方複製的記帳文字：'); if (!t) return;
    try {
      const add = JSON.parse(t); if (!Array.isArray(add)) throw 0;
      const sp = getSp(), ids = new Set(sp.map(x => x.i));
      add.forEach(x => { if (x && x.i && x.d && x.a > 0 && !ids.has(x.i)) sp.push({ i: x.i, d: String(x.d), a: Math.round(x.a), c: String(x.c || '其他'), n: String(x.n || '').slice(0, 60) }); });
      setSp(sp); paintSpend();
    } catch (e) { alert('格式不對，沒有匯入。'); }
  };
  $('#spend-clear').onclick = () => { if (confirm('清除這支手機上的全部記帳？')) { setSp([]); paintSpend(); } };

  // ── 13. 啟動與定時更新
  syncTicks();
  render();
  setInterval(render, 60000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) render(); });

  // ── 14. 離線（service worker：network-first，不會永遠吃舊版）
  if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost')) {
    navigator.serviceWorker.register('sw.js').then(() => { $('#sw-state').textContent = '已存離線'; }).catch(() => {});
  }
})();
