/* News Briefer tab — articles, daily brief, filters */

let currentFilter = 'all';
let newsSummaryPoll = null;

async function loadNews() {
    const data = await api('GET', '/api/news/articles');
    renderDailyBrief(data.daily_brief || '');
    renderNewsFilters(data.categories || []);
    renderArticles(data.articles || []);
}

async function refreshNews() {
    const btn = document.querySelector('#tab-news .btn');
    btn.textContent = '⏳ Fetching...';
    btn.disabled = true;

    const data = await api('POST', '/api/news/refresh');
    renderDailyBrief(data.daily_brief || '');
    renderNewsFilters(data.categories || []);
    renderArticles(data.articles || []);

    btn.textContent = '🔄 Refresh';
    btn.disabled = false;

    // Poll for summaries being generated in background
    if (newsSummaryPoll) clearInterval(newsSummaryPoll);
    newsSummaryPoll = setInterval(async () => {
        const updated = await api('GET', '/api/news/articles');
        renderDailyBrief(updated.daily_brief || '');
        renderArticles(updated.articles || []);
        // Stop polling once we have summaries
        const hasSummaries = (updated.articles || []).some(a => a.ai_summary && a.ai_summary.length > 0);
        if (hasSummaries && updated.daily_brief) {
            clearInterval(newsSummaryPoll);
            newsSummaryPoll = null;
        }
    }, 8000);

    // Stop polling after 3 minutes max
    setTimeout(() => {
        if (newsSummaryPoll) {
            clearInterval(newsSummaryPoll);
            newsSummaryPoll = null;
        }
    }, 180000);
}

function renderDailyBrief(brief) {
    document.getElementById('daily-brief').innerHTML = brief
        ? `<h3 style="margin-bottom: 8px;">📝 Daily Brief</h3><p>${brief}</p>`
        : '<p style="color: var(--text-secondary);">Daily brief not available. Click Refresh.</p>';
}

function renderNewsFilters(categories) {
    const container = document.getElementById('news-filters');
    const allCats = ['all', ...categories];
    container.innerHTML = allCats.map(cat => `
        <button class="filter-btn ${cat === currentFilter ? 'active' : ''}"
                onclick="filterNews('${cat}')">${cat === 'all' ? 'All' : cat.charAt(0).toUpperCase() + cat.slice(1)}</button>
    `).join('');
}

function filterNews(category) {
    currentFilter = category;
    loadNews();
}

function renderArticles(articles) {
    const container = document.getElementById('news-articles');
    const filtered = currentFilter === 'all'
        ? articles
        : articles.filter(a => a.category === currentFilter);

    if (!filtered.length) {
        container.innerHTML = '<p style="color: var(--text-secondary);">No articles available. Click Refresh to fetch news.</p>';
        return;
    }

    container.innerHTML = filtered.map(a => `
        <div class="article-card">
            ${a.image_url ? `<img src="${a.image_url}" alt="" loading="lazy" onerror="this.style.display='none'">` : ''}
            <div class="article-body">
                <div class="article-source">${a.source} • ${a.category} • ${a.published_at ? a.published_at.slice(0, 10) : ''}</div>
                <a href="${a.url}" target="_blank" style="text-decoration: none; color: var(--text-primary);">
                    <div class="article-title">${a.title}</div>
                </a>
                <div class="article-summary">${a.ai_summary || a.description || ''}</div>
            </div>
        </div>
    `).join('');
}
