// ── 密碼驗證 ──
// SHA-256("regen2025")
const PASS_HASH = '0ba4070b7679f2eb2e7db3dfa6951c26df25cdc7d324d2f6a6ec3d1b5bed1956';

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

// ── 載入資料 ──
async function loadAllData() {
  const container = document.getElementById('cards-container');
  container.innerHTML = `<div class="loading-spinner"><div class="spinner"></div><p>載入情報資料...</p></div>`;

  const results = await Promise.allSettled(MODULES.map(m => fetchModule(m)));

  allCards = [];
  let latestDate = null;

  results.forEach((r, i) => {
    if (r.status === 'fulfilled') {
      const items = r.value.items || [];
      items.forEach(item => {
        allCards.push({ ...item, moduleId: MODULES[i].id, moduleLabel: MODULES[i].label });
        if (item.date && (!latestDate || item.date > latestDate)) latestDate = item.date;
      });
    }
  });

  // 按日期排序
  allCards.sort((a, b) => (b.date || '').localeCompare(a.date || ''));

  document.getElementById('total-items').textContent = allCards.length;
  document.getElementById('last-update').textContent = `更新：${latestDate ? formatDate(latestDate) : '未知'}`;
  document.getElementById('data-date').textContent = new Date().toLocaleDateString('zh-TW');

  renderCards(allCards);
}

async function fetchModule(mod) {
  const res = await fetch(`${mod.file}?t=${Date.now()}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ── 渲染 ──
function renderCards(cards) {
  const container = document.getElementById('cards-container');

  if (cards.length === 0) {
    container.innerHTML = `<div class="empty-state"><p style="font-size:32px">📭</p><p>暫無情報資料</p></div>`;
    return;
  }

  if (currentModule === 'all') {
    // 按模組分組顯示
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
  const safeTitle = escHtml(item.title || '無標題');
  const safeSummary = escHtml(item.summary || '');
  const safeSource = escHtml(item.source || mod?.label || '');
  const dateStr = formatDate(item.date || '');

  return `<div class="intel-card" data-module="${mod?.id || item.moduleId}">
    <div class="card-top">
      <span class="card-tag ${mod?.tag || 'tag-research'}">${mod?.label || item.moduleLabel}</span>
      <span class="card-date">${dateStr}</span>
    </div>
    <div class="card-title">${safeTitle}</div>
    ${safeSummary ? `<div class="card-summary">${safeSummary}</div>` : ''}
    <div class="card-footer">
      <span class="card-source">${safeSource}</span>
      ${item.url ? `<a class="card-link" href="${escHtml(item.url)}" target="_blank" rel="noopener">查看原文 →</a>` : ''}
    </div>
  </div>`;
}

function filterModule(moduleId, btn) {
  currentModule = moduleId;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');

  const filtered = moduleId === 'all' ? allCards : allCards.filter(c => c.moduleId === moduleId);
  renderCards(filtered);
}

// ── 工具函數 ──
function formatDate(dateStr) {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('zh-TW', { month: 'numeric', day: 'numeric' });
  } catch { return dateStr.slice(0, 10); }
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── 自動載入 ──
if (sessionStorage.getItem('regen_auth') === '1') {
  loadAllData();
}
