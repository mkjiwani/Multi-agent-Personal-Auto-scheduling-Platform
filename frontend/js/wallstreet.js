/* Wallstreet Wolf tab — stocks, gainers, losers, commentary */

async function loadWallstreet() {
    const data = await api('GET', '/api/wallstreet/stocks');
    renderMarketStatus(data);
    renderGainersLosers(data.gainers || [], data.losers || []);
    renderWatchlist(data.stocks || []);
    renderCommentary(data.commentary || '');
    renderCurrenciesMetals(data.currencies || [], data.metals || []);
}

async function refreshStocks() {
    const data = await api('POST', '/api/wallstreet/refresh');
    renderMarketStatus(data);
    renderGainersLosers(data.gainers || [], data.losers || []);
    renderWatchlist(data.stocks || []);
    renderCommentary(data.commentary || '');
    renderCurrenciesMetals(data.currencies || [], data.metals || []);
}

function renderMarketStatus(data) {
    const banner = document.getElementById('market-status-banner');
    const dot = banner.querySelector('.status-dot');
    const text = document.getElementById('market-status-text');

    if (data.market_open) {
        dot.className = 'status-dot open';
        text.textContent = 'Market is OPEN — showing live prices';
    } else {
        dot.className = 'status-dot closed';
        const lastUpdated = data.last_updated ? new Date(data.last_updated).toLocaleString() : 'N/A';
        text.textContent = `Market is CLOSED — showing last closing prices (updated: ${lastUpdated})`;
    }
}

function renderGainersLosers(gainers, losers) {
    document.getElementById('gainers-list').innerHTML = gainers.map(s => `
        <div class="stock-row">
            <span class="stock-ticker">${s.ticker}</span>
            <span class="stock-price">$${s.price.toFixed(2)}</span>
            <span class="stock-change positive">+${s.change_percent.toFixed(2)}%</span>
        </div>
    `).join('') || '<p style="color: var(--text-secondary);">No data yet — click Refresh</p>';

    document.getElementById('losers-list').innerHTML = losers.map(s => `
        <div class="stock-row">
            <span class="stock-ticker">${s.ticker}</span>
            <span class="stock-price">$${s.price.toFixed(2)}</span>
            <span class="stock-change negative">${s.change_percent.toFixed(2)}%</span>
        </div>
    `).join('') || '<p style="color: var(--text-secondary);">No data yet — click Refresh</p>';
}

function renderWatchlist(stocks) {
    const container = document.getElementById('watchlist-table');
    if (!stocks.length) {
        container.innerHTML = '<p style="color: var(--text-secondary);">No stock data loaded. Click Refresh.</p>';
        return;
    }
    container.innerHTML = `
        <table style="width: 100%; border-collapse: collapse;">
            <thead>
                <tr style="border-bottom: 1px solid var(--border);">
                    <th style="text-align: left; padding: 8px;">Ticker</th>
                    <th style="text-align: right; padding: 8px;">Price</th>
                    <th style="text-align: right; padding: 8px;">Change</th>
                    <th style="text-align: right; padding: 8px;">Volume</th>
                </tr>
            </thead>
            <tbody>
                ${stocks.map(s => `
                    <tr style="border-bottom: 1px solid var(--border);">
                        <td style="padding: 8px; font-weight: 600;">${s.ticker}</td>
                        <td style="padding: 8px; text-align: right;">$${s.price.toFixed(2)}</td>
                        <td style="padding: 8px; text-align: right;" class="stock-change ${s.change_percent >= 0 ? 'positive' : 'negative'}">
                            ${s.change_percent >= 0 ? '+' : ''}${s.change_percent.toFixed(2)}%
                        </td>
                        <td style="padding: 8px; text-align: right; color: var(--text-secondary);">${formatVolume(s.volume)}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

function renderCommentary(commentary) {
    document.getElementById('market-commentary').innerHTML =
        commentary ? `<p>${commentary}</p>` : '<p style="color: var(--text-secondary);">Commentary not available yet.</p>';
}

function renderCurrenciesMetals(currencies, metals) {
    const container = document.getElementById('currencies-metals');
    const items = [...currencies, ...metals];
    if (!items.length) {
        container.innerHTML = '<p style="color: var(--text-secondary);">No data yet — click Refresh</p>';
        return;
    }
    container.innerHTML = items.map(item => `
        <div class="currency-card">
            <div class="symbol">${item.symbol}</div>
            <div class="price">$${item.price.toFixed(4)}</div>
            <div class="stock-change ${item.change_percent >= 0 ? 'positive' : 'negative'}">
                ${item.change_percent >= 0 ? '+' : ''}${item.change_percent.toFixed(2)}%
            </div>
        </div>
    `).join('');
}

function formatVolume(vol) {
    if (!vol) return 'N/A';
    if (vol >= 1e9) return (vol / 1e9).toFixed(1) + 'B';
    if (vol >= 1e6) return (vol / 1e6).toFixed(1) + 'M';
    if (vol >= 1e3) return (vol / 1e3).toFixed(1) + 'K';
    return vol.toString();
}
