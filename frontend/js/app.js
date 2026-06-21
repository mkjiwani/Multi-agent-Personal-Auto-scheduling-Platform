/* Main application JS — tab switching, WebSocket connection, API helpers */

// --- Tab Navigation ---
document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById(`tab-${tab.dataset.tab}`).classList.add('active');
    });
});

// --- WebSocket Connection ---
let ws = null;
let reconnectInterval = null;

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

    ws.onopen = () => {
        document.getElementById('connection-status').textContent = 'Connected';
        document.getElementById('connection-status').className = 'status-badge connected';
        if (reconnectInterval) {
            clearInterval(reconnectInterval);
            reconnectInterval = null;
        }
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'update') {
            updateSystemMetrics(data.system);
            updateAlarms(data.alarms);
            updateAgentCards(data.agents);
            updateLLMStatus(data.llm);
        }
    };

    ws.onclose = () => {
        document.getElementById('connection-status').textContent = 'Disconnected';
        document.getElementById('connection-status').className = 'status-badge disconnected';
        if (!reconnectInterval) {
            reconnectInterval = setInterval(connectWebSocket, 5000);
        }
    };

    ws.onerror = () => ws.close();
}

connectWebSocket();

// --- API Helper ---
async function api(method, path, body = null) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(path, opts);
    return res.json();
}

// --- Initial Data Load ---
window.addEventListener('load', async () => {
    loadAITimes();
    loadMailman();
    loadWallstreet();
    loadNews();
});
