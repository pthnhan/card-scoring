/* ============================================================
   Card Scoring – main.js
   ============================================================ */

// ── Player color palette ─────────────────────────────────────
const COLORS = [
    { bg: '#6c63ff22', text: '#a78bfa', solid: '#6c63ff' },
    { bg: '#f43f5e22', text: '#fb7185', solid: '#f43f5e' },
    { bg: '#22d3a022', text: '#34d399', solid: '#22d3a0' },
    { bg: '#fbbf2422', text: '#fcd34d', solid: '#fbbf24' },
    { bg: '#38bdf822', text: '#7dd3fc', solid: '#38bdf8' },
    { bg: '#e879f922', text: '#f0abfc', solid: '#e879f9' },
    { bg: '#fb923c22', text: '#fdba74', solid: '#fb923c' },
    { bg: '#a3e63522', text: '#bef264', solid: '#a3e635' },
];
function playerColor(i) { return COLORS[i % COLORS.length]; }
function initials(name) {
    return name.trim().split(/\s+/).map(w => w[0]).join('').toUpperCase().slice(0, 2) || '?';
}

// ── State ─────────────────────────────────────────────────────
let state = null;
let playerCount = 4;
let manualAdminSelected = null;
let currentAdminSelected = null;
const page = document.body?.dataset?.page || '';

// ── Initialise setup view ─────────────────────────────────────
window.onload = async () => {
    if (page === 'setup') {
        renderPlayerInputs();
        onAdminModeChange();
    } else if (page === 'game') {
        const restored = await tryRestoreState();
        if (!restored) window.location.href = '/setup';
    }
};

function changeCount(delta) {
    playerCount = Math.max(2, Math.min(10, playerCount + delta));
    document.getElementById('player-count-display').textContent = playerCount;
    renderPlayerInputs();
    onAdminModeChange(); // refresh selects that depend on names
}

function renderPlayerInputs() {
    const container = document.getElementById('player-inputs');
    const existing = container.querySelectorAll('.player-row');
    const oldData = [];
    existing.forEach(row => {
        oldData.push({
            name: row.querySelector('.player-name-input').value,
            score: row.querySelector('.player-score-input').value,
        });
    });

    container.innerHTML = '';
    for (let i = 0; i < playerCount; i++) {
        const c = playerColor(i);
        const row = document.createElement('div');
        row.className = 'player-row';
        row.innerHTML = `
      <div class="player-avatar" style="background:${c.bg};color:${c.text}">P${i + 1}</div>
      <input type="text"
             class="input-field player-name-input"
             placeholder="Người chơi ${i + 1}"
             value="${(oldData[i] && oldData[i].name) || `P${i + 1}`}"
             oninput="syncAdminSelects()" />
      <input type="number"
             class="input-field player-score-input"
             placeholder="0"
             value="${(oldData[i] && oldData[i].score) || 0}"
             style="width:88px;text-align:center;" />
    `;
        container.appendChild(row);
    }
    syncAdminSelects();
}

function getSetupPlayers() {
    const rows = document.querySelectorAll('.player-row');
    return Array.from(rows).map((row, i) => ({
        name: row.querySelector('.player-name-input').value.trim() || `P${i + 1}`,
        initial: parseInt(row.querySelector('.player-score-input').value) || 0,
    }));
}

function onAdminModeChange() {
    const mode = document.querySelector('input[name="admin-mode"]:checked')?.value || 'none';
    document.getElementById('admin-sub-fixed').classList.toggle('hidden', mode !== 'fixed');
    document.getElementById('admin-sub-rotating').classList.toggle('hidden', mode !== 'rotating');
    syncAdminSelects();
}

function syncAdminSelects() {
    const players = getSetupPlayers();
    const names = players.map(p => p.name);

    ['fixed-admin-select', 'rotating-start-select'].forEach(id => {
        const sel = document.getElementById(id);
        const prev = sel.value;
        sel.innerHTML = names.map((n, i) => `<option value="${i}">${n}</option>`).join('');
        if (names.includes(prev)) sel.value = prev;
    });
}

// ── Start game ────────────────────────────────────────────────
async function startGame() {
    const players = getSetupPlayers();
    const mode = document.querySelector('input[name="admin-mode"]:checked').value;

    let adminConfig = {};
    if (mode === 'fixed') {
        adminConfig = { fixed_index: parseInt(document.getElementById('fixed-admin-select').value) };
    } else if (mode === 'rotating') {
        adminConfig = {
            every: parseInt(document.getElementById('rotating-every').value) || 1,
            start: parseInt(document.getElementById('rotating-start-select').value) || 0,
        };
    }

    const res = await api('/api/start', { players, admin_mode: mode, admin_config: adminConfig });
    if (res.ok) {
        window.location.href = '/game';
    } else {
        alert(res.error || 'Không thể bắt đầu ván');
    }
}

