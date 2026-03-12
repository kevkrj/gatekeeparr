/**
 * Gatekeeper Setup Wizard - Frontend Logic
 */

let currentStep = 1;
const totalSteps = 6;

// Default model hints per provider
const MODEL_HINTS = {
    claude: 'Default: claude-sonnet-4-20250514',
    openai: 'Default: gpt-4o',
    grok: 'Default: grok-3',
    ollama: 'Default: llama3',
};

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

function nextStep() {
    if (currentStep < totalSteps) {
        // Build summary when entering the final step
        if (currentStep + 1 === totalSteps) {
            buildSummary();
        }
        setStep(currentStep + 1);
    }
}

function prevStep() {
    if (currentStep > 1) {
        setStep(currentStep - 1);
    }
}

function setStep(n) {
    // Hide current
    const cur = document.getElementById('step-' + currentStep);
    if (cur) cur.classList.remove('active');

    // Show new
    currentStep = n;
    const next = document.getElementById('step-' + currentStep);
    if (next) next.classList.add('active');

    // Update progress indicators
    document.querySelectorAll('.progress-step').forEach(el => {
        const s = parseInt(el.dataset.step);
        el.classList.remove('active', 'done');
        if (s === currentStep) el.classList.add('active');
        else if (s < currentStep) el.classList.add('done');
    });
}

// ---------------------------------------------------------------------------
// Provider toggle
// ---------------------------------------------------------------------------

function onProviderChange() {
    const provider = document.getElementById('ai_provider').value;
    const apiKeyGroup = document.getElementById('ai_api_key_group');
    const baseUrlGroup = document.getElementById('ai_base_url_group');
    const hint = document.getElementById('model-hint');

    if (provider === 'ollama') {
        apiKeyGroup.style.display = 'none';
        baseUrlGroup.style.display = 'block';
    } else {
        apiKeyGroup.style.display = 'block';
        baseUrlGroup.style.display = 'none';
    }

    hint.textContent = MODEL_HINTS[provider] || '';
}

// ---------------------------------------------------------------------------
// Connection tests
// ---------------------------------------------------------------------------

async function testConnection(service) {
    const resultEl = document.getElementById('test-' + service);
    resultEl.textContent = 'Testing...';
    resultEl.className = 'test-result testing';

    const payload = { service };

    // Gather relevant fields
    if (service === 'jellyseerr' || service === 'all') {
        payload.jellyseerr_url = val('jellyseerr_url');
        payload.jellyseerr_api_key = val('jellyseerr_api_key');
    }
    if (service === 'radarr' || service === 'all') {
        payload.radarr_url = val('radarr_url');
        payload.radarr_api_key = val('radarr_api_key');
    }
    if (service === 'sonarr' || service === 'all') {
        payload.sonarr_url = val('sonarr_url');
        payload.sonarr_api_key = val('sonarr_api_key');
    }
    if (service === 'tmdb') {
        payload.tmdb_api_key = val('tmdb_api_key');
    }
    if (service === 'ai') {
        payload.ai_provider = val('ai_provider');
        payload.ai_api_key = val('ai_api_key');
        payload.ai_base_url = val('ai_base_url');
        payload.ai_model = val('ai_model');
    }
    if (service === 'mattermost') {
        payload.mattermost_webhook = val('mattermost_webhook');
    }
    if (service === 'discord') {
        payload.discord_webhook = val('discord_webhook');
    }

    try {
        const resp = await fetch('/api/setup/validate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await resp.json();
        const result = data[service];

        if (result && result.ok) {
            resultEl.textContent = 'Connected';
            resultEl.className = 'test-result success';
        } else {
            const err = result ? result.error : 'Unknown error';
            resultEl.textContent = 'Failed: ' + err;
            resultEl.className = 'test-result error';
        }
    } catch (e) {
        resultEl.textContent = 'Error: ' + e.message;
        resultEl.className = 'test-result error';
    }
}

// ---------------------------------------------------------------------------
// Jellyseerr user loading
// ---------------------------------------------------------------------------

async function loadJellyseerrUsers() {
    const btn = document.getElementById('btn-load-users');
    const select = document.getElementById('jellyseerr_user_select');

    btn.textContent = 'Loading...';
    btn.disabled = true;

    try {
        const resp = await fetch('/api/setup/jellyseerr-users', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                jellyseerr_url: val('jellyseerr_url'),
                jellyseerr_api_key: val('jellyseerr_api_key'),
            }),
        });
        const data = await resp.json();

        if (data.error) {
            showToast('Failed to load users: ' + data.error, 'error');
            btn.textContent = 'Load Jellyseerr Users';
            btn.disabled = false;
            return;
        }

        // Populate select
        select.innerHTML = '<option value="">-- Select a Jellyseerr user --</option>';
        (data.users || []).forEach(u => {
            const opt = document.createElement('option');
            opt.value = JSON.stringify({
                id: u.id,
                username: u.username,
                email: u.email,
                display_name: u.display_name,
            });
            const label = u.display_name
                ? u.display_name + ' (' + u.username + ')'
                : u.username;
            opt.textContent = label + (u.is_admin ? ' [admin]' : '');
            select.appendChild(opt);
        });

        select.style.display = 'block';
        btn.textContent = 'Reload Users';
        btn.disabled = false;
    } catch (e) {
        showToast('Error: ' + e.message, 'error');
        btn.textContent = 'Load Jellyseerr Users';
        btn.disabled = false;
    }
}

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

