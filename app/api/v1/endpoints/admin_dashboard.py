from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from datetime import datetime, timedelta
from typing import Optional
import uuid

from app.db.database import get_db
from app.db.entity.user import User
from app.db.entity.api_key import APIKey
from app.db.entity.usage_log import UsageLog
from app.db.entity.llm_usage_log import LLMUsageLog

router = APIRouter(prefix="/dashboard")  # ← ĐỔI THÀNH /dashboard
templates = Jinja2Templates(directory="app/templates")


# ========== Page Endpoints (trả HTML) ==========
@router.get("/admin/api/pages/dashboard", response_class=HTMLResponse)
async def page_dashboard():
    return """
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8" id="stats-cards">
        <div class="bg-white rounded-lg shadow-md p-6 card-hover"><div class="loading-spinner mx-auto"></div></div>
    </div>
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <div class="bg-white rounded-lg shadow-md p-6"><h3 class="text-lg font-semibold mb-4">Requests theo service</h3><canvas id="service-chart" height="250"></canvas></div>
        <div class="bg-white rounded-lg shadow-md p-6"><h3 class="text-lg font-semibold mb-4">Xu hướng 7 ngày qua</h3><canvas id="trend-chart" height="250"></canvas></div>
    </div>
    <div class="bg-white rounded-lg shadow-md">
        <div class="px-6 py-4 border-b border-gray-200 flex justify-between items-center"><h3 class="text-lg font-semibold">Người dùng mới nhất</h3><a href="/admin/users" class="text-blue-500 hover:text-blue-700 text-sm">Xem tất cả →</a></div>
        <div class="overflow-x-auto"><table class="w-full table-hover"><thead class="bg-gray-50"><tr><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">ID</th><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Tên</th><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Email</th><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Trạng thái</th><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Ngày tạo</th></tr></thead><tbody id="recent-users"></tbody></table></div>
    </div>
    <script>
        const API_KEY = localStorage.getItem('admin_api_key');
        
        async function loadDashboard() {
            const response = await fetch('/admin/api/stats/dashboard', { headers: { 'X-Internal-Key': API_KEY } });
            const data = await response.json();
            
            document.getElementById('stats-cards').innerHTML = `
                <div class="bg-white rounded-lg shadow-md p-6 card-hover"><div class="flex items-center justify-between"><div><p class="text-gray-500 text-sm">Tổng người dùng</p><p class="text-3xl font-bold text-gray-800">${data.total_users || 0}</p></div><div class="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center"><i class="fas fa-users text-blue-500 text-xl"></i></div></div></div>
                <div class="bg-white rounded-lg shadow-md p-6 card-hover"><div class="flex items-center justify-between"><div><p class="text-gray-500 text-sm">Tổng requests</p><p class="text-3xl font-bold text-gray-800">${data.total_requests || 0}</p><p class="text-green-500 text-xs mt-2">Hôm nay: ${data.today_requests || 0}</p></div><div class="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center"><i class="fas fa-chart-line text-green-500 text-xl"></i></div></div></div>
                <div class="bg-white rounded-lg shadow-md p-6 card-hover"><div class="flex items-center justify-between"><div><p class="text-gray-500 text-sm">Tổng tokens</p><p class="text-3xl font-bold text-gray-800">${(data.total_tokens || 0).toLocaleString()}</p><p class="text-yellow-500 text-xs mt-2">~ ${(data.estimated_cost || 0).toFixed(4)} USD</p></div><div class="w-12 h-12 bg-yellow-100 rounded-full flex items-center justify-center"><i class="fas fa-coins text-yellow-500 text-xl"></i></div></div></div>
                <div class="bg-white rounded-lg shadow-md p-6 card-hover"><div class="flex items-center justify-between"><div><p class="text-gray-500 text-sm">Tỷ lệ thành công</p><p class="text-3xl font-bold text-gray-800">${data.success_rate || 0}%</p></div><div class="w-12 h-12 bg-purple-100 rounded-full flex items-center justify-center"><i class="fas fa-check-circle text-purple-500 text-xl"></i></div></div></div>
            `;
            
            new Chart(document.getElementById('service-chart'), { type: 'bar', data: { labels: Object.keys(data.service_stats || {}), datasets: [{ label: 'Requests', data: Object.values(data.service_stats || {}), backgroundColor: 'rgba(59, 130, 246, 0.6)' }] }, options: { responsive: true } });
            new Chart(document.getElementById('trend-chart'), { type: 'line', data: { labels: (data.trend_data || []).map(d => d.date), datasets: [{ label: 'Requests', data: (data.trend_data || []).map(d => d.count), borderColor: '#10b981', fill: true }] }, options: { responsive: true } });
            
            const usersRes = await fetch('/admin/api/users?limit=5', { headers: { 'X-Internal-Key': API_KEY } });
            const usersData = await usersRes.json();
            document.getElementById('recent-users').innerHTML = (usersData.users || []).map(u => `<tr class="border-b"><td class="px-6 py-3 text-sm">${u.id}</td><td class="px-6 py-3 text-sm font-medium">${u.username}</td><td class="px-6 py-3 text-sm">${u.email}</td><td class="px-6 py-3 text-sm"><span class="px-2 py-1 rounded-full text-xs ${u.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}">${u.is_active ? 'Hoạt động' : 'Khóa'}</span></td><td class="px-6 py-3 text-sm">${new Date(u.created_at).toLocaleDateString('vi-VN')}</td></tr>`).join('');
        }
        loadDashboard();
    </script>
    """


