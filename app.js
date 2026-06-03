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
    const savedPersona = localStorage.getItem(PERSONA_KEY);
    if (savedPersona) {
      document.getElementById('main-app').classList.remove('hidden');
      updatePersonaBtn(savedPersona);
      loadAllData().then(() => applyPersonaFilter(savedPersona));
    } else {
      showPersonaScreen();
    }
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
  const savedPersona = localStorage.getItem(PERSONA_KEY);
  if (savedPersona) {
    document.getElementById('main-app').classList.remove('hidden');
    updatePersonaBtn(savedPersona);
  } else {
    showPersonaScreen();
  }
}

// ── 角色分流 ──
const PERSONA_KEY = 'regen_persona';

const PERSONAS = {
  investor:   { label: '投資人',      icon: '💰', modules: ['funding', 'taiwan', 'competitor'] },
  researcher: { label: '研究 / 醫療', icon: '🔬', modules: ['research', 'regulation'] },
  industry:   { label: '產業觀察',    icon: '🌏', modules: ['apac', 'tourism', 'competitor'] },
  all:        { label: '全部瀏覽',    icon: '📡', modules: [] },
};

function showPersonaScreen() {
  document.getElementById('persona-screen').classList.remove('hidden');
}

function selectPersona(personaId) {
  localStorage.setItem(PERSONA_KEY, personaId);
  document.getElementById('persona-screen').classList.add('hidden');
  document.getElementById('main-app').classList.remove('hidden');
  updatePersonaBtn(personaId);
  loadAllData().then(() => {
    applyPersonaFilter(personaId);
    // 全部瀏覽確保 tabs/controls 顯示
    if (personaId === 'all') {
      document.querySelector('.module-tabs')?.classList.remove('hidden');
      document.querySelector('.controls-bar')?.classList.remove('hidden');
    }
  });
}

function applyPersonaFilter(personaId) {
  // 依角色切換 UI 模式
  const tabs = document.querySelector('.module-tabs');
  const controls = document.querySelector('.controls-bar');
  const stockTicker = document.getElementById('stock-ticker');

  if (personaId === 'all') {
    tabs?.classList.remove('hidden');
    controls?.classList.remove('hidden');
    renderCards(allCards);
    return;
  }

  // 各角色專屬 dashboard，隱藏通用 tabs
  tabs?.classList.add('hidden');
  controls?.classList.add('hidden');

  if (personaId === 'investor') {
    stockTicker?.classList.remove('hidden');
    renderDashboardInvestor();
  } else if (personaId === 'researcher') {
    stockTicker?.classList.add('hidden');
    renderDashboardResearcher();
  } else if (personaId === 'industry') {
    stockTicker?.classList.add('hidden');
    renderDashboardIndustry();
  }
}

// ── 投資人 Dashboard ──
function renderDashboardInvestor() {
  const funding    = allCards.filter(c => c.moduleId === 'funding');
  const taiwan     = allCards.filter(c => c.moduleId === 'taiwan');
  const competitor = allCards.filter(c => c.moduleId === 'competitor');
  const container  = document.getElementById('cards-container');

  const kpiHtml = `
    <div class="dash-kpi-bar">
      <div class="dash-kpi">
        <span class="dash-kpi-num">${funding.length}</span>
        <span class="dash-kpi-label">💰 資金動向</span>
      </div>
      <div class="dash-kpi">
        <span class="dash-kpi-num">${taiwan.length}</span>
        <span class="dash-kpi-label">🇹🇼 台灣市場</span>
      </div>
      <div class="dash-kpi">
        <span class="dash-kpi-num">${competitor.length}</span>
        <span class="dash-kpi-label">🎯 競爭動態</span>
      </div>
    </div>`;

  const col = (title, icon, items, modId) => {
    const mod = MODULES.find(m => m.id === modId);
    const cards = items.slice(0, 6).map(c => cardHTML(c, mod, '')).join('');
    return `<div class="dash-col">
      <div class="dash-col-header"><span>${icon}</span><span>${title}</span><span class="dash-col-count">${items.length}</span></div>
      ${cards}
    </div>`;
  };

  container.innerHTML = `
    ${kpiHtml}
    <div class="dash-grid-3">
      ${col('資金動向', '💰', funding, 'funding')}
      ${col('台灣市場', '🇹🇼', taiwan, 'taiwan')}
      ${col('競爭動態', '🎯', competitor, 'competitor')}
    </div>`;

  currentCards = [...funding, ...taiwan, ...competitor];
}