function buildSummary() {
    const container = document.getElementById('summary-content');

    const items = [
        ['Jellyseerr', val('jellyseerr_url') && val('jellyseerr_api_key') ? val('jellyseerr_url') : null],
        ['Radarr', val('radarr_url') && val('radarr_api_key') ? val('radarr_url') : null],
        ['Sonarr', val('sonarr_url') && val('sonarr_api_key') ? val('sonarr_url') : null],
        ['AI Provider', val('ai_provider')],
        ['AI Model', val('ai_model') || '(default)'],
        ['TMDB', val('tmdb_api_key') ? 'Configured' : null],
        ['Mattermost', val('mattermost_webhook') ? 'Configured' : null],
        ['Discord', val('discord_webhook') ? 'Configured' : null],
        ['Admin User', val('admin_username') || null],
        ['Jellyseerr Link', getJellyseerrSelection() ? getJellyseerrSelection().username : null],
    ];

    container.innerHTML = items.map(([label, value]) => {
        const cls = value ? 'ok' : 'missing';
        const display = value || 'Not configured';
        return '<div class="summary-item">' +
            '<span class="summary-label">' + label + '</span>' +
            '<span class="summary-value ' + cls + '">' + escapeHtml(display) + '</span>' +
            '</div>';
    }).join('');
}

// ---------------------------------------------------------------------------
// Complete setup
// ---------------------------------------------------------------------------

async function completeSetup() {
    const btn = document.getElementById('btn-complete');
    btn.disabled = true;
    btn.textContent = 'Setting up...';

    const jsUser = getJellyseerrSelection();

    const payload = {
        // Services
        jellyseerr_url: val('jellyseerr_url'),
        jellyseerr_api_key: val('jellyseerr_api_key'),
        radarr_url: val('radarr_url'),
        radarr_api_key: val('radarr_api_key'),
        sonarr_url: val('sonarr_url'),
        sonarr_api_key: val('sonarr_api_key'),
        // AI
        ai_provider: val('ai_provider'),
        ai_api_key: val('ai_api_key'),
        ai_base_url: val('ai_base_url'),
        ai_model: val('ai_model'),
        // TMDB
        tmdb_api_key: val('tmdb_api_key'),
        // Notifications
        mattermost_webhook: val('mattermost_webhook'),
        discord_webhook: val('discord_webhook'),
        // Admin user
        admin_username: val('admin_username'),
        jellyseerr_username: jsUser ? jsUser.username : val('admin_username'),
        jellyseerr_id: jsUser ? jsUser.id : null,
        admin_display_name: jsUser ? jsUser.display_name : null,
        admin_email: jsUser ? jsUser.email : null,
    };

    // Basic validation
    if (!payload.admin_username) {
        showToast('Admin username is required', 'error');
        btn.disabled = false;
        btn.textContent = 'Complete Setup';
        return;
    }

    try {
        const resp = await fetch('/api/setup/complete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await resp.json();

        if (data.success) {
            // Hide current step, show done
            document.getElementById('step-' + currentStep).classList.remove('active');
            document.getElementById('step-done').style.display = 'block';

            // Mark all progress steps as done
            document.querySelectorAll('.progress-step').forEach(el => {
                el.classList.remove('active');
                el.classList.add('done');
            });
        } else {
            showToast('Setup failed: ' + (data.error || 'Unknown error'), 'error');
            btn.disabled = false;
            btn.textContent = 'Complete Setup';
        }
    } catch (e) {
        showToast('Error: ' + e.message, 'error');
        btn.disabled = false;
        btn.textContent = 'Complete Setup';
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function val(id) {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
}

function getJellyseerrSelection() {
    const select = document.getElementById('jellyseerr_user_select');
    if (!select || !select.value) return null;
    try {
        return JSON.parse(select.value);
    } catch {
        return null;
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showToast(message, type) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = 'toast show ' + (type || '');
    setTimeout(() => {
        toast.className = 'toast';
    }, 4000);
}

// ---------------------------------------------------------------------------
// Init: check if setup is even needed
// ---------------------------------------------------------------------------

(async function init() {
    try {
        const resp = await fetch('/api/setup/status');
        const data = await resp.json();
        if (!data.setup_needed) {
            // Setup already done, redirect to admin
            window.location.href = '/admin';
        }
    } catch (e) {
        // If status check fails, stay on setup page
        console.error('Setup status check failed:', e);
    }
})();
