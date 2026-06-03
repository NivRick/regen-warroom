// ── 密碼驗證 ──
// SHA-256("GSBC2026")
const PASS_HASH = '74a148789560c4870dfac86e2b8915e03920db298ead51272ff2f8d0de59d951';

async function sha256(str) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(str));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
}

async function checkPassword() {
  const val = document.getElementById('pwd-input').value;
  const hash = await sha256(val);
  if (hash === PASS_HASH) {
    sessionStorage.setItem('regen_auth', '1');
    document.getElementById('login-screen').classList.add('hidden');
    document.getElementById('main-app').classList.remove('hidden');
    loadAllData();
  } else {
    const err = document.getElementById('login-error');
    err.textContent = '密碼錯誤，請重試';
    document.getElementById('pwd-input').value = '';
    setTimeout(() => err.textContent = '', 3000);
  }
}

function logout() {
  sessionStorage.removeItem('regen_auth');
  location.reload();
}

document.getElementById('pwd-input')?.addEventListener('keydown', e => {
  if (e.key === 'Enter') checkPassword();
});

if (sessionStorage.getItem('regen_auth') === '1') {
  document.getElementById('login-screen').classList.add('hidden');
  document.getElementById('main-app').classList.remove('hidden');
}

// ── 模組定義 ──
const MODULES = [
  { id: 'taiwan',     label: '台灣市場',  icon: '🇹🇼', tag: 'tag-taiwan',      file: 'data/taiwan-market.json' },
  { id: 'research',   label: '臨床突破',  icon: '🔬',  tag: 'tag-research',    file: 'data/global-research.json' },
  { id: 'apac',       label: '亞太合作',  icon: '🌏',  tag: 'tag-apac',        file: 'data/asia-pacific.json' },
  { id: 'regulation', label: '法規動態',  icon: '⚖️',  tag: 'tag-regulation',  file: 'data/regulations.json' },
  { id: 'funding',    label: '資金動向',  icon: '💰',  tag: 'tag-funding',     file: 'data/funding.json' },
  { id: 'tourism',    label: '醫療旅遊',  icon: '✈️',  tag: 'tag-tourism',     file: 'data/medical-tourism.json' },
  { id: 'competitor', label: '競爭動態',  icon: '🎯',  tag: 'tag-competitor',  file: 'data/competitors.json' },
];

// ── 全域狀態 ──
let allCards = [];
let currentModule = 'all';
let searchQuery   = '';
let searchTimer   = null;
let digestMode    = false;         // #30 一頁摘要模式

// #9 排序（date-desc / date-asc / module）
let sortMode = 'date-desc';

// #11 我的關注
const WATCH_KEY = 'regen_watchlist';
let watchlist = JSON.parse(localStorage.getItem(WATCH_KEY) || '[]');
let watchFilterActive = false;

// #25 已讀標記
const READ_KEY = 'regen_read_ids';
let readIds = new Set(JSON.parse(localStorage.getItem(READ_KEY) || '[]'));
function saveReadIds() {
  localStorage.setItem(READ_KEY, JSON.stringify([...readIds]));
}

// ── 載入資料 ──
async function loadAllData() {
  const container = document.getElementById('cards-container');
  container.innerHTML = `
    <div class="loading-spinner">
      <div class="spinner"></div>
      <p id="load-progress">載入情報資料 0 / ${MODULES.length}...</p>
    </div>`;

  let loaded = 0;
  const failedModules = [];

  const results = await Promise.allSettled(
    MODULES.map(m =>
      fetchModule(m).then(data => {
        loaded++;
        const el = document.getElementById('load-progress');
        if (el) el.textContent = `載入情報資料 ${loaded} / ${MODULES.length}...`;
        return data;
      })
    )
  );

  allCards = [];
  let latestDate = null;

  results.forEach((r, i) => {
    if (r.status === 'fulfilled') {
      const items = r.value.items || [];
      items.forEach(item => {
        allCards.push({ ...item, moduleId: MODULES[i].id, moduleLabel: MODULES[i].label });
        if (item.date && (!latestDate || item.date > latestDate)) latestDate = item.date;
      });
    } else {
      failedModules.push(MODULES[i].label);
    }
  });

  allCards.sort((a, b) => (b.date || '').localeCompare(a.date || ''));

  document.getElementById('total-items').textContent = allCards.length;
  document.getElementById('last-update').textContent = `更新：${latestDate ? formatDate(latestDate) : '未知'}`;
  document.getElementById('data-date').textContent = new Date().toLocaleDateString('zh-TW');

  if (failedModules.length > 0) {
    showErrorBanner(`⚠️ 以下模組載入失敗：${failedModules.join('、')}，其他資料正常顯示。`);
  }

  updateWatchBtn();
  renderCards(allCards);
}

