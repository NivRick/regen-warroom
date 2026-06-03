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

// 自動登入（session 內）
if (sessionStorage.getItem('regen_auth') === '1') {
  document.getElementById('login-screen').classList.add('hidden');
  document.getElementById('main-app').classList.remove('hidden');
}

// ── 模組定義 ──
const MODULES = [
  { id: 'taiwan',     label: '台灣市場',  icon: '🇹🇼', tag: 'tag-taiwan',     file: 'data/taiwan-market.json' },
  { id: 'research',   label: '臨床突破',  icon: '🔬', tag: 'tag-research',    file: 'data/global-research.json' },
  { id: 'apac',       label: '亞太合作',  icon: '🌏', tag: 'tag-apac',        file: 'data/asia-pacific.json' },
  { id: 'regulation', label: '法規動態',  icon: '⚖️', tag: 'tag-regulation',  file: 'data/regulations.json' },
  { id: 'funding',    label: '資金動向',  icon: '💰', tag: 'tag-funding',     file: 'data/funding.json' },
  { id: 'tourism',    label: '醫療旅遊',  icon: '✈️', tag: 'tag-tourism',     file: 'data/medical-tourism.json' },
];

let allCards = [];
let currentModule = 'all';
// #25 已讀標記 — 從 localStorage 讀取
const READ_KEY = 'regen_read_ids';
let readIds = new Set(JSON.parse(localStorage.getItem(READ_KEY) || '[]'));

function saveReadIds() {
  localStorage.setItem(READ_KEY, JSON.stringify([...readIds]));
}

// ── 載入資料 ──
async function loadAllData() {
  const container = document.getElementById('cards-container');
  // #26 進度條
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
      // #27 記錄載入失敗的模組
      failedModules.push(MODULES[i].label);
    }
  });

  // 按日期排序（新到舊）
  allCards.sort((a, b) => (b.date || '').localeCompare(a.date || ''));

  document.getElementById('total-items').textContent = allCards.length;
  document.getElementById('last-update').textContent = `更新：${latestDate ? formatDate(latestDate) : '未知'}`;
  document.getElementById('data-date').textContent = new Date().toLocaleDateString('zh-TW');

  // #27 錯誤提示 UI
  if (failedModules.length > 0) {
    showErrorBanner(`⚠️ 以下模組載入失敗：${failedModules.join('、')}，其他資料正常顯示。`);
  }

  renderCards(allCards);
}

async function fetchModule(mod) {
  const res = await fetch(`${mod.file}?t=${Date.now()}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// #27 錯誤橫幅
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
function renderCards(cards) {
  const container = document.getElementById('cards-container');

  if (cards.length === 0) {
    container.innerHTML = `<div class="empty-state"><p style="font-size:32px">📭</p><p>暫無情報資料</p></div>`;
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
      html += `<div class="module-header">
        <span class="module-icon">${m.icon}</span>
        <span class="module-title">${m.label}</span>
        <span class="module-count">${items.length}</span>
      </div>`;
      html += items.slice(0, 5).map(c => cardHTML(c, m)).join('');
    });
    container.innerHTML = html;
  } else {
    const mod = MODULES.find(m => m.id === currentModule);
    container.innerHTML = cards.map(c => cardHTML(c, mod)).join('');
  }
}

function cardHTML(item, mod) {
  const safeTitle   = escHtml(decodeEntities(item.title || '無標題'));
  const safeSummary = escHtml(decodeEntities(item.summary || ''));
  const safeSource  = escHtml(item.source || mod?.label || '');
  const moduleId    = mod?.id || item.moduleId;
  const moduleLabel = mod?.label || item.moduleLabel;
  const modTag      = mod?.tag || 'tag-research';

  // #12 新鮮度
  const freshnessHtml = freshnessTag(item.date);

  // 產生唯一 ID（用來追蹤已讀）
  const cardId = btoa(encodeURIComponent((item.title || '') + (item.date || ''))).slice(0, 20);
  const isRead = readIds.has(cardId);

  // #24 分享按鈕
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
      <span class="card-source">${safeSource}</span>
      ${item.url ? `<a class="card-link" href="${escHtml(item.url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">查看原文 →</a>` : ''}
    </div>
  </div>`;
}

// #4 Tab 切換：修正跳位問題
function filterModule(moduleId, btn) {
  currentModule = moduleId;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');

  const filtered = moduleId === 'all' ? allCards : allCards.filter(c => c.moduleId === moduleId);
  renderCards(filtered);

  // 捲回頂部（修正 Tab 跳位）
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// #25 標記已讀
function markRead(cardId, el) {
  if (!readIds.has(cardId)) {
    readIds.add(cardId);
    saveReadIds();
    el.classList.add('is-read');
  }
}

// #24 分享功能（Web Share API）
function shareCard(event, cardId) {
  event.stopPropagation();
  const card = document.querySelector(`[data-card-id="${cardId}"]`);
  if (!card) return;
  const title = card.querySelector('.card-title')?.textContent || '';
  const source = card.querySelector('.card-source')?.textContent || '';
  const link = card.querySelector('.card-link')?.href || location.href;

  const text = `【再生醫療情報】\n${title}\n來源：${source}`;

  if (navigator.share) {
    navigator.share({ title, text, url: link }).catch(() => {});
  } else {
    // 降級：複製到剪貼簿
    navigator.clipboard?.writeText(`${text}\n${link}`).then(() => {
      showToast('已複製到剪貼簿');
    }).catch(() => {
      showToast('請手動複製連結');
    });
  }
}

// Toast 提示
function showToast(msg) {
  const t = document.createElement('div');
  t.className = 'toast';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.classList.add('toast-show'), 10);
  setTimeout(() => { t.classList.remove('toast-show'); setTimeout(() => t.remove(), 300); }, 2500);
}

// ── 工具函數 ──

// #12 新鮮度標籤
function freshnessTag(dateStr) {
  if (!dateStr) return '';
  const days = Math.floor((Date.now() - new Date(dateStr).getTime()) / 86400000);
  if (days < 0) return '';
  if (days === 0) return `<span class="fresh-tag fresh-today">今天</span>`;
  if (days <= 2) return `<span class="fresh-tag fresh-new">${days}天前</span>`;
  if (days <= 7) return `<span class="fresh-tag fresh-week">${days}天前</span>`;
  return `<span class="fresh-tag fresh-old">${days}天前</span>`;
}

// 短日期（月/日）
function formatDateShort(dateStr) {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('zh-TW', { month: 'numeric', day: 'numeric' });
  } catch { return dateStr.slice(5, 10); }
}

// 長日期（年/月/日）
function formatDate(dateStr) {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('zh-TW', { year: 'numeric', month: 'numeric', day: 'numeric' });
  } catch { return dateStr.slice(0, 10); }
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