@router.get("/admin/api/pages/users", response_class=HTMLResponse)
async def page_users():
    return """
    <div class="bg-white rounded-lg shadow-md">
        <div class="px-6 py-4 border-b border-gray-200 flex justify-between items-center">
            <h3 class="text-lg font-semibold">Danh sách người dùng</h3>
            <button onclick="showCreateUserModal()" class="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded-lg text-sm"><i class="fas fa-plus mr-2"></i> Thêm người dùng</button>
        </div>
        <div class="overflow-x-auto"><table class="w-full table-hover"><thead class="bg-gray-50"><tr><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">ID</th><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Tên</th><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Email</th><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">API Keys</th><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Trạng thái</th><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Ngày tạo</th><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Thao tác</th></tr></thead><tbody id="users-table"></tbody></table></div>
        <div class="px-6 py-4 border-t border-gray-200 flex justify-between items-center"><div class="text-sm text-gray-500">Hiển thị <span id="page-start">0</span> - <span id="page-end">0</span> của <span id="total-users">0</span></div><div class="flex space-x-2"><button id="prev-page" class="px-3 py-1 border rounded" disabled>« Trước</button><span id="page-info" class="px-3 py-1 text-sm">Trang 1</span><button id="next-page" class="px-3 py-1 border rounded">Sau »</button></div></div>
    </div>
    <div id="create-user-modal" class="fixed inset-0 bg-black bg-opacity-50 hidden flex items-center justify-center z-50"><div class="bg-white rounded-lg w-96 p-6"><h3 class="text-lg font-semibold mb-4">Thêm người dùng</h3><form id="create-user-form"><div class="mb-4"><label class="block text-sm font-medium mb-1">Tên đăng nhập *</label><input type="text" name="username" required class="w-full border rounded-lg px-3 py-2"></div><div class="mb-4"><label class="block text-sm font-medium mb-1">Email *</label><input type="email" name="email" required class="w-full border rounded-lg px-3 py-2"></div><div class="flex justify-end space-x-2"><button type="button" onclick="closeModal()" class="px-4 py-2 border rounded-lg">Hủy</button><button type="submit" class="px-4 py-2 bg-blue-500 text-white rounded-lg">Tạo</button></div></form></div></div>
    <script>
        const API_KEY = localStorage.getItem('admin_api_key');
        let currentPage = 1, totalPages = 1;
        
        async function loadUsers() {
            const response = await fetch(`/admin/api/users?page=${currentPage}&limit=10`, { headers: { 'X-Internal-Key': API_KEY } });
            const data = await response.json();
            document.getElementById('users-table').innerHTML = (data.users || []).map(u => `<tr class="border-b"><td class="px-6 py-3 text-sm">${u.id}</td><td class="px-6 py-3 text-sm font-medium">${u.username}</td><td class="px-6 py-3 text-sm">${u.email}</td><td class="px-6 py-3 text-sm"><button onclick="viewApiKeys(${u.id})" class="text-blue-500"><i class="fas fa-key"></i> Xem</button></td><td class="px-6 py-3 text-sm"><span class="px-2 py-1 rounded-full text-xs ${u.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}">${u.is_active ? 'Hoạt động' : 'Khóa'}</span></td><td class="px-6 py-3 text-sm">${new Date(u.created_at).toLocaleDateString('vi-VN')}</td><td class="px-6 py-3 text-sm"><button onclick="toggleUserStatus(${u.id}, ${!u.is_active})" class="text-yellow-500 mr-2"><i class="fas ${u.is_active ? 'fa-ban' : 'fa-check-circle'}"></i></button><button onclick="createApiKey(${u.id})" class="text-green-500 mr-2"><i class="fas fa-plus-circle"></i></button><button onclick="deleteUser(${u.id})" class="text-red-500"><i class="fas fa-trash"></i></button></td></tr>`).join('');
            document.getElementById('total-users').innerText = data.total;
            document.getElementById('page-start').innerText = ((currentPage - 1) * 10) + 1;
            document.getElementById('page-end').innerText = Math.min(currentPage * 10, data.total);
            totalPages = Math.ceil(data.total / 10);
            document.getElementById('page-info').innerText = `Trang ${currentPage} / ${totalPages}`;
            document.getElementById('prev-page').disabled = currentPage === 1;
            document.getElementById('next-page').disabled = currentPage === totalPages;
        }
        
        function changePage(delta) { const newPage = currentPage + delta; if (newPage >= 1 && newPage <= totalPages) { currentPage = newPage; loadUsers(); } }
        document.getElementById('prev-page').onclick = () => changePage(-1);
        document.getElementById('next-page').onclick = () => changePage(1);
        
        function showCreateUserModal() { document.getElementById('create-user-modal').classList.remove('hidden'); }
        function closeModal() { document.getElementById('create-user-modal').classList.add('hidden'); }
        
        document.getElementById('create-user-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            await fetch('/admin/api/users', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Internal-Key': API_KEY }, body: JSON.stringify({ username: formData.get('username'), email: formData.get('email') }) });
            closeModal(); loadUsers();
        });
        
        async function toggleUserStatus(userId, activate) { await fetch(`/admin/api/users/${userId}`, { method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-Internal-Key': API_KEY }, body: JSON.stringify({ is_active: activate }) }); loadUsers(); }
        async function createApiKey(userId) { const res = await fetch(`/admin/api/users/${userId}/api-keys`, { method: 'POST', headers: { 'X-Internal-Key': API_KEY } }); const data = await res.json(); alert(`API Key: ${data.api_key}`); loadUsers(); }
        async function viewApiKeys(userId) { const res = await fetch(`/admin/api/api-keys?user_id=${userId}`, { headers: { 'X-Internal-Key': API_KEY } }); const data = await res.json(); if(data.api_keys && data.api_keys.length) alert('API Keys:\n' + data.api_keys.map(k => `- ${k.key} (${k.is_active ? 'active' : 'inactive'})`).join('\n')); else alert('Chưa có API key'); }
        async function deleteUser(userId) { if(confirm('Xóa user?')) { await fetch(`/admin/api/users/${userId}`, { method: 'DELETE', headers: { 'X-Internal-Key': API_KEY } }); loadUsers(); } }
        loadUsers();
    </script>
    """