async function joinGame() {
    const input = document.getElementById('join-code');
    const code = (input.value || '').trim().toUpperCase();
    if (!code) {
        alert('Vui lòng nhập mã ván');
        return;
    }
    const res = await api('/api/join', { code });
    if (res.ok) {
        window.location.href = '/game';
    } else {
        alert(res.error || 'Không thể tham gia ván');
    }
}

// ── Apply server state ────────────────────────────────────────
function applyState(s) {
    state = s;
    updateGameCode();
    updateRoundBadge();
    updateAdminBadge();
    refreshScoringInputs();
    renderHistoryTable();
    // keep summary updated if open
    const overlay = document.getElementById('summary-overlay');
    if (!overlay.classList.contains('hidden')) renderSummaryTable();
}

function updateGameCode() {
    const label = document.getElementById('game-code-label');
    if (!label) return;
    if (state && state.game_code) {
        label.textContent = `Mã ván: ${state.game_code}`;
        label.classList.remove('hidden');
    } else {
        label.textContent = '';
        label.classList.add('hidden');
    }
}

function updateRoundBadge() {
    document.getElementById('round-badge').textContent = `Lượt ${state.round_number}`;
}

function updateAdminBadge() {
    const badge = document.getElementById('admin-badge');
    const label = document.getElementById('admin-name-label');
    const mode = state.admin_mode;

    document.getElementById('manual-admin-section').classList.add('hidden');

    if (mode === 'none') {
        badge.classList.add('hidden');
        currentAdminSelected = null;
        return;
    }
    badge.classList.remove('hidden');

    if (mode === 'manual') {
        badge.classList.add('hidden');
        const sec = document.getElementById('manual-admin-section');
        sec.classList.remove('hidden');
        const sel = document.getElementById('manual-admin-select');
        const prev = manualAdminSelected || sel.value;
        sel.innerHTML = state.players.map(n => `<option value="${n}">${n}</option>`).join('');
        if (prev && state.players.includes(prev)) {
            sel.value = prev;
        } else {
            sel.value = state.players[0] || '';
        }
        manualAdminSelected = sel.value;
        currentAdminSelected = sel.value;
    } else {
        const sec = document.getElementById('manual-admin-section');
        sec.classList.remove('hidden');
        const sel = document.getElementById('manual-admin-select');
        sel.innerHTML = state.players.map(n => `<option value="${n}">${n}</option>`).join('');
        sel.value = state.next_admin || state.players[0] || '';
        currentAdminSelected = sel.value;
        label.textContent = currentAdminSelected || '—';
    }
}

function getCurrentAdmin() {
    const mode = state.admin_mode;
    if (mode === 'none') return null;
    if (currentAdminSelected) return currentAdminSelected;
    const sel = document.getElementById('manual-admin-select');
    return sel ? sel.value : state.next_admin;
}

function onManualAdminChange() {
    const sel = document.getElementById('manual-admin-select');
    const mode = state?.admin_mode;
    currentAdminSelected = sel ? sel.value : null;
    if (mode === 'manual') manualAdminSelected = currentAdminSelected;
    const label = document.getElementById('admin-name-label');
    if (label && mode !== 'manual') label.textContent = currentAdminSelected || '—';
    refreshScoringInputs();
}

function refreshScoringInputs() {
    const admin = getCurrentAdmin();
    const container = document.getElementById('scoring-inputs');
    container.innerHTML = '';
    const hasAdmin = admin !== null;

    state.players.forEach((name, i) => {
        const c = playerColor(i);
        const isAdmin = name === admin;
        const row = document.createElement('div');
        row.className = 'score-row';
        row.dataset.player = name;

        const labelHtml = `
      <div class="score-player-label">
        <div class="score-avatar" style="background:${c.bg};color:${c.text}">${initials(name)}</div>
        <span>${name}</span>
      </div>`;

        if (isAdmin) {
            row.innerHTML = labelHtml + `<div class="score-admin-tag">👑 Admin</div>`;
        } else if (!hasAdmin) {
            row.innerHTML = labelHtml + `
        <div class="score-input-wrap">
          <input type="number" class="input-field score-input"
                 id="score-${i}" data-player="${name}"
                 value="0" step="1" />
        </div>`;
        } else {
            row.innerHTML = labelHtml + `
        <div class="score-input-wrap admin-vs">
          <input type="number" class="input-field score-input"
                 data-player="${name}" value="0" step="1" min="0" />
          <select class="input-field outcome-select" data-player="${name}" onchange="onOutcomeChange(this)">
            <option value="win">Thua</option>
            <option value="draw" selected>Hòa</option>
            <option value="lose">Thắng</option>
          </select>
        </div>`;
        }
        container.appendChild(row);
    });

    // Toggle action buttons
    document.getElementById('admin-actions').classList.toggle('hidden', admin === null);
    document.getElementById('no-admin-actions').classList.toggle('hidden', admin !== null);
    clearError();
}

