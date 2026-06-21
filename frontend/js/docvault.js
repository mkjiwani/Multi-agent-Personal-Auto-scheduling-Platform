/* DocVault RAG frontend logic */

async function loadDocVaultStatus() {
    try {
        const res = await fetch('/api/docvault/status');
        const data = await res.json();

        document.getElementById('dv-doc-count').textContent = data.indexed_documents || 0;
        document.getElementById('dv-chunk-count').textContent = data.total_chunks || 0;
        document.getElementById('dv-folder-count').textContent = (data.folders || []).length;

        if (data.indexed_at) {
            const d = new Date(data.indexed_at + 'Z');
            document.getElementById('dv-indexed-at').textContent = d.toLocaleTimeString();
        }

        // Render folders list
        const foldersEl = document.getElementById('dv-folders-list');
        if (data.folders && data.folders.length > 0) {
            foldersEl.innerHTML = data.folders.map(f => {
                const shortName = f.split('/').slice(-2).join('/');
                return `<div class="dv-folder-item">
                    <span class="dv-folder-icon">📁</span>
                    <span class="dv-folder-name" title="${f}">.../${shortName}</span>
                    <button class="dv-folder-remove" onclick="removeDocVaultFolder('${f.replace(/'/g, "\\'")}')">✕</button>
                </div>`;
            }).join('');
        } else {
            foldersEl.innerHTML = '<p class="dv-empty">No folders added. Enter a folder path above and click "Add Folder".</p>';
        }

        // Render query history
        const historyEl = document.getElementById('dv-history');
        if (data.query_history && data.query_history.length > 0) {
            historyEl.innerHTML = data.query_history.map(q => `
                <div class="dv-history-item">
                    <div class="dv-history-q">Q: ${q.question}</div>
                    <div class="dv-history-a">${q.answer.substring(0, 150)}${q.answer.length > 150 ? '...' : ''}</div>
                </div>
            `).join('');
        } else {
            historyEl.innerHTML = '<p class="dv-empty">No queries yet.</p>';
        }
    } catch (e) {
        console.error('DocVault status error:', e);
    }
}

async function addDocVaultFolder() {
    const input = document.getElementById('dv-new-folder');
    const folderPath = input.value.trim();
    if (!folderPath) return;

    try {
        const res = await fetch('/api/docvault/folders/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder_path: folderPath }),
        });
        const data = await res.json();
        if (data.error) {
            alert(data.error);
        } else {
            input.value = '';
            loadDocVaultStatus();
        }
    } catch (e) {
        console.error('Add folder error:', e);
    }
}

async function removeDocVaultFolder(folderPath) {
    if (!confirm('Remove this folder from indexing?')) return;
    try {
        const res = await fetch('/api/docvault/folders/remove', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder_path: folderPath }),
        });
        await res.json();
        loadDocVaultStatus();
    } catch (e) {
        console.error('Remove folder error:', e);
    }
}

async function askDocVault() {
    const input = document.getElementById('dv-question');
    const question = input.value.trim();
    if (!question) return;

    const answerEl = document.getElementById('dv-answer');
    answerEl.classList.remove('hidden');
    answerEl.innerHTML = '<div class="dv-loading">Searching documents and generating answer...</div>';

    try {
        const res = await fetch('/api/docvault/query', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question }),
        });
        const data = await res.json();

        const sourcesHtml = data.sources && data.sources.length > 0
            ? `<div class="dv-sources">
                <span class="dv-sources-label">Sources:</span>
                ${data.sources.map(s => `<span class="dv-source-tag">${s.source} (${(s.relevance * 100).toFixed(0)}%)</span>`).join('')}
               </div>`
            : '';

        answerEl.innerHTML = `
            <div class="dv-answer-content">
                <div class="dv-answer-text">${data.answer}</div>
                ${sourcesHtml}
            </div>
        `;

        input.value = '';
        loadDocVaultStatus(); // Refresh history
    } catch (e) {
        answerEl.innerHTML = '<div class="dv-error">Error querying documents. Please try again.</div>';
    }
}

async function reindexDocVault() {
    const statusEl = document.getElementById('dv-doc-count');
    statusEl.textContent = '...';
    document.getElementById('dv-chunk-count').textContent = '...';

    try {
        const res = await fetch('/api/docvault/reindex', { method: 'POST' });
        await res.json();
        loadDocVaultStatus();
    } catch (e) {
        console.error('Reindex error:', e);
    }
}

// Load status when DocVault tab is shown
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-tab]').forEach(btn => {
        btn.addEventListener('click', () => {
            if (btn.dataset.tab === 'docvault') {
                loadDocVaultStatus();
            }
        });
    });

    setTimeout(() => {
        const tab = document.getElementById('tab-docvault');
        if (tab && tab.classList.contains('active')) {
            loadDocVaultStatus();
        }
    }, 1000);
});
