/**
 * Gatekeeper Admin Panel JavaScript
 */

// API helper
const api = {
    async get(url) {
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
    },
    async post(url, data = {}) {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
    },
    async put(url, data = {}) {
        const response = await fetch(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
    }
};

// Toast notifications
function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type} show`;
    setTimeout(() => toast.classList.remove('show'), 3000);
}

// Format date
function formatDate(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
}

// Status badge
function statusBadge(status) {
    const colors = {
        pending: 'gray',
        analyzing: 'blue',
        held: 'orange',
        approved: 'green',
        denied: 'red',
        auto_approved: 'teal',
        error: 'red'
    };
    return `<span class="badge badge-${colors[status] || 'gray'}">${status}</span>`;
}

// Rating badge
function ratingBadge(rating) {
    if (!rating) return '-';
    const colors = {
        'G': 'green', 'TV-Y': 'green', 'TV-Y7': 'green', 'TV-G': 'green',
        'PG': 'teal', 'TV-PG': 'teal',
        'PG-13': 'yellow', 'TV-14': 'yellow',
        'R': 'orange', 'TV-MA': 'orange',
        'NC-17': 'red', 'X': 'red'
    };
    return `<span class="badge badge-${colors[rating] || 'gray'}">${rating}</span>`;
}

// User type badge
function userTypeBadge(type) {
    const colors = { kid: 'blue', teen: 'teal', adult: 'gray', admin: 'purple' };
    return `<span class="badge badge-${colors[type] || 'gray'}">${type}</span>`;
}

// Action badge
function actionBadge(action) {
    const colors = { approve: 'green', deny: 'red', auto_approve: 'teal' };
    const labels = { approve: 'Approved', deny: 'Denied', auto_approve: 'Auto-Approved' };
    return `<span class="badge badge-${colors[action] || 'gray'}">${labels[action] || action}</span>`;
}

// View navigation
document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', (e) => {
        e.preventDefault();
        const view = link.dataset.view;

        // Update nav
        document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
        link.classList.add('active');

        // Show view
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
        document.getElementById(`${view}-view`).classList.add('active');

        // Load data
        if (view === 'dashboard') loadDashboard();
        else if (view === 'requests') loadRequests();
        else if (view === 'users') loadUsers();
        else if (view === 'approvals') loadApprovals();
    });
});

// Modal handling
document.querySelectorAll('.modal-close, .modal-close-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.modal').forEach(m => m.style.display = 'none');
    });
});

window.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal')) {
        e.target.style.display = 'none';
    }
});

// Dashboard
async function loadDashboard() {
    try {
        const stats = await api.get('/api/stats');

        // Update stat cards
        document.getElementById('stat-total').textContent = stats.totals.requests;
        document.getElementById('stat-held').textContent = stats.totals.held;
        document.getElementById('stat-approved').textContent =
            (stats.by_status.approved || 0) + (stats.by_status.auto_approved || 0);
        document.getElementById('stat-denied').textContent = stats.by_status.denied || 0;

        // Load held requests
        const held = await api.get('/api/requests/held');
        const heldList = document.getElementById('held-requests-list');
        if (held.requests.length === 0) {
            heldList.innerHTML = '<div class="empty-state">No requests held for review</div>';
        } else {
            heldList.innerHTML = held.requests.map(r => `
                <div class="request-item">
                    <div class="request-info">
                        <strong>${r.title}</strong> ${r.year ? `(${r.year})` : ''}
                        <div class="request-meta">
                            ${ratingBadge(r.ai_rating)} • ${r.media_type} • by ${r.requested_by || 'Unknown'}
                        </div>
                    </div>
                    <div class="request-actions">
                        <button class="btn btn-small btn-approve" onclick="approveRequest(${r.id})">Approve</button>
                        <button class="btn btn-small btn-deny" onclick="denyRequest(${r.id})">Deny</button>
                    </div>
                </div>
            `).join('');
        }

        // Load recent activity
        const activity = await api.get('/api/stats/recent-activity');
        const activityList = document.getElementById('recent-activity');
        if (activity.activity.length === 0) {
            activityList.innerHTML = '<div class="empty-state">No recent activity</div>';
        } else {
            activityList.innerHTML = activity.activity.slice(0, 10).map(a => {
                if (a.type === 'request') {
                    return `
                        <div class="activity-item">
                            <span class="activity-icon">📥</span>
                            <div class="activity-text">
                                <strong>${a.title}</strong> requested by ${a.user || 'Unknown'}
                                <div class="activity-meta">${formatDate(a.timestamp)}</div>
                            </div>
                            ${statusBadge(a.status)}
                        </div>
                    `;
                } else {
                    return `
                        <div class="activity-item">
                            <span class="activity-icon">${a.action === 'approve' ? '✅' : '❌'}</span>
                            <div class="activity-text">
                                <strong>${a.request_title || 'Unknown'}</strong> ${a.action}d by ${a.decided_by}
                                <div class="activity-meta">${formatDate(a.timestamp)}</div>
                            </div>
                        </div>
                    `;
                }
            }).join('');
        }

        // Rating chart (simple bar chart)
        const chartContainer = document.getElementById('rating-chart');
        const ratings = stats.by_rating;
        if (Object.keys(ratings).length === 0) {
            chartContainer.innerHTML = '<div class="empty-state">No rating data yet</div>';
        } else {
            const maxCount = Math.max(...Object.values(ratings));
            chartContainer.innerHTML = `
                <div class="bar-chart">
                    ${Object.entries(ratings).map(([rating, count]) => `
                        <div class="bar-item">
                            <div class="bar-label">${rating}</div>
                            <div class="bar-wrapper">
                                <div class="bar" style="width: ${(count / maxCount) * 100}%"></div>
                            </div>
                            <div class="bar-value">${count}</div>
                        </div>
                    `).join('')}
                </div>
            `;
        }

    } catch (err) {
        console.error('Failed to load dashboard:', err);
        showToast('Failed to load dashboard', 'error');
    }
}

// Requests
async function loadRequests() {
    try {
        const status = document.getElementById('filter-status').value;
        const mediaType = document.getElementById('filter-media-type').value;
        let url = '/api/requests?limit=100';
        if (status) url += `&status=${status}`;
        if (mediaType) url += `&media_type=${mediaType}`;

        const data = await api.get(url);
        const tbody = document.querySelector('#requests-table tbody');

        if (data.requests.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No requests found</td></tr>';
        } else {
            tbody.innerHTML = data.requests.map(r => `
                <tr>
                    <td>
                        <a href="#" onclick="showRequestDetail(${r.id}); return false;">
                            ${r.title} ${r.year ? `(${r.year})` : ''}
                        </a>
                    </td>
                    <td>${r.media_type}</td>
                    <td>${ratingBadge(r.ai_rating)}</td>
                    <td>${r.requested_by || '-'}</td>
                    <td>${statusBadge(r.status)}</td>
                    <td>${formatDate(r.created_at)}</td>
                    <td>
                        ${r.status === 'held' ? `
                            <button class="btn btn-small btn-approve" onclick="approveRequest(${r.id})">Approve</button>
                            <button class="btn btn-small btn-deny" onclick="denyRequest(${r.id})">Deny</button>
                        ` : '-'}
                    </td>
                </tr>
            `).join('');
        }
    } catch (err) {
        console.error('Failed to load requests:', err);
        showToast('Failed to load requests', 'error');
    }
}

// Request detail modal
async function showRequestDetail(requestId) {
    const modal = document.getElementById('request-modal');
    const modalBody = document.getElementById('modal-body');
    modal.style.display = 'block';
    modalBody.innerHTML = '<div class="loading">Loading...</div>';

    try {
        const r = await api.get(`/api/requests/${requestId}`);
        modalBody.innerHTML = `
            <div class="request-detail">
                <h2>${r.title} ${r.year ? `(${r.year})` : ''}</h2>
                <div class="detail-grid">
                    <div class="detail-item">
                        <label>Type</label>
                        <span>${r.media_type}</span>
                    </div>
                    <div class="detail-item">
                        <label>Status</label>
                        <span>${statusBadge(r.status)}</span>
                    </div>
                    <div class="detail-item">
                        <label>Rating</label>
                        <span>${ratingBadge(r.ai_rating)}</span>
                    </div>
                    <div class="detail-item">
                        <label>Requested By</label>
                        <span>${r.requested_by || 'Unknown'}</span>
                    </div>
                    <div class="detail-item">
                        <label>Requested At</label>
                        <span>${formatDate(r.created_at)}</span>
                    </div>
                    <div class="detail-item">
                        <label>AI Provider</label>
                        <span>${r.ai_provider || '-'}</span>
                    </div>
                </div>

                ${r.ai_summary ? `
                    <div class="detail-section">
                        <h3>AI Summary</h3>
                        <p>${r.ai_summary}</p>
                    </div>
                ` : ''}

                ${r.ai_concerns && r.ai_concerns.length > 0 ? `
                    <div class="detail-section">
                        <h3>Concerns</h3>
                        <ul>
                            ${r.ai_concerns.map(c => `<li>${c}</li>`).join('')}
                        </ul>
                    </div>
                ` : ''}

                ${r.held_reason ? `
                    <div class="detail-section">
                        <h3>Held Reason</h3>
                        <p>${r.held_reason}</p>
                    </div>
                ` : ''}

                ${r.approvals && r.approvals.length > 0 ? `
                    <div class="detail-section">
                        <h3>Approval History</h3>
                        <ul>
                            ${r.approvals.map(a => `
                                <li>${actionBadge(a.action)} by ${a.decided_by} via ${a.source} - ${formatDate(a.created_at)}</li>
                            `).join('')}
                        </ul>
                    </div>
                ` : ''}

                ${r.status === 'held' ? `
                    <div class="detail-actions">
                        <button class="btn btn-primary btn-approve" onclick="approveRequest(${r.id}); document.getElementById('request-modal').style.display='none';">Approve</button>
                        <button class="btn btn-deny" onclick="denyRequest(${r.id}); document.getElementById('request-modal').style.display='none';">Deny</button>
                    </div>
                ` : ''}
            </div>
        `;
    } catch (err) {
        console.error('Failed to load request:', err);
        modalBody.innerHTML = '<div class="error">Failed to load request details</div>';
    }
}

// Approve/Deny actions
async function approveRequest(requestId) {
    if (!confirm('Approve this request?')) return;
    try {
        await api.post(`/api/requests/${requestId}/approve`, { decided_by: 'admin_panel' });
        showToast('Request approved', 'success');
        loadDashboard();
        loadRequests();
    } catch (err) {
        console.error('Failed to approve:', err);
        showToast('Failed to approve request', 'error');
    }
}

async function denyRequest(requestId) {
    if (!confirm('Deny this request? This will delete the content from Radarr/Sonarr.')) return;
    try {
        await api.post(`/api/requests/${requestId}/deny`, { decided_by: 'admin_panel' });
        showToast('Request denied', 'success');
        loadDashboard();
        loadRequests();
    } catch (err) {
        console.error('Failed to deny:', err);
        showToast('Failed to deny request', 'error');
    }
}

// Users
async function loadUsers() {
    try {
        const data = await api.get('/api/users');
        const tbody = document.querySelector('#users-table tbody');

        if (data.users.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No users found. Click "Sync from Jellyseerr" to import users.</td></tr>';
        } else {
            tbody.innerHTML = data.users.map(u => `
                <tr>
                    <td>${u.username}</td>
                    <td>${userTypeBadge(u.user_type)}</td>
                    <td>${u.max_rating || 'No limit'}</td>
                    <td>${u.request_count || 0}</td>
                    <td>
                        <button class="btn btn-small" onclick="editUser(${u.id})">Edit</button>
                    </td>
                </tr>
            `).join('');
        }
    } catch (err) {
        console.error('Failed to load users:', err);
        showToast('Failed to load users', 'error');
    }
}

// Edit user modal
async function editUser(userId) {
    const modal = document.getElementById('user-modal');
    modal.style.display = 'block';

    try {
        const user = await api.get(`/api/users/${userId}`);
        document.getElementById('edit-user-id').value = user.id;
        document.getElementById('edit-username').value = user.username;
        document.getElementById('edit-user-type').value = user.user_type;
        document.getElementById('edit-max-rating').value = user.max_rating || '';
        document.getElementById('edit-requires-approval').checked = user.requires_approval;
    } catch (err) {
        console.error('Failed to load user:', err);
        showToast('Failed to load user details', 'error');
        modal.style.display = 'none';
    }
}

// Save user
document.getElementById('user-edit-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const userId = document.getElementById('edit-user-id').value;
    const data = {
        user_type: document.getElementById('edit-user-type').value,
        max_rating: document.getElementById('edit-max-rating').value || null,
        requires_approval: document.getElementById('edit-requires-approval').checked
    };

    try {
        await api.put(`/api/users/${userId}`, data);
        showToast('User updated', 'success');
        document.getElementById('user-modal').style.display = 'none';
        loadUsers();
    } catch (err) {
        console.error('Failed to update user:', err);
        showToast('Failed to update user', 'error');
    }
});

// Sync users
document.getElementById('btn-sync-users').addEventListener('click', async () => {
    try {
        const result = await api.post('/api/users/sync');
        showToast(`Synced ${result.synced_count} users`, 'success');
        loadUsers();
    } catch (err) {
        console.error('Failed to sync users:', err);
        showToast('Failed to sync users', 'error');
    }
});

// Approvals
async function loadApprovals() {
    try {
        const action = document.getElementById('filter-action').value;
        let url = '/api/approvals?limit=100';
        if (action) url += `&action=${action}`;

        const data = await api.get(url);
        const tbody = document.querySelector('#approvals-table tbody');

        if (data.approvals.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No approvals found</td></tr>';
        } else {
            tbody.innerHTML = data.approvals.map(a => `
                <tr>
                    <td>${a.request ? a.request.title : '-'}</td>
                    <td>${actionBadge(a.action)}</td>
                    <td>${a.decided_by}</td>
                    <td>${a.source}</td>
                    <td>${formatDate(a.created_at)}</td>
                </tr>
            `).join('');
        }
    } catch (err) {
        console.error('Failed to load approvals:', err);
        showToast('Failed to load approvals', 'error');
    }
}

// Event listeners for filters and buttons
document.getElementById('filter-status').addEventListener('change', loadRequests);
document.getElementById('filter-media-type').addEventListener('change', loadRequests);
document.getElementById('btn-refresh-requests').addEventListener('click', loadRequests);
document.getElementById('btn-refresh-users').addEventListener('click', loadUsers);
document.getElementById('filter-action').addEventListener('change', loadApprovals);
document.getElementById('btn-refresh-approvals').addEventListener('click', loadApprovals);

// Initial load
loadDashboard();
