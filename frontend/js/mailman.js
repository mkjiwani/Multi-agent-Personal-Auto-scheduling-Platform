/* Mailman tab — email categories and list */

let mailmanPoll = null;

async function loadMailman() {
    const data = await api('GET', '/api/mailman/emails');
    renderEmailCategories(data.categories || {});
    renderEmailList(data.emails || []);
}

async function scanMailbox() {
    const btn = document.querySelector('#tab-mailman .btn');
    btn.textContent = '⏳ Scanning...';
    btn.disabled = true;

    const data = await api('POST', '/api/mailman/scan');
    renderEmailCategories(data.categories || {});
    renderEmailList(data.emails || []);

    btn.textContent = '📥 Scan Now';
    btn.disabled = false;

    // Poll for classifications being done in background
    if (mailmanPoll) clearInterval(mailmanPoll);
    mailmanPoll = setInterval(async () => {
        const updated = await api('GET', '/api/mailman/emails');
        renderEmailCategories(updated.categories || {});
        renderEmailList(updated.emails || []);
        // Stop if no more "Classifying..." entries
        const stillClassifying = (updated.emails || []).some(e => e.classification === 'Classifying...');
        if (!stillClassifying) {
            clearInterval(mailmanPoll);
            mailmanPoll = null;
        }
    }, 6000);

    // Max 2 min polling
    setTimeout(() => {
        if (mailmanPoll) { clearInterval(mailmanPoll); mailmanPoll = null; }
    }, 120000);
}

function renderEmailCategories(categories) {
    const container = document.getElementById('email-categories');
    if (!Object.keys(categories).length) {
        container.innerHTML = '<p style="color: var(--text-secondary);">No emails scanned yet. Click Scan Now.</p>';
        return;
    }
    container.innerHTML = Object.entries(categories).map(([cat, count]) => `
        <div class="category-badge">
            ${cat}: <span class="count">${count}</span>
        </div>
    `).join('');
}

function renderEmailList(emails) {
    const container = document.getElementById('email-list');
    if (!emails.length) {
        container.innerHTML = '';
        return;
    }
    container.innerHTML = emails.slice(0, 20).map(e => {
        const urgentClass = e.classification === 'Urgent' ? 'urgent' :
                           e.classification === 'Action Required' ? 'action' : '';
        const dateStr = e.received_at ? formatEmailDate(e.received_at) : '';
        return `
        <div class="email-item ${urgentClass}">
            <span class="email-badge">${e.classification || 'Other'}</span>
            ${e.is_key_person ? '<span class="email-badge" style="background: var(--accent-yellow); color: #000;">⭐ Key Person</span>' : ''}
            <div class="email-subject">${e.subject}</div>
            <div class="email-sender">${e.sender}${dateStr ? ' • <span style="color:var(--accent-cyan);">' + dateStr + '</span>' : ''}</div>
            <div class="email-summary">${e.summary || e.snippet || ''}</div>
        </div>
        `;
    }).join('');
}

function formatEmailDate(dateStr) {
    if (!dateStr) return '';
    try {
        // Handle RFC 2822 format: "Mon, 25 May 2026 20:53:18 -0700"
        const d = new Date(dateStr);
        if (isNaN(d.getTime())) {
            // Fallback: show raw date portion
            const match = dateStr.match(/(\d{1,2}\s+\w+\s+\d{4})/);
            return match ? match[1] : dateStr.slice(0, 16);
        }
        const now = new Date();
        const diff = now - d;
        const mins = Math.floor(diff / 60000);
        if (mins < 60) return mins + 'm ago';
        const hours = Math.floor(diff / 3600000);
        if (hours < 24) return hours + 'h ago';
        const days = Math.floor(hours / 24);
        if (days < 7) return days + 'd ago';
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } catch (e) {
        return dateStr.slice(0, 16);
    }
}