// ── Submit round: NO admin ─────────────────────────────────────
async function submitRoundNoAdmin() {
    const scores = collectScores();
    if (scores === null) return;

    const total = Object.values(scores).reduce((a, b) => a + b, 0);
    if (total !== 0) {
        showError(`Tổng điểm phải = 0, nhưng hiện tại = ${total > 0 ? '+' : ''}${total}`);
        return;
    }

    const res = await api('/api/round', { scores });
    if (res.ok) applyState(res.state);
    else showError(res.error || 'Lỗi không xác định');
}

// ── Submit round: WITH admin ───────────────────────────────────
function onOutcomeChange(sel) {
    const wrap = sel.closest('.score-input-wrap');
    const input = wrap ? wrap.querySelector('.score-input') : null;
    if (!input) return;
    const isDraw = sel.value === 'draw';
    input.disabled = isDraw;
    if (isDraw) input.value = 0;
}

async function submitRoundAdmin() {
    const admin = getCurrentAdmin();
    if (!admin) {
        showError('Không có Admin cho lượt này');
        return;
    }

    const scores = {};
    let adminDelta = 0;

    const rows = document.querySelectorAll('.score-row');
    for (const row of rows) {
        const name = row.dataset.player;
        if (!name || name === admin) continue;

        const outcomeSel = row.querySelector('.outcome-select');
        const input = row.querySelector('.score-input');
        if (!outcomeSel || !input) continue;

        const outcome = outcomeSel.value;
        let amount = 0;
        if (outcome !== 'draw') {
            const raw = parseInt(input.value);
            if (isNaN(raw) || !Number.isInteger(raw)) {
                showError(`Điểm phải là số nguyên cho ${name}`);
                return;
            }
            if (raw < 0) {
                showError(`Điểm cược không thể nhỏ hơn 0 cho ${name}`);
                return;
            }
            amount = Math.abs(raw);
        }

        if (outcome === 'win') {
            scores[name] = -amount;
            adminDelta += amount;
        } else if (outcome === 'lose') {
            scores[name] = amount;
            adminDelta -= amount;
        } else {
            scores[name] = 0;
        }
    }

    scores[admin] = adminDelta;

    const res = await api('/api/round', { scores, admin });
    if (res.ok) applyState(res.state);
    else showError(res.error || 'Lỗi không xác định');
}

function collectScores(skipPlayer = null) {
    const inputs = document.querySelectorAll('.score-input');
    const scores = {};
    for (const inp of inputs) {
        const name = inp.dataset.player;
        if (name === skipPlayer) continue;
        const val = parseInt(inp.value);
        if (isNaN(val) || !Number.isInteger(val)) {
            showError(`Điểm phải là số nguyên cho ${name}`);
            return null;
        }
        scores[name] = val;
    }
    return scores;
}

// ── Undo ──────────────────────────────────────────────────────
async function undoRound() {
    const res = await api('/api/undo', {});
    if (res.ok) applyState(res.state);
    else alert(res.error);
}

// ── Reset ─────────────────────────────────────────────────────
function resetGame() {
    if (!confirm('Bạn có chắc muốn bắt đầu lại từ đầu?')) return;
    api('/api/reset', {}).then(() => {
        state = null;
        window.location.href = '/setup';
    });
}