@router.get("/admin/api/pages/api-keys", response_class=HTMLResponse)
async def page_api_keys():
    return """
    <div class="bg-white rounded-lg shadow-md">
        <div class="px-6 py-4 border-b border-gray-200"><h3 class="text-lg font-semibold">Danh sách API Keys</h3></div>
        <div class="overflow-x-auto"><table class="w-full table-hover"><thead class="bg-gray-50"><tr><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">ID</th><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Key</th><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">User ID</th><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Tên</th><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Trạng thái</th><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Hết hạn</th><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Lần cuối dùng</th></tr></thead><tbody id="api-keys-table"></tbody></table></div>
    </div>
    <script>
        const API_KEY = localStorage.getItem('admin_api_key');
        async function loadApiKeys() {
            const response = await fetch('/admin/api/api-keys', { headers: { 'X-Internal-Key': API_KEY } });
            const data = await response.json();
            document.getElementById('api-keys-table').innerHTML = (data.api_keys || []).map(k => `<tr class="border-b"><td class="px-6 py-3 text-sm">${k.id}</td><td class="px-6 py-3 text-sm font-mono">${k.key}</td><td class="px-6 py-3 text-sm">${k.user_id}</td><td class="px-6 py-3 text-sm">${k.name || '-'}</td><td class="px-6 py-3 text-sm"><span class="px-2 py-1 rounded-full text-xs ${k.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}">${k.is_active ? 'active' : 'inactive'}</span></td><td class="px-6 py-3 text-sm">${k.expires_at ? new Date(k.expires_at).toLocaleDateString('vi-VN') : '-'}</td><td class="px-6 py-3 text-sm">${k.last_used_at ? new Date(k.last_used_at).toLocaleDateString('vi-VN') : 'Chưa dùng'}</td></tr>`).join('');
        }
        loadApiKeys();
    </script>
    """