// ── 研究/醫療 Dashboard ──
function renderDashboardResearcher() {
  const research   = allCards.filter(c => c.moduleId === 'research');
  const regulation = allCards.filter(c => c.moduleId === 'regulation');
  const container  = document.getElementById('cards-container');

  const latestResearch = research[0];
  const heroHtml = latestResearch ? `
    <div class="dash-hero">
      <div class="dash-hero-label">🔬 最新臨床突破</div>
      <div class="dash-hero-title">${escHtml(decodeEntities(latestResearch.title || ''))}</div>
      <div class="dash-hero-meta">${escHtml(latestResearch.source || '')} · ${formatDateShort(latestResearch.date)}</div>
      ${latestResearch.url ? `<a class="dash-hero-link" href="${escHtml(latestResearch.url)}" target="_blank" rel="noopener">查看原文 →</a>` : ''}
    </div>` : '';

  const kpiHtml = `
    <div class="dash-kpi-bar">
      <div class="dash-kpi">
        <span class="dash-kpi-num">${research.length}</span>
        <span class="dash-kpi-label">🔬 臨床突破</span>
      </div>
      <div class="dash-kpi">
        <span class="dash-kpi-num">${regulation.length}</span>
        <span class="dash-kpi-label">⚖️ 法規動態</span>
      </div>
    </div>`;

  const researchMod   = MODULES.find(m => m.id === 'research');
  const regulationMod = MODULES.find(m => m.id === 'regulation');

  container.innerHTML = `
    ${heroHtml}
    ${kpiHtml}
    <div class="dash-grid-2 dash-grid-7-3">
      <div class="dash-col">
        <div class="dash-col-header"><span>🔬</span><span>臨床突破</span><span class="dash-col-count">${research.length}</span></div>
        ${research.slice(0, 10).map(c => cardHTML(c, researchMod, '')).join('')}
      </div>
      <div class="dash-col">
        <div class="dash-col-header"><span>⚖️</span><span>法規動態</span><span class="dash-col-count">${regulation.length}</span></div>
        ${regulation.slice(0, 8).map(c => cardHTML(c, regulationMod, '')).join('')}
      </div>
    </div>`;

  currentCards = [...research, ...regulation];
}

// ── 產業觀察 Dashboard ──
function renderDashboardIndustry() {
  const apac       = allCards.filter(c => c.moduleId === 'apac');
  const tourism    = allCards.filter(c => c.moduleId === 'tourism');
  const competitor = allCards.filter(c => c.moduleId === 'competitor');
  const container  = document.getElementById('cards-container');

  const kpiHtml = `
    <div class="dash-kpi-bar">
      <div class="dash-kpi">
        <span class="dash-kpi-num">${apac.length}</span>
        <span class="dash-kpi-label">🌏 亞太合作</span>
      </div>
      <div class="dash-kpi">
        <span class="dash-kpi-num">${tourism.length}</span>
        <span class="dash-kpi-label">✈️ 醫療旅遊</span>
      </div>
      <div class="dash-kpi">
        <span class="dash-kpi-num">${competitor.length}</span>
        <span class="dash-kpi-label">🎯 競爭動態</span>
      </div>
    </div>`;

  const apacMod      = MODULES.find(m => m.id === 'apac');
  const tourismMod   = MODULES.find(m => m.id === 'tourism');
  const competitorMod = MODULES.find(m => m.id === 'competitor');

  container.innerHTML = `
    ${kpiHtml}
    <div class="dash-grid-2 dash-grid-6-4">
      <div class="dash-col">
        <div class="dash-col-header"><span>🌏</span><span>亞太合作</span><span class="dash-col-count">${apac.length}</span></div>
        ${apac.slice(0, 8).map(c => cardHTML(c, apacMod, '')).join('')}
      </div>
      <div class="dash-col dash-col-stack">
        <div>
          <div class="dash-col-header"><span>✈️</span><span>醫療旅遊</span><span class="dash-col-count">${tourism.length}</span></div>
          ${tourism.slice(0, 4).map(c => cardHTML(c, tourismMod, '')).join('')}
        </div>
        <div>
          <div class="dash-col-header"><span>🎯</span><span>競爭動態</span><span class="dash-col-count">${competitor.length}</span></div>
          ${competitor.slice(0, 4).map(c => cardHTML(c, competitorMod, '')).join('')}
        </div>
      </div>
    </div>`;

  currentCards = [...apac, ...tourism, ...competitor];
}

function updatePersonaBtn(personaId) {
  const persona = PERSONAS[personaId] || PERSONAS.all;
  const btn = document.getElementById('persona-reset-btn');
  if (btn) btn.textContent = `${persona.icon} ${persona.label}`;
}

