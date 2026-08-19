async function startBot() {
    try {
        const res = await fetch('/api/start', { method: 'POST' });
        const data = await res.json();
        console.log("Bot Start Response:", data);
        fetchState(); // Instantly refresh UI
    } catch (e) {
        console.error("Error starting bot:", e);
    }
}

async function stopBot() {
    try {
        const res = await fetch('/api/stop', { method: 'POST' });
        const data = await res.json();
        console.log("Bot Stop Response:", data);
        fetchState();
    } catch (e) {
        console.error("Error stopping bot:", e);
    }
}

async function fetchState() {
    try {
        const response = await fetch('/api/state');
        const data = await response.json();
        updateDashboard(data);
    } catch (error) {
        console.error("Error fetching state:", error);
    }
}

function updateDashboard(data) {
    // 1. Update Status Indicator
    const indicator = document.getElementById('bot-status-indicator');
    const statusText = document.getElementById('bot-status-text');
    if (data.status === 'RUNNING') {
        indicator.className = 'status-indicator status-running';
        statusText.textContent = 'SYSTEM RUNNING';
    } else {
        indicator.className = 'status-indicator status-offline';
        statusText.textContent = 'SYSTEM OFFLINE';
    }

    // 2. Update Stats
    document.getElementById('total-balance').textContent = `$${data.balance.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    
    const pnlEl = document.getElementById('unrealized-pnl');
    const pnl = data.unrealized_pnl;
    pnlEl.textContent = `${pnl >= 0 ? '+' : ''}$${pnl.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    pnlEl.className = 'stat-value ' + (pnl >= 0 ? 'pnl-positive' : 'pnl-negative');

    const now = new Date();
    document.getElementById('last-update').textContent = now.toLocaleTimeString('en-US', { hour12: false });
    
    // 3. Update FVGs (Radar)
    const fvgContainer = document.getElementById('fvg-container');
    fvgContainer.innerHTML = '';
    
    let hasFVGs = false;
    for (const [symbol, fvgs] of Object.entries(data.fvgs)) {
        fvgs.forEach(fvg => {
            if (fvg.mitigated) return; // Only show active unmitigated FVGs
            hasFVGs = true;
            
            const card = document.createElement('div');
            card.className = 'fvg-card';
            const dirClass = fvg.dir === 'LONG' ? 'dir-long' : 'dir-short';
            
            card.innerHTML = `
                <div class="fvg-header">
                    <span class="fvg-symbol">${symbol}</span>
                    <span class="fvg-dir ${dirClass}">${fvg.dir}</span>
                </div>
                <div class="fvg-details">
                    <div>Entry zone: <span class="highlight">${fvg.bottom.toFixed(2)} - ${fvg.top.toFixed(2)}</span></div>
                    <div>Stop loss: <span class="highlight">${fvg.ob_stop.toFixed(2)}</span></div>
                    <div>Target: <span class="highlight">${fvg.target.toFixed(2)}</span></div>
                    <div style="margin-top: 8px; font-size: 0.8rem;">Detected: ${fvg.detected_at}</div>
                </div>
            `;
            fvgContainer.appendChild(card);
        });
    }
    
    if (!hasFVGs) {
        fvgContainer.innerHTML = data.status === 'RUNNING' 
            ? '<div class="empty-state">Scanning 1H charts for imbalances...</div>'
            : '<div class="empty-state">Bot Offline. Click START BOT to begin scanning.</div>';
    }

    // 4. Update Recent Trades History
    const historyContainer = document.getElementById('history-container');
    if (data.recent_trades && data.recent_trades.length > 0) {
        let tableHTML = `
            <table class="trade-table">
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>Symbol</th>
                        <th>Side</th>
                        <th>Price</th>
                        <th>Quantity</th>
                        <th>Realized PNL</th>
                    </tr>
                </thead>
                <tbody>
        `;
        data.recent_trades.forEach(t => {
            const dateStr = new Date(t.time).toLocaleString('en-US', {hour12: false, month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'});
            const pnlClass = t.realizedPnl > 0 ? 'pnl-positive' : (t.realizedPnl < 0 ? 'pnl-negative' : '');
            tableHTML += `
                <tr>
                    <td>${dateStr}</td>
                    <td style="color:white; font-weight:bold;">${t.symbol}</td>
                    <td class="${t.side === 'BUY' ? 'pnl-positive' : 'pnl-negative'}">${t.side}</td>
                    <td>$${t.price.toFixed(2)}</td>
                    <td>${t.qty}</td>
                    <td class="${pnlClass}">$${t.realizedPnl.toFixed(2)}</td>
                </tr>
            `;
        });
        tableHTML += `</tbody></table>`;
        historyContainer.innerHTML = tableHTML;
    } else {
        historyContainer.innerHTML = '<div class="empty-state">No recent closed trades found on the server.</div>';
    }

    // 5. Update Logs
    const logContainer = document.getElementById('log-container');
    if (data.logs && data.logs.length > 0) {
        logContainer.innerHTML = '';
        data.logs.forEach(logStr => {
            const match = logStr.match(/^\[(.*?)\] (.*)/);
            if (match) {
                const time = match[1];
                const msg = match[2];
                const div = document.createElement('div');
                div.className = 'log-line';
                if (msg.includes('🚀') || msg.includes('✅')) {
                    div.innerHTML = `<span class="log-time">[${time}]</span><span class="log-trade">${msg}</span>`;
                } else {
                    div.innerHTML = `<span class="log-time">[${time}]</span>${msg}`;
                }
                logContainer.appendChild(div);
            }
        });
    } else {
        logContainer.innerHTML = '<div class="log-line"><span class="log-time">[SYSTEM]</span> Awaiting initialization...</div>';
    }
}

// Fetch every 2 seconds
setInterval(fetchState, 2000);
fetchState(); // Initial fetch