@router.get("/admin/api/pages/logs", response_class=HTMLResponse)
async def page_logs():
    return """
    <div class="bg-white rounded-lg shadow-md">
        <div class="px-6 py-4 border-b border-gray-200">
            <h3 class="text-lg font-semibold">Usage Logs</h3>
            <div class="flex gap-4 mt-2"><select id="filter-service" class="border rounded px-3 py-1 text-sm"><option value="">Tất cả service</option><option value="privacy">Privacy</option><option value="scoring">Scoring</option><option value="quiz">Quiz</option><option value="suggestion">Suggestion</option><option value="expert">Expert</option><option value="moderation">Moderation</option></select><select id="filter-status" class="border rounded px-3 py-1 text-sm"><option value="">Tất cả status</option><option value="success">Success</option><option value="error">Error</option></select><button onclick="loadLogs()" class="bg-blue-500 text-white px-4 py-1 rounded text-sm">Lọc</button></div>
        </div>
        <div class="overflow-x-auto"><table class="w-full table-hover"><thead class="bg-gray-50"><tr><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">ID</th><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Correlation ID</th><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">User</th><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Service</th><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Latency</th><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">IP</th><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Thời gian</th></tr></thead><tbody id="logs-table"></tbody></table></div>
    </div>
    <script>
        const API_KEY = localStorage.getItem('admin_api_key');
        async function loadLogs() {
            const service = document.getElementById('filter-service').value;
            const status = document.getElementById('filter-status').value;
            let url = '/admin/api/logs?limit=100';
            if(service) url += `&service=${service}`;
            if(status) url += `&status=${status}`;
            const response = await fetch(url, { headers: { 'X-Internal-Key': API_KEY } });
            const data = await response.json();
            document.getElementById('logs-table').innerHTML = (data.logs || []).map(l => `<tr class="border-b"><td class="px-6 py-3 text-sm">${l.id}</td><td class="px-6 py-3 text-sm font-mono text-xs">${l.correlation_id}</td><td class="px-6 py-3 text-sm">${l.user_id || '-'}</td><td class="px-6 py-3 text-sm"><span class="px-2 py-1 rounded-full text-xs bg-gray-100">${l.service_name}</span></td><td class="px-6 py-3 text-sm"><span class="px-2 py-1 rounded-full text-xs ${l.status === 'success' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}">${l.status}</span></td><td class="px-6 py-3 text-sm">${l.latency_ms}ms</td><td class="px-6 py-3 text-sm">${l.ip_address || '-'}</td><td class="px-6 py-3 text-sm">${new Date(l.created_at).toLocaleString('vi-VN')}</td></tr>`).join('');
        }
        loadLogs();
    </script>
    """


