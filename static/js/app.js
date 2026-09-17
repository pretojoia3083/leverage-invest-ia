document.querySelectorAll('.nav-item[data-section]').forEach(item => {
    item.addEventListener('click', function(e) {
        e.preventDefault();
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        this.classList.add('active');
        document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
        document.getElementById('section-' + this.dataset.section).classList.add('active');
        document.getElementById('section-title').textContent = this.textContent.trim();
        if (this.dataset.section === 'robot') loadRobot();
        if (this.dataset.section === 'positions') refreshPositions();
        if (this.dataset.section === 'history') refreshHistory();
        if (this.dataset.section === 'connect') loadConnect();
        if (this.dataset.section === 'license') loadLicense();
    });
});

function toggleSidebar() { document.querySelector('.sidebar').classList.toggle('open'); }

async function api(url, method, body) {
    const opts = { method: method || 'GET', headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    return (await fetch(url, opts)).json();
}

// DASHBOARD
async function refreshDashboard() {
    try {
        const data = await api('/api/status');
        if (data.error) return;
        document.getElementById('statusDot').className = 'status-dot ' + (data.license_valid ? 'online' : 'offline');
        document.getElementById('statBalance').textContent = '$' + (data.balance || 0).toFixed(2);
        document.getElementById('statEquity').textContent = '$' + (data.equity || 0).toFixed(2);
        const profit = data.profit || 0;
        const profitEl = document.getElementById('statProfit');
        profitEl.textContent = '$' + profit.toFixed(2);
        profitEl.className = 'stat-value ' + (profit >= 0 ? 'text-profit-pos' : 'text-profit-neg');
        document.getElementById('statPositions').textContent = data.positions || 0;
        const robotEl = document.getElementById('statRobot');
        robotEl.textContent = data.robot_active ? 'LIGADO' : 'DESLIGADO';
        robotEl.className = 'stat-value ' + (data.robot_active ? 'text-success' : 'text-off');
        document.getElementById('statWinLoss').textContent = (data.wins || 0) + ' / ' + (data.losses || 0);
    } catch (e) {}
}

// LICENSE
async function loadLicense() {
    const data = await api('/api/status');
    document.getElementById('licenseKey').value = data.license_key || 'Sem chave';
    const expires = data.license_expires;
    document.getElementById('licenseExpires').value = expires ? new Date(expires).toLocaleDateString('pt-BR') : '-';
    const statusEl = document.getElementById('licenseStatus');
    if (data.license_valid) {
        statusEl.innerHTML = '<span class="badge badge-buy">ATIVA</span>';
    } else {
        statusEl.innerHTML = '<span class="badge badge-sell">INATIVA / EXPIRADA</span>';
    }
}

// ROBO
async function loadRobot() {
    const data = await api('/api/status');
    document.getElementById('robotWarning').style.display = data.license_valid ? 'none' : 'block';
    document.getElementById('robotNoMt5').style.display = (data.license_valid && !data.connected) ? 'block' : 'none';
    if (data.robot_symbol) document.getElementById('robotSymbolSelect').value = data.robot_symbol;
    updateRobotUI(data.robot_active, data.robot_symbol);
}

function updateRobotUI(active, symbol) {
    document.getElementById('btnStartRobot').style.display = active ? 'none' : 'block';
    document.getElementById('btnStopRobot').style.display = active ? 'block' : 'none';
    const ind = document.getElementById('robotIndicator');
    const txt = document.getElementById('robotStatusText');
    const sym = document.getElementById('robotCurrentSymbol');
    if (active) {
        ind.className = 'robot-indicator on';
        txt.textContent = 'LIGADO';
        txt.className = 'robot-label text-success';
        sym.textContent = symbol || 'XAUUSD';
    } else {
        ind.className = 'robot-indicator off';
        txt.textContent = 'DESLIGADO';
        txt.className = 'robot-label text-off';
        sym.textContent = symbol || '-';
    }
}

async function startRobot() {
    const symbol = document.getElementById('robotSymbolSelect').value;
    const data = await api('/api/robot/start', 'POST', { symbol });
    if (data.error) { alert(data.error); return; }
    updateRobotUI(true, symbol);
    refreshDashboard();
}

async function stopRobot() {
    await api('/api/robot/stop', 'POST');
    const symbol = document.getElementById('robotSymbolSelect').value;
    updateRobotUI(false, symbol);
    refreshDashboard();
}

// POSITIONS
async function refreshPositions() {
    const data = await api('/api/status');
    const tbody = document.getElementById('positionsTable');
    if (!data.positions_list || data.positions_list.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center text-dim">Nenhuma posicao</td></tr>';
        return;
    }
    tbody.innerHTML = data.positions_list.map(p => '<tr><td>' + p.symbol + '</td><td><span class="badge ' + (p.type == 'COMPRA' ? 'badge-buy' : 'badge-sell') + '">' + p.type + '</span></td><td>' + p.volume + '</td><td>' + p.price_open.toFixed(2) + '</td><td class="' + (p.profit >= 0 ? 'text-success' : 'text-danger') + '">$' + p.profit.toFixed(2) + '</td><td>' + p.sl.toFixed(2) + '</td><td>' + p.tp.toFixed(2) + '</td></tr>').join('');
}

// HISTORY
async function refreshHistory() {
    const data = await api('/api/status');
    const tbody = document.getElementById('historyTable');
    const trades = (data.trades || []).reverse();
    if (trades.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-dim">Nenhuma operacao</td></tr>';
        return;
    }
    tbody.innerHTML = trades.map(t => '<tr><td>' + (t.created_at ? new Date(t.created_at).toLocaleString('pt-BR') : '-') + '</td><td>' + t.symbol + '</td><td><span class="badge ' + (t.direction === 'buy' ? 'badge-buy' : 'badge-sell') + '">' + (t.direction === 'buy' ? 'COMPRA' : 'VENDA') + '</span></td><td>' + t.lot + '</td><td class="' + ((t.profit || 0) >= 0 ? 'text-success' : 'text-danger') + '">$' + (t.profit || 0).toFixed(2) + '</td></tr>').join('');
}

// CONNECT
async function loadConnect() {
    const data = await api('/api/status');
    if (data.connected) {
        document.getElementById('mt5ConnectedSection').style.display = 'block';
        document.getElementById('mt5DisconnectedSection').style.display = 'none';
        document.getElementById('mt5ConnectedInfo').textContent = 'Conta #' + data.mt5_account + ' | Servidor: ' + data.mt5_server;
    } else {
        document.getElementById('mt5ConnectedSection').style.display = 'none';
        document.getElementById('mt5DisconnectedSection').style.display = 'block';
    }
}

async function connectMT5() {
    const account = document.getElementById('mt5Account').value.trim();
    const server = document.getElementById('mt5Server').value.trim();
    if (!account || !server) { alert('Preencha todos os campos'); return; }
    const r = await api('/api/connect-mt5', 'POST', { account, server });
    if (r.error) { alert(r.error); return; }
    alert(r.message);
    loadConnect();
    refreshDashboard();
}

async function disconnectMT5() {
    if (!confirm('Desvincular conta?')) return;
    await api('/api/disconnect-mt5', 'POST');
    loadConnect();
    refreshDashboard();
}

document.addEventListener('DOMContentLoaded', () => {
    refreshDashboard();
    setInterval(refreshDashboard, 5000);
});