async function fetchModule(mod) {
  const res = await fetch(`${mod.file}?t=${Date.now()}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function showErrorBanner(msg) {
  const existing = document.getElementById('error-banner');
  if (existing) existing.remove();
  const banner = document.createElement('div');
  banner.id = 'error-banner';
  banner.className = 'error-banner';
  banner.innerHTML = `${msg} <button onclick="this.parentElement.remove()" style="margin-left:8px;background:none;border:none;color:inherit;cursor:pointer;font-size:14px;">✕</button>`;
  document.getElementById('cards-container').insertAdjacentElement('beforebegin', banner);
}

// ── 渲染 ──
function renderCards(cards, query = '') {
  const container = document.getElementById('cards-container');

  if (cards.length === 0) {
    container.innerHTML = `<div class="empty-state"><p style="font-size:32px">📭</p><p>暫無情報資料</p></div>`;
    return;
  }

  // #30 一頁摘要模式
  if (digestMode) {
    container.innerHTML = `<div class="digest-list">${cards.map(c => digestRow(c, query)).join('')}</div>`;
    return;
  }

  if (currentModule === 'all') {
    const grouped = {};
    MODULES.forEach(m => grouped[m.id] = []);
    cards.forEach(c => { if (grouped[c.moduleId]) grouped[c.moduleId].push(c); });

    let html = '';
    MODULES.forEach(m => {
      const items = grouped[m.id];
      if (!items.length) return;

      // #14 落後指標警示
      const latestDate = items[0]?.date;
      const daysSince = latestDate
        ? Math.floor((Date.now() - new Date(latestDate).getTime()) / 86400000)
        : null;
      const staleWarning = (daysSince !== null && daysSince > 7)
        ? `<span class="stale-badge">⚠ ${daysSince}天前</span>`
        : '';

      html += `<div class="module-header">
        <span class="module-icon">${m.icon}</span>
        <span class="module-title">${m.label}</span>
        ${staleWarning}
        <span class="module-count">${items.length}</span>
      </div>`;
      html += items.slice(0, 8).map(c => cardHTML(c, m, query)).join('');
      if (items.length > 8) {
        html += `<button class="show-more-btn" onclick="switchToModule('${m.id}')">查看全部 ${items.length} 則 ${m.label} →</button>`;
      }
    });
    container.innerHTML = html;
  } else {
    const mod = MODULES.find(m => m.id === currentModule);
    container.innerHTML = cards.map(c => cardHTML(c, mod, query)).join('');
  }
}

// #30 摘要列（一行一則）
function digestRow(item, query = '') {
  const mod  = MODULES.find(m => m.id === item.moduleId);
  const raw  = decodeEntities(item.title || '無標題');
  const title = query ? highlight(raw, query) : escHtml(raw);
  const url  = item.url ? escHtml(item.url) : '#';
  const meta = `${escHtml(item.source || mod?.label || '')} · ${formatDateShort(item.date)}`;
  return `<a class="digest-row" href="${url}" target="_blank" rel="noopener" onclick="event.stopPropagation()">
    <span class="digest-icon">${mod?.icon || '📄'}</span>
    <span class="digest-title">${title}</span>
    <span class="digest-meta">${meta}</span>
  </a>`;
}

function cardHTML(item, mod, query = '') {
  const rawTitle   = decodeEntities(item.title || '無標題');
  const rawSummary = decodeEntities(item.summary || '');
  const safeTitle   = query ? highlight(rawTitle, query)   : escHtml(rawTitle);
  const safeSummary = query ? highlight(rawSummary, query) : escHtml(rawSummary);
  const safeSource  = escHtml(item.source || mod?.label || '');
  const moduleId    = mod?.id || item.moduleId;
  const moduleLabel = mod?.label || item.moduleLabel;
  const modTag      = mod?.tag || 'tag-research';
  const freshnessHtml = freshnessTag(item.date);
  const cardId = btoa(encodeURIComponent((item.title || '') + (item.date || ''))).slice(0, 20);
  const isRead = readIds.has(cardId);

  // #22 顯示來源域名而非 Google 長網址
  const displaySource = item.source && item.source !== 'Google News'
    ? safeSource
    : escHtml(getDisplayDomain(item.url) || item.source || mod?.label || '');

  const shareBtn = item.title
    ? `<button class="share-btn" onclick="shareCard(event,'${cardId}')" title="分享此情報">⎋</button>`
    : '';

  return `<div class="intel-card${isRead ? ' is-read' : ''}" data-module="${moduleId}" data-card-id="${cardId}"
    onclick="markRead('${cardId}', this)">
    <div class="card-top">
      <span class="card-tag ${modTag}">${moduleLabel}</span>
      <div class="card-top-right">
        ${freshnessHtml}
        <span class="card-date">${formatDateShort(item.date || '')}</span>
        ${shareBtn}
      </div>
    </div>
    <div class="card-title">${safeTitle}</div>
    ${safeSummary ? `<div class="card-summary">${safeSummary}</div>` : ''}
    <div class="card-footer">
      <span class="card-source">${displaySource}</span>
      ${item.url ? `<a class="card-link" href="${escHtml(item.url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">查看原文 →</a>` : ''}
    </div>
  </div>`;
}

// ── #9 排序 + #11 關注 + 搜尋 三合一過濾 ──
function applyFilters() {
  let cards = currentModule === 'all'
    ? allCards
    : allCards.filter(c => c.moduleId === currentModule);

  // #11 我的關注篩選
  if (watchFilterActive && watchlist.length > 0) {
    cards = cards.filter(card => {
      const hay = [card.title, card.summary, card.source, card.moduleLabel].join(' ').toLowerCase();
      return watchlist.some(kw => hay.includes(kw.toLowerCase()));
    });
  }

  // 搜尋篩選
  if (searchQuery) {
    const keywords = searchQuery.toLowerCase().split(/\s+/).filter(Boolean);
    cards = cards.filter(card => {
      const haystack = [card.title, card.summary, card.source, card.moduleLabel].join(' ').toLowerCase();
      return keywords.every(kw => haystack.includes(kw));
    });

    const hint = document.getElementById('search-hint');
    hint.classList.remove('hidden');
    if (cards.length === 0) {
      hint.innerHTML = `🔍 找不到「<strong>${escHtml(searchQuery)}</strong>」相關情報`;
      hint.className = 'search-hint search-hint-empty';
    } else {
      hint.innerHTML = `找到 <strong>${cards.length}</strong> 筆「<strong>${escHtml(searchQuery)}</strong>」相關情報`;
      hint.className = 'search-hint search-hint-found';
    }
  } else {
    document.getElementById('search-hint').classList.add('hidden');
  }

  // #9 排序
  sortMode = document.getElementById('sort-select')?.value || 'date-desc';
  if (sortMode === 'date-asc') {
    cards = [...cards].sort((a, b) => (a.date || '').localeCompare(b.date || ''));
  } else if (sortMode === 'module') {
    cards = [...cards].sort((a, b) => a.moduleId.localeCompare(b.moduleId));
  }
  // date-desc 已是預設順序，不額外排序

  renderCards(cards, searchQuery);
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// 搜尋 debounce
function onSearch(val) {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    searchQuery = val.trim();
    document.getElementById('search-clear').classList.toggle('hidden', !searchQuery);
    applyFilters();
  }, 300);
}

function clearSearch() {
  const input = document.getElementById('search-input');
  input.value = '';
  searchQuery = '';
  document.getElementById('search-clear').classList.add('hidden');
  document.getElementById('search-hint').classList.add('hidden');
  applyFilters();
  input.focus();
}

// Tab 切換
function filterModule(moduleId, btn) {
  currentModule = moduleId;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  applyFilters();
}

// 從「看更多」按鈕切換到對應 tab
function switchToModule(moduleId) {
  const btn = document.querySelector(`.tab-btn[data-module="${moduleId}"]`);
  if (btn) filterModule(moduleId, btn);
}

// #25 標記已讀
function markRead(cardId, el) {
  if (!readIds.has(cardId)) {
    readIds.add(cardId);
    saveReadIds();
    el.classList.add('is-read');
  }
}

// #24 分享功能
function shareCard(event, cardId) {
  event.stopPropagation();
  const card = document.querySelector(`[data-card-id="${cardId}"]`);
  if (!card) return;
  const title  = card.querySelector('.card-title')?.textContent || '';
  const source = card.querySelector('.card-source')?.textContent || '';
  const link   = card.querySelector('.card-link')?.href || location.href;
  const text   = `【再生醫療情報】\n${title}\n來源：${source}`;
  if (navigator.share) {
    navigator.share({ title, text, url: link }).catch(() => {});
  } else {
    navigator.clipboard?.writeText(`${text}\n${link}`).then(() => showToast('已複製到剪貼簿')).catch(() => showToast('請手動複製連結'));
  }
}

// #30 摘要模式切換
function toggleDigest() {
  digestMode = !digestMode;
  document.getElementById('digest-btn')?.classList.toggle('active', digestMode);
  applyFilters();
}

// ── #11 我的關注 ──
function toggleWatchPanel() {
  const panel = document.getElementById('watch-panel');
  const isHidden = panel.classList.toggle('hidden');
  if (!isHidden) {
    renderWatchChips();
    document.getElementById('watch-input')?.focus();
  }
}

function addWatchword() {
  const inp = document.getElementById('watch-input');
  const val = inp.value.trim();
  if (!val) return;
  if (!watchlist.includes(val)) {
    watchlist.push(val);
    localStorage.setItem(WATCH_KEY, JSON.stringify(watchlist));
  }
  inp.value = '';
  renderWatchChips();
  updateWatchBtn();
}

function removeWatchword(i) {
  watchlist.splice(i, 1);
  localStorage.setItem(WATCH_KEY, JSON.stringify(watchlist));
  renderWatchChips();
  updateWatchBtn();
  if (watchFilterActive) applyFilters();
}

function toggleWatchFilter() {
  watchFilterActive = !watchFilterActive;
  document.getElementById('watch-filter-btn')?.classList.toggle('active', watchFilterActive);
  updateWatchBtn();
  applyFilters();
}

function renderWatchChips() {
  const container = document.getElementById('watch-chips');
  if (!container) return;
  if (watchlist.length === 0) {
    container.innerHTML = `<span style="font-size:13px;color:var(--text-dim)">尚未新增任何關注關鍵字</span>`;
  } else {
    container.innerHTML = watchlist.map((kw, i) =>
      `<span class="watch-chip">${escHtml(kw)}<button onclick="removeWatchword(${i})">×</button></span>`
    ).join('');
  }
  document.getElementById('watch-filter-btn')?.classList.toggle('active', watchFilterActive);
}

function updateWatchBtn() {
  const btn = document.getElementById('watch-btn');
  if (!btn) return;
  btn.textContent = watchlist.length > 0 ? `⭐ 關注 (${watchlist.length})` : '⭐ 關注';
  btn.classList.toggle('active', watchFilterActive);
}

// 關注面板 Enter 快捷鍵
document.getElementById('watch-input')?.addEventListener('keydown', e => {
  if (e.key === 'Enter') addWatchword();
});

// Toast
function showToast(msg) {
  const t = document.createElement('div');
  t.className = 'toast';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.classList.add('toast-show'), 10);
  setTimeout(() => { t.classList.remove('toast-show'); setTimeout(() => t.remove(), 300); }, 2500);
}

// ── 工具函數 ──

function freshnessTag(dateStr) {
  if (!dateStr) return '';
  const days = Math.floor((Date.now() - new Date(dateStr).getTime()) / 86400000);
  if (days < 0) return '';
  if (days === 0) return `<span class="fresh-tag fresh-today">今天</span>`;
  if (days <= 2) return `<span class="fresh-tag fresh-new">${days}天前</span>`;
  if (days <= 7) return `<span class="fresh-tag fresh-week">${days}天前</span>`;
  return `<span class="fresh-tag fresh-old">${days}天前</span>`;
}

function formatDateShort(dateStr) {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('zh-TW', { month: 'numeric', day: 'numeric' });
  } catch { return dateStr.slice(5, 10); }
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('zh-TW', { year: 'numeric', month: 'numeric', day: 'numeric' });
  } catch { return dateStr.slice(0, 10); }
}

// #22 從 URL 取得乾淨域名
function getDisplayDomain(url) {
  if (!url) return '';
  try { return new URL(url).hostname.replace(/^www\./, ''); }
  catch { return ''; }
}

function highlight(text, query) {
  if (!query || !text) return escHtml(text);
  const escaped = escHtml(text);
  const keywords = query.trim().split(/\s+/).filter(Boolean);
  let result = escaped;
  keywords.forEach(kw => {
    const safe = kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    result = result.replace(new RegExp(`(${safe})`, 'gi'), '<mark>$1</mark>');
  });
  return result;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function decodeEntities(str) {
  return String(str)
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#\d+;/g, '')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

// ── 自動載入 ──
if (sessionStorage.getItem('regen_auth') === '1') {
  loadAllData();
}