@router.get("/admin/api/pages/stats", response_class=HTMLResponse)
async def page_stats():
    return """
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="bg-white rounded-lg shadow-md p-6"><h3 class="text-lg font-semibold mb-4">Requests theo service</h3><canvas id="service-stats-chart" height="300"></canvas></div>
        <div class="bg-white rounded-lg shadow-md p-6"><h3 class="text-lg font-semibold mb-4">Xu hướng 30 ngày</h3><canvas id="trend-30-chart" height="300"></canvas></div>
        <div class="bg-white rounded-lg shadow-md p-6"><h3 class="text-lg font-semibold mb-4">Top 10 users dùng nhiều nhất</h3><canvas id="top-users-chart" height="300"></canvas></div>
        <div class="bg-white rounded-lg shadow-md p-6"><h3 class="text-lg font-semibold mb-4">Success rate theo service</h3><canvas id="success-rate-chart" height="300"></canvas></div>
    </div>
    <script>
        const API_KEY = localStorage.getItem('admin_api_key');
        async function loadStats() {
            const response = await fetch('/admin/api/stats/dashboard', { headers: { 'X-Internal-Key': API_KEY } });
            const data = await response.json();
            new Chart(document.getElementById('service-stats-chart'), { type: 'pie', data: { labels: Object.keys(data.service_stats || {}), datasets: [{ data: Object.values(data.service_stats || {}), backgroundColor: ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'] }] } });
            new Chart(document.getElementById('trend-30-chart'), { type: 'line', data: { labels: (data.trend_data || []).map(d => d.date), datasets: [{ label: 'Requests', data: (data.trend_data || []).map(d => d.count), borderColor: '#3b82f6', fill: true }] } });
            const topUsers = await fetch('/admin/api/stats/top-users', { headers: { 'X-Internal-Key': API_KEY } });
            const topUsersData = await topUsers.json();
            new Chart(document.getElementById('top-users-chart'), { type: 'bar', data: { labels: (topUsersData.top_users || []).map(u => u.username), datasets: [{ label: 'Requests', data: (topUsersData.top_users || []).map(u => u.request_count), backgroundColor: '#10b981' }] } });
        }
        loadStats();
    </script>
    """


# ========== API Endpoints ==========
@router.get("/admin/api/stats/dashboard")
async def dashboard_stats(db: AsyncSession = Depends(get_db)):
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)

    total_users = await db.scalar(select(func.count()).select_from(User)) or 0
    total_requests = await db.scalar(select(func.count()).select_from(UsageLog)) or 0
    today_requests = await db.scalar(select(func.count()).select_from(UsageLog).where(UsageLog.created_at >= today_start)) or 0

    total_tokens_result = await db.execute(select(func.sum(LLMUsageLog.total_tokens)).select_from(LLMUsageLog))
    total_tokens = total_tokens_result.scalar() or 0

    success_count = await db.scalar(select(func.count()).select_from(UsageLog).where(UsageLog.status == "success")) or 0
    success_rate = round(success_count / total_requests *
                         100, 1) if total_requests > 0 else 0

    service_stats_result = await db.execute(select(UsageLog.service_name, func.count(UsageLog.id)).group_by(UsageLog.service_name))
    service_stats = {row[0]: row[1] for row in service_stats_result.all()}

    trend_data = []
    for i in range(6, -1, -1):
        day = now - timedelta(days=i)
        day_start = datetime(day.year, day.month, day.day)
        day_end = day_start + timedelta(days=1)
        count = await db.scalar(select(func.count()).select_from(UsageLog).where(UsageLog.created_at >= day_start, UsageLog.created_at < day_end)) or 0
        trend_data.append({"date": day.strftime("%d/%m"), "count": count})

    return {
        "total_users": total_users, "total_requests": total_requests, "today_requests": today_requests,
        "total_tokens": total_tokens, "estimated_cost": total_tokens * 0.000001,
        "success_count": success_count, "success_rate": success_rate,
        "service_stats": service_stats, "trend_data": trend_data
    }


