/* Orchestrator — system metrics, alarms, agent cards, LLM status */

function updateSystemMetrics(metrics) {
    if (!metrics) return;

    updateGauge('cpu', metrics.cpu_percent);
    updateGauge('ram', metrics.ram_percent);
    updateGauge('disk', metrics.disk_percent);

    document.getElementById('threads-value').textContent = metrics.active_threads;
}

function updateGauge(id, value) {
    const gauge = document.getElementById(`${id}-gauge`);
    const valueEl = document.getElementById(`${id}-value`);
    const ring = document.getElementById(`${id}-ring`);
    valueEl.textContent = `${Math.round(value)}%`;

    // SVG ring animation (circumference = 2 * π * 42 ≈ 264)
    if (ring) {
        const circumference = 264;
        const offset = circumference - (circumference * value / 100);
        ring.style.strokeDashoffset = offset;
    }

    // Status classes
    gauge.className = 'gauge-ring';
    if (value >= 90) gauge.classList.add('critical');
    else if (value >= 70) gauge.classList.add('warning');
    else gauge.classList.add('normal');
}

function updateAlarms(alarms) {
    const banner = document.getElementById('alarm-banner');
    if (!alarms || alarms.all_clear) {
        banner.classList.add('hidden');
        return;
    }

    const active = alarms.active_alarms;
    if (active.length > 0) {
        banner.classList.remove('hidden');
        const alarm = active[0];
        document.getElementById('alarm-message').textContent =
            `${alarm.resource.toUpperCase()} at ${alarm.current_value.toFixed(1)}% (threshold: ${alarm.threshold}%)`;
        document.getElementById('alarm-suggestion').textContent = `💡 ${alarm.suggestion}`;
    } else {
        banner.classList.add('hidden');
    }
}

function updateAgentCards(agents) {
    if (!agents) return;
    const container = document.getElementById('agent-cards');
    container.innerHTML = '';

    for (const [name, info] of Object.entries(agents)) {
        const card = document.createElement('div');
        card.className = 'agent-card';
        card.innerHTML = `
            <div class="agent-name">${formatAgentName(name)}</div>
            <span class="agent-status ${info.status}">${info.status}</span>
            <p style="margin-top: 8px; font-size: 0.8rem; color: var(--text-secondary);">
                PID: ${info.pid || 'N/A'} | Restarts: ${info.restart_count}
            </p>
            ${info.error_message ? `<p style="font-size: 0.75rem; color: var(--accent-red); margin-top: 4px;">${info.error_message}</p>` : ''}
            <button class="btn" style="margin-top: 8px; font-size: 0.75rem;" onclick="restartAgent('${name}')">🔄 Restart</button>
        `;
        container.appendChild(card);
    }
}

function updateLLMStatus(llm) {
    if (!llm) return;
    document.getElementById('llm-locked').textContent = llm.is_locked ? '🔒 Busy' : '🟢 Idle';
    document.getElementById('llm-holder').textContent = llm.current_holder || 'None';
    document.getElementById('llm-queue').textContent =
        llm.waiting_queue.length > 0 ? llm.waiting_queue.join(', ') : 'None';
}

function formatAgentName(name) {
    const names = {
        'ai_times': '🎬 AI-Times',
        'mailman': '📬 Mailman',
        'wallstreet_wolf': '🐺 Wallstreet Wolf',
        'news_briefer': '📰 News Briefer',
    };
    return names[name] || name;
}

async function restartAgent(name) {
    await api('POST', `/api/agents/${name}/restart`);
}

async function clearCaches() {
    const btn = document.getElementById('clear-caches-btn');
    btn.disabled = true;
    btn.textContent = '⏳ Clearing...';
    const result = await api('POST', '/api/clear-caches');
    btn.textContent = '✓ Cleared!';
    setTimeout(() => {
        btn.disabled = false;
        btn.textContent = '🧹 Clear Caches';
    }, 2000);
}

/* --- Digest Schedule Management --- */
async function loadSchedules() {
    try {
        const data = await api('GET', '/api/schedules');
        if (data) {
            for (const [agent, time] of Object.entries(data)) {
                const input = document.getElementById(`schedule-${agent}`);
                if (input) input.value = time;
            }
        }
    } catch (e) { console.warn('Could not load schedules:', e); }
}

async function saveSchedules() {
    const agents = ['ai_times', 'mailman', 'wallstreet', 'news'];
    let saved = 0;
    for (const agent of agents) {
        const input = document.getElementById(`schedule-${agent}`);
        if (!input) continue;
        const time = input.value;
        if (time) {
            await api('POST', `/api/schedules/${agent}?time=${time}`);
            saved++;
        }
    }
    alert(`✓ ${saved} schedules updated. Digests will be sent at the configured times.`);
}

// Load schedules on page init
document.addEventListener('DOMContentLoaded', loadSchedules);
