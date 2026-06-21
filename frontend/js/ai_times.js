/* AI-Times tab — video grid display */

async function loadAITimes() {
    const data = await api('GET', '/api/ai-times/videos');
    renderVideos('ai-news-grid', data.news || []);
    renderVideos('ai-personality-grid', data.personality || []);
}

async function refreshAITimes() {
    const data = await api('POST', '/api/ai-times/refresh');
    renderVideos('ai-news-grid', data.news || []);
    renderVideos('ai-personality-grid', data.personality || []);
}

function formatViewCount(count) {
    if (!count) return '';
    if (count >= 1e6) return (count / 1e6).toFixed(1) + 'M views';
    if (count >= 1e3) return (count / 1e3).toFixed(1) + 'K views';
    return count + ' views';
}

function renderVideos(containerId, videos) {
    const container = document.getElementById(containerId);
    if (!videos.length) {
        container.innerHTML = '<p style="color: var(--text-secondary);">No videos loaded yet. Click Refresh.</p>';
        return;
    }
    container.innerHTML = videos.map(v => `
        <div class="video-card">
            <a href="${v.url}" target="_blank">
                <img src="${v.thumbnail}" alt="${v.title}" loading="lazy">
            </a>
            <div class="video-info">
                <div class="video-title">${v.title}</div>
                <div class="video-meta">
                    <span>${v.channel}</span>
                    <span>•</span>
                    <span>${v.published_at ? v.published_at.slice(0, 10) : ''}</span>
                    ${v.view_count ? `<span>•</span><span class="video-views">${formatViewCount(v.view_count)}</span>` : ''}
                </div>
                ${v.summary ? `<div class="video-summary">${v.summary}</div>` : ''}
            </div>
        </div>
    `).join('');
}