@router.get("/admin/api/stats/top-users")
async def top_users(limit: int = 10, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User.id, User.username, func.count(UsageLog.id).label('count'))
        .join(UsageLog, User.id == UsageLog.user_id)
        .group_by(User.id, User.username)
        .order_by(func.count(UsageLog.id).desc())
        .limit(limit)
    )
    return {"top_users": [{"id": r[0], "username": r[1], "request_count": r[2]} for r in result.all()]}


@router.get("/admin/api/users")
async def list_users(page: int = 1, limit: int = 10, db: AsyncSession = Depends(get_db)):
    offset = (page - 1) * limit
    total = await db.scalar(select(func.count()).select_from(User)) or 0
    result = await db.execute(select(User).order_by(User.id.desc()).offset(offset).limit(limit))
    users = result.scalars().all()
    return {
        "users": [{"id": u.id, "username": u.username, "email": u.email, "is_active": u.is_active, "created_at": u.created_at.isoformat()} for u in users],
        "total": total
    }


@router.post("/admin/api/users")
async def create_user_api(user_data: dict, db: AsyncSession = Depends(get_db)):
    new_user = User(username=user_data["username"], email=user_data["email"],
                    hashed_password="temporary", is_active=True)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return {"id": new_user.id, "username": new_user.username, "email": new_user.email}


@router.put("/admin/api/users/{user_id}")
async def update_user(user_id: int, user_data: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    if "is_active" in user_data:
        user.is_active = user_data["is_active"]
    await db.commit()
    return {"message": "Updated"}


@router.delete("/admin/api/users/{user_id}")
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    await db.delete(user)
    await db.commit()
    return {"message": "Deleted"}


@router.post("/admin/api/users/{user_id}/api-keys")
async def create_api_key_admin(user_id: int, db: AsyncSession = Depends(get_db)):
    new_key = APIKey(key=f"bdh_{uuid.uuid4().hex}{uuid.uuid4().hex[:8]}", user_id=user_id,
                     name=f"API Key for user {user_id}", is_active=True, expires_at=datetime.utcnow() + timedelta(days=90))
    db.add(new_key)
    await db.commit()
    await db.refresh(new_key)
    return {"api_key": new_key.key, "expires_at": new_key.expires_at}


@router.get("/admin/api/api-keys")
async def list_api_keys_admin(user_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    if user_id:
        result = await db.execute(select(APIKey).where(APIKey.user_id == user_id))
    else:
        result = await db.execute(select(APIKey))
    keys = result.scalars().all()
    return {"api_keys": [{"id": k.id, "key": k.key[:20] + "...", "user_id": k.user_id, "name": k.name, "is_active": k.is_active, "expires_at": k.expires_at.isoformat() if k.expires_at else None, "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None} for k in keys]}


@router.get("/admin/api/logs")
async def get_logs(service: Optional[str] = None, status: Optional[str] = None, limit: int = 100, db: AsyncSession = Depends(get_db)):
    query = select(UsageLog).order_by(UsageLog.id.desc()).limit(limit)
    if service:
        query = query.where(UsageLog.service_name == service)
    if status:
        query = query.where(UsageLog.status == status)
    result = await db.execute(query)
    logs = result.scalars().all()
    return {"logs": [{"id": l.id, "correlation_id": l.correlation_id, "user_id": l.user_id, "service_name": l.service_name, "status": l.status, "latency_ms": l.latency_ms, "ip_address": l.ip_address, "created_at": l.created_at.isoformat()} for l in logs]}