function resetPersona() {
  localStorage.removeItem(PERSONA_KEY);
  document.getElementById('main-app').classList.add('hidden');
  document.getElementById('persona-screen').classList.remove('hidden');
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
let allCards     = [];
let currentCards = [];          // 目前顯示的卡片（供匯出用）
let currentModule = 'all';
let searchQuery   = '';
let searchTimer   = null;
let digestMode    = false;
let chartVisible  = false;
let sortMode      = 'date-desc';
let _chartInstance = null;

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
  currentCards = allCards;

  document.getElementById('total-items').textContent = allCards.length;
  document.getElementById('last-update').textContent = `更新：${latestDate ? formatDate(latestDate) : '未知'}`;
  document.getElementById('data-date').textContent = new Date().toLocaleDateString('zh-TW');

  if (failedModules.length > 0) {
    showErrorBanner(`⚠️ 以下模組載入失敗：${failedModules.join('、')}，其他資料正常顯示。`);
  }

  updateWatchBtn();
  renderCards(allCards);

  // #15 股票快訊（非同步，不阻塞主畫面）
  loadStocks();
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

// ── #15 股票快訊 ──
async function loadStocks() {
  try {
    const res = await fetch(`data/stocks.json?t=${Date.now()}`);
    if (!res.ok) return;
    const data = await res.json();
    if (data.stocks?.length) renderStockTicker(data);
  } catch { /* 靜默失敗，股票非核心功能 */ }
}

function renderStockTicker(data) {
  const ticker = document.getElementById('stock-ticker');
  if (!ticker || !data.stocks?.length) return;

  // 依上中下游分組
  const TIERS = ['上游', '中游', '下游'];
  const grouped = {};
  TIERS.forEach(t => grouped[t] = []);
  data.stocks.forEach(s => {
    if (grouped[s.tier]) grouped[s.tier].push(s);
    else grouped['上游']?.push(s); // 未知 tier 歸上游
  });

  const TIER_ICONS = { '上游': '🔵', '中游': '🟡', '下游': '🔴' };

  let html = `<span class="ticker-label">📈 台股</span>`;

  TIERS.forEach(tier => {
    const stocks = grouped[tier];
    if (!stocks?.length) return;
    html += `<span class="ticker-sep">${TIER_ICONS[tier]}${tier}</span>`;
    html += stocks.map(s => {
      const isUp  = s.change_pct > 0;
      const isDown = s.change_pct < 0;
      const cls   = isUp ? 'up' : isDown ? 'down' : 'flat';
      const arrow = isUp ? '▲' : isDown ? '▼' : '─';
      const pct   = Math.abs(s.change_pct).toFixed(2);
      const url   = `https://tw.stock.yahoo.com/quote/${s.code}.TW`;
      return `<a class="stock-chip ${cls}" href="${url}" target="_blank" rel="noopener"
        title="${s.name}（${s.code}）${tier}">
        <span class="stock-name">${escHtml(s.name)}</span>
        <span class="stock-price">${s.close}</span>
        <span class="stock-chg">${arrow}${pct}%</span>
      </a>`;
    }).join('');
  });

  const dateLabel = data.stocks[0]?.date
    ? `<span class="ticker-date">${data.stocks[0].date}</span>` : '';
  ticker.innerHTML = html + dateLabel;
  ticker.classList.remove('hidden');
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

// #30 摘要列
function digestRow(item, query = '') {
  const mod   = MODULES.find(m => m.id === item.moduleId);
  const raw   = decodeEntities(item.title || '無標題');
  const title = query ? highlight(raw, query) : escHtml(raw);
  const url   = item.url ? escHtml(item.url) : '#';
  const meta  = `${escHtml(item.source || mod?.label || '')} · ${formatDateShort(item.date)}`;
  return `<a class="digest-row" href="${url}" target="_blank" rel="noopener">
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
  const moduleId    = mod?.id || item.moduleId;
  const moduleLabel = mod?.label || item.moduleLabel;
  const modTag      = mod?.tag || 'tag-research';
  const freshnessHtml = freshnessTag(item.date);
  const cardId = btoa(encodeURIComponent((item.title || '') + (item.date || ''))).slice(0, 20);
  const isRead = readIds.has(cardId);

  // #22 顯示乾淨域名而非 Google 重導址
  const displaySource = (item.source && item.source !== 'Google News')
    ? escHtml(item.source)
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

// ── 三合一過濾（#9排序 + #11關注 + 搜尋）──
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
      const hay = [card.title, card.summary, card.source, card.moduleLabel].join(' ').toLowerCase();
      return keywords.every(kw => hay.includes(kw));
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

  currentCards = cards; // 供 CSV 匯出用
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
    navigator.clipboard?.writeText(`${text}\n${link}`)
      .then(() => showToast('已複製到剪貼簿'))
      .catch(() => showToast('請手動複製連結'));
  }
}

// #30 摘要模式切換
function toggleDigest() {
  digestMode = !digestMode;
  document.getElementById('digest-btn')?.classList.toggle('active', digestMode);
  applyFilters();
}

// ── #31 統計圖表 ──
async function toggleChart() {
  chartVisible = !chartVisible;
  document.getElementById('chart-btn')?.classList.toggle('active', chartVisible);
  const panel = document.getElementById('chart-panel');

  if (!chartVisible) {
    panel.classList.add('hidden');
    return;
  }
  panel.classList.remove('hidden');

  // 惰性載入 Chart.js
  if (!window.Chart) {
    try {
      await new Promise((resolve, reject) => {
        const s = document.createElement('script');
        s.src = 'https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js';
        s.onload = resolve;
        s.onerror = reject;
        document.head.appendChild(s);
      });
    } catch {
      showToast('圖表載入失敗，請確認網路連線');
      chartVisible = false;
      panel.classList.add('hidden');
      return;
    }
  }

  renderModuleChart();
}

function renderModuleChart() {
  const canvas = document.getElementById('module-chart');
  if (!canvas || !window.Chart) return;

  // 計算各模組數量（使用 allCards 而非 currentCards，顯示全貌）
  const counts = {};
  MODULES.forEach(m => { counts[m.id] = 0; });
  allCards.forEach(c => { if (counts[c.moduleId] !== undefined) counts[c.moduleId]++; });

  const labels = MODULES.map(m => `${m.icon} ${m.label}`);
  const data   = MODULES.map(m => counts[m.id]);
  const COLORS = ['#f59e0b', '#00d4ff', '#10b981', '#ef4444', '#8b5cf6', '#ec4899', '#fb923c'];

  if (_chartInstance) _chartInstance.destroy();
  _chartInstance = new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: COLORS.map(c => c + 'aa'),
        borderColor: COLORS,
        borderWidth: 1,
        borderRadius: 6,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => ` ${ctx.raw} 則情報` } },
      },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,0.05)' },
          ticks: { color: '#64748b', font: { size: 11 } },
        },
        y: {
          grid: { display: false },
          ticks: { color: '#94a3b8', font: { size: 12 } },
        },
      },
    },
  });
}

// ── #17 匯出 ──
function exportCSV() {
  if (!currentCards.length) { showToast('目前沒有資料可匯出'); return; }
  const headers = ['標題', '摘要', '來源', '模組', '日期', '連結'];
  const rows = currentCards.map(c =>
    [c.title, c.summary, c.source, c.moduleLabel, c.date, c.url]
      .map(v => `"${String(v || '').replace(/"/g, '""')}"`)
  );
  const csv  = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' });
  const a    = document.createElement('a');
  a.href     = URL.createObjectURL(blob);
  a.download = `regen-intel-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(a.href);
  showToast(`已匯出 ${currentCards.length} 筆，可用 Excel 開啟`);
}

function printPage() {
  // 列印前在 top-bar 上標記時間（CSS ::after 讀取）
  document.querySelector('.top-bar')?.setAttribute('data-print-date',
    new Date().toLocaleString('zh-TW', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  );
  window.print();
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
  container.innerHTML = watchlist.length === 0
    ? `<span style="font-size:13px;color:var(--text-dim)">尚未新增任何關注關鍵字</span>`
    : watchlist.map((kw, i) =>
        `<span class="watch-chip">${escHtml(kw)}<button onclick="removeWatchword(${i})">×</button></span>`
      ).join('');
  document.getElementById('watch-filter-btn')?.classList.toggle('active', watchFilterActive);
}

function updateWatchBtn() {
  const btn = document.getElementById('watch-btn');
  if (!btn) return;
  btn.textContent = watchlist.length > 0 ? `⭐ 關注 (${watchlist.length})` : '⭐ 關注';
  btn.classList.toggle('active', watchFilterActive);
}

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
  setTimeout(() => { t.classList.remove('toast-show'); setTimeout(() => t.remove(), 300); }, 2800);
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
    return new Date(dateStr).toLocaleDateString('zh-TW', { month: 'numeric', day: 'numeric' });
  } catch { return dateStr.slice(5, 10); }
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  try {
    return new Date(dateStr).toLocaleDateString('zh-TW', { year: 'numeric', month: 'numeric', day: 'numeric' });
  } catch { return dateStr.slice(0, 10); }
}

// #22 取乾淨域名
function getDisplayDomain(url) {
  if (!url) return '';
  try { return new URL(url).hostname.replace(/^www\./, ''); }
  catch { return ''; }
}

function highlight(text, query) {
  if (!query || !text) return escHtml(text);
  const escaped  = escHtml(text);
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