// ── Render history table ───────────────────────────────────────
function renderHistoryTable() {
    const rounds = state.rounds;
    const players = state.players;

    const empty = document.getElementById('history-empty');
    const table = document.getElementById('history-table');

    if (rounds.length === 0) {
        empty.style.display = 'block';
        table.style.display = 'none';
        return;
    }
    empty.style.display = 'none';
    table.style.display = 'table';

    // Header
    const thead = document.getElementById('history-thead');
    let headerHtml = '<tr><th>Lượt</th>';
    players.forEach((name, i) => {
        const c = playerColor(i);
        headerHtml += `<th><span style="color:${c.text}">${name}</span></th>`;
    });
    headerHtml += '</tr>';
    thead.innerHTML = headerHtml;

    // Rows
    const tbody = document.getElementById('history-tbody');
    let bodyHtml = '';
    let runningTotals = {};
    players.forEach(n => {
        runningTotals[n] = state.players.indexOf(n) >= 0
            ? (state.rounds[0] ? 0 : 0) : 0;
    });

    // Re-init from initial scores — we need full totals per round
    const initials_map = {};
    // We can't get initial scores from state here, so use totals minus all rounds
    // Compute initial totals from totals - sum of all round deltas
    players.forEach(n => {
        const allDeltas = rounds.reduce((sum, r) => sum + (r.scores[n] || 0), 0);
        initials_map[n] = (state.totals[n] || 0) - allDeltas;
    });

    let runningMap = { ...initials_map };

    rounds.forEach((rnd, idx) => {
        const adminMark = rnd.admin ? `<div class="admin-badge" style="display:inline-block;margin-top:4px;font-size:0.72rem;">👑 ${rnd.admin}</div>` : '';
        bodyHtml += `<tr>
      <td class="td-round">${idx + 1}${adminMark ? '<br>' + adminMark : ''}</td>`;
        players.forEach(name => {
            const delta = rnd.scores[name] ?? null;
            runningMap[name] = (runningMap[name] || 0) + (delta || 0);

            if (delta === null) {
                bodyHtml += `<td class="score-zero">—</td>`;
            } else if (name === rnd.admin) {
                const cls = delta > 0 ? 'score-pos' : delta < 0 ? 'score-neg' : 'score-zero';
                bodyHtml += `<td class="${cls}">${delta > 0 ? '+' : ''}${delta}</td>`;
            } else {
                const cls = delta > 0 ? 'score-pos' : delta < 0 ? 'score-neg' : 'score-zero';
                const sign = delta > 0 ? '+' : '';
                bodyHtml += `<td class="${cls}">${sign}${delta}</td>`;
            }
        });
        bodyHtml += '</tr>';
    });

    tbody.innerHTML = bodyHtml;
}

// ── Summary table ─────────────────────────────────────────────
function toggleSummary() {
    const overlay = document.getElementById('summary-overlay');
    overlay.classList.toggle('hidden');
    if (!overlay.classList.contains('hidden')) renderSummaryTable();
}
function closeSummaryOnBg(e) {
    if (e.target === document.getElementById('summary-overlay')) toggleSummary();
}

function renderSummaryTable() {
    const sorted = [...state.players].sort((a, b) => (state.totals[b] || 0) - (state.totals[a] || 0));
    const tbody = document.getElementById('summary-tbody');
    tbody.innerHTML = sorted.map((name, rank) => {
        const idx = state.players.indexOf(name);
        const c = playerColor(idx);
        const t = state.totals[name] || 0;
        const cls = t > 0 ? 'score-pos' : t < 0 ? 'score-neg' : 'score-zero';
        const rankClass = rank === 0 ? 'rank-1' : rank === 1 ? 'rank-2' : rank === 2 ? 'rank-3' : 'rank-n';
        return `
      <tr>
        <td><div class="rank-badge ${rankClass}">${rank + 1}</div></td>
        <td>
          <div style="display:flex;align-items:center;gap:10px;">
            <div class="chip-avatar" style="background:${c.bg};color:${c.text}">${initials(name)}</div>
            <span class="summary-name">${name}</span>
          </div>
        </td>
        <td class="summary-score ${cls}">${t > 0 ? '+' : ''}${t}</td>
      </tr>`;
    }).join('');
}

// ── Error helpers ─────────────────────────────────────────────
function showError(msg) {
    const box = document.getElementById('score-error');
    box.textContent = '⚠️ ' + msg;
    box.classList.remove('hidden');
    // re-trigger animation
    box.style.animation = 'none';
    box.offsetHeight; // reflow
    box.style.animation = '';
}
function clearError() {
    document.getElementById('score-error').classList.add('hidden');
}

// ── API helper ────────────────────────────────────────────────
async function api(path, body) {
    try {
        const res = await fetch(path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        return await res.json();
    } catch (e) {
        return { ok: false, error: e.message };
    }
}

async function tryRestoreState() {
    try {
        const res = await fetch('/api/state', { method: 'GET' });
        const data = await res.json();
        if (data && data.started) {
            applyState(data);
            return true;
        }
        updateGameCode();
        return false;
    } catch (e) {
        return false;
    }
}
