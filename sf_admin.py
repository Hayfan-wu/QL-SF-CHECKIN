"""
顺丰速运 sfsyUrl 管理面板
功能：管理 sfsyUrl、青龙面板配置、一键同步
"""

import json
import os
import hashlib
import time
import re
from urllib.parse import parse_qs, urlparse, unquote
from flask import Flask, request, jsonify, Response

import requests
requests.packages.urllib3.disable_warnings()

app = Flask(__name__)

# 配置文件路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, 'admin_data.json')


# ==================== 数据存储 ====================
def load_data():
    """加载数据"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'urls': [], 'qinglong': {'url': '', 'client_id': '', 'client_secret': ''}}


def save_data(data):
    """保存数据"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ==================== sfsyUrl 解析 ====================
def parse_sfsy_url(url_or_ck):
    """解析 sfsyUrl/CK，提取手机号和用户ID"""
    info = {'url': url_or_ck, 'phone': '', 'user_id': '', 'type': 'unknown', 'valid': False}
    
    try:
        decoded = unquote(url_or_ck.strip())
        
        # CK 格式: sessionId=xxx;_login_mobile_=xxx;_login_user_id_=xxx
        if decoded.startswith('sessionId=') or '_login_mobile_=' in decoded:
            info['type'] = 'ck'
            cookie_dict = {}
            for item in decoded.split(';'):
                item = item.strip()
                if '=' in item:
                    k, v = item.split('=', 1)
                    cookie_dict[k] = v
            info['phone'] = cookie_dict.get('_login_mobile_', '')
            info['user_id'] = cookie_dict.get('_login_user_id_', '')
            if info['phone'] and info['user_id']:
                info['valid'] = True
        
        # URL 格式
        elif 'sf-express.com' in decoded:
            info['type'] = 'url'
            parsed = urlparse(decoded)
            params = parse_qs(parsed.query)
            info['phone'] = params.get('mobile', [''])[0]
            info['user_id'] = params.get('userId', [''])[0]
            if info['phone'] or info['user_id']:
                info['valid'] = True
    
    except Exception:
        pass
    
    return info


def test_url_valid(url_or_ck):
    """测试 sfsyUrl 是否有效"""
    try:
        session = requests.Session()
        decoded = unquote(url_or_ck.strip())
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 MicroMessenger/8.0.40 NetType/WIFI Language/zh_CN',
            'sysCode': 'MCS-MIMP-CORE',
            'platform': 'MINI_PROGRAM',
        }
        
        # 按 CK 格式处理
        if '_login_mobile_=' in decoded:
            cookie_dict = {}
            for item in decoded.split(';'):
                item = item.strip()
                if '=' in item:
                    k, v = item.split('=', 1)
                    cookie_dict[k] = v
                    session.cookies.set(k, v, domain='mcs-mimp-web.sf-express.com')
        else:
            session.get(decoded, headers=headers, timeout=10)
        
        # 测试调用积分接口
        token = 'wwesldfs29aniversaryvdld29'
        sys_code = 'MCS-MIMP-CORE'
        timestamp = str(int(time.time() * 1000))
        sign_str = token + timestamp + sys_code
        signature = hashlib.md5(sign_str.encode()).hexdigest()
        
        headers.update({
            'timestamp': timestamp,
            'signature': signature,
            'Content-Type': 'application/json',
        })
        
        api_url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberIntegral~userInfoServices~personalInfoNew'
        resp = session.post(api_url, headers=headers, json={}, timeout=10)
        data = resp.json()
        
        if data.get('success'):
            return True, '有效'
        
        error_msg = data.get('errorMessage', '')
        if '用户信息失效' in error_msg:
            return False, '已过期'
        elif '系统繁忙' in error_msg:
            return False, '系统繁忙'
        else:
            return False, error_msg or '未知错误'
    
    except Exception as e:
        return False, str(e)[:50]


# ==================== 青龙面板 ====================
def get_ql_token(ql_config):
    """获取青龙面板 token"""
    try:
        url = ql_config['url'].rstrip('/')
        resp = requests.post(
            f'{url}/open/auth/token',
            params={
                'client_id': ql_config['client_id'],
                'client_secret': ql_config['client_secret']
            },
            timeout=10
        )
        data = resp.json()
        if data.get('code') == 200:
            return data['data']['token']
        return None
    except Exception:
        return None


def test_ql_connection(ql_config):
    """测试青龙面板连接"""
    if not ql_config.get('url') or not ql_config.get('client_id') or not ql_config.get('client_secret'):
        return False, '配置不完整'
    
    token = get_ql_token(ql_config)
    if token:
        return True, '连接正常'
    return False, '连接失败，请检查地址和密钥'


def get_ql_env(ql_config, name='sfsyUrl'):
    """获取青龙环境变量值"""
    try:
        token = get_ql_token(ql_config)
        if not token:
            return []
        
        url = ql_config['url'].rstrip('/')
        resp = requests.get(
            f'{url}/open/envs',
            headers={'Authorization': f'Bearer {token}'},
            params={'searchValue': name},
            timeout=10
        )
        data = resp.json()
        if data.get('code') == 200:
            return data.get('data', [])
        return []
    except Exception:
        return []


def sync_to_ql(ql_config, url_value, name='sfsyUrl', remarks=''):
    """同步 sfsyUrl 到青龙"""
    try:
        token = get_ql_token(ql_config)
        if not token:
            return False, '获取 token 失败'
        
        url = ql_config['url'].rstrip('/')
        
        # 先检查是否已存在
        envs = get_ql_env(ql_config, name)
        existing = None
        for env in envs:
            if env.get('name') == name:
                existing = env
                break
        
        if existing:
            # 更新
            resp = requests.put(
                f'{url}/open/envs',
                headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                json={
                    'id': existing['id'],
                    'name': name,
                    'value': url_value,
                    'remarks': remarks or existing.get('remarks', '')
                },
                timeout=10
            )
        else:
            # 新增
            resp = requests.post(
                f'{url}/open/envs',
                headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                json=[{
                    'name': name,
                    'value': url_value,
                    'remarks': remarks
                }],
                timeout=10
            )
        
        data = resp.json()
        if data.get('code') == 200:
            return True, '同步成功'
        return False, data.get('message', '同步失败')
    
    except Exception as e:
        return False, str(e)[:80]


def sync_all_to_ql(ql_config, urls, name='sfsyUrl'):
    """批量同步到青龙（用 & 拼接）"""
    if not urls:
        return False, '没有可同步的 URL'
    
    combined = '&'.join(urls)
    return sync_to_ql(ql_config, combined, name, f'共{len(urls)}个账号')


# ==================== API 路由 ====================
INDEX_HTML = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>顺丰 sfsyUrl 管理面板</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    background: #f0f2f5;
    color: #333;
    padding: 20px;
}
.container {
    max-width: 900px;
    margin: 0 auto;
}
.header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 24px;
    border-radius: 12px;
    margin-bottom: 20px;
}
.header h1 { font-size: 24px; margin-bottom: 8px; }
.header p { opacity: 0.9; font-size: 14px; }
.card {
    background: white;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 16px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.card h2 {
    font-size: 18px;
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
}
.tabs {
    display: flex;
    gap: 8px;
    margin-bottom: 20px;
}
.tab {
    padding: 10px 20px;
    background: white;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    color: #666;
    transition: all 0.2s;
}
.tab.active {
    background: #667eea;
    color: white;
}
.tab:hover:not(.active) { background: #f0f0f0; }
.form-group { margin-bottom: 16px; }
.form-group label {
    display: block;
    margin-bottom: 6px;
    font-size: 14px;
    color: #555;
    font-weight: 500;
}
.form-group input, .form-group textarea {
    width: 100%;
    padding: 10px 12px;
    border: 1px solid #d9d9d9;
    border-radius: 8px;
    font-size: 14px;
    transition: border-color 0.2s;
}
.form-group input:focus, .form-group textarea:focus {
    outline: none;
    border-color: #667eea;
}
.form-group textarea {
    resize: vertical;
    min-height: 80px;
    font-family: monospace;
}
.btn {
    padding: 10px 20px;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 500;
    transition: all 0.2s;
}
.btn-primary { background: #667eea; color: white; }
.btn-primary:hover { background: #5568d3; }
.btn-success { background: #52c41a; color: white; }
.btn-success:hover { background: #45a917; }
.btn-danger { background: #ff4d4f; color: white; }
.btn-danger:hover { background: #e63946; }
.btn-secondary { background: #f0f0f0; color: #333; }
.btn-secondary:hover { background: #e0e0e0; }
.btn-sm { padding: 6px 12px; font-size: 12px; }
.url-item {
    background: #fafafa;
    border: 1px solid #eee;
    border-radius: 8px;
    padding: 14px;
    margin-bottom: 10px;
}
.url-item-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
}
.url-phone {
    font-weight: 600;
    color: #333;
    font-size: 15px;
}
.url-type {
    display: inline-block;
    padding: 2px 8px;
    background: #e6f7ff;
    color: #1890ff;
    border-radius: 4px;
    font-size: 12px;
    margin-left: 8px;
}
.url-preview {
    font-family: monospace;
    font-size: 12px;
    color: #888;
    word-break: break-all;
    margin-bottom: 10px;
    background: #f5f5f5;
    padding: 8px;
    border-radius: 6px;
}
.url-actions { display: flex; gap: 8px; }
.alert {
    padding: 12px 16px;
    border-radius: 8px;
    margin-bottom: 12px;
    font-size: 14px;
}
.alert-success { background: #f6ffed; border: 1px solid #b7eb8f; color: #389e0d; }
.alert-error { background: #fff2f0; border: 1px solid #ffccc7; color: #cf1322; }
.alert-warning { background: #fffbe6; border: 1px solid #ffe58f; color: #d48806; }
.alert-info { background: #e6f7ff; border: 1px solid #91d5ff; color: #0050b3; }
.stats {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    margin-bottom: 20px;
}
.stat-card {
    background: white;
    border-radius: 10px;
    padding: 16px;
    text-align: center;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.stat-card .num {
    font-size: 28px;
    font-weight: 700;
    color: #667eea;
}
.stat-card .label {
    font-size: 13px;
    color: #999;
    margin-top: 4px;
}
.empty {
    text-align: center;
    padding: 40px 20px;
    color: #999;
}
.empty .icon { font-size: 48px; margin-bottom: 12px; }
.hidden { display: none; }
.status-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 12px;
    margin-left: 6px;
}
.status-ok { background: #f6ffed; color: #52c41a; }
.status-fail { background: #fff2f0; color: #ff4d4f; }
.status-testing { background: #e6f7ff; color: #1890ff; }
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>📦 顺丰 sfsyUrl 管理面板</h1>
        <p>管理账号、配置青龙、一键同步</p>
    </div>
    <div class="stats">
        <div class="stat-card">
            <div class="num" id="stat-local">0</div>
            <div class="label">本地账号</div>
        </div>
        <div class="stat-card">
            <div class="num" id="stat-ql">0</div>
            <div class="label">青龙账号</div>
        </div>
        <div class="stat-card">
            <div class="num" id="stat-status">-</div>
            <div class="label">青龙连接</div>
        </div>
    </div>
    <div class="tabs">
        <button class="tab active" data-tab="urls">📋 账号管理</button>
        <button class="tab" data-tab="qinglong">☁️ 青龙配置</button>
    </div>
    <div id="tab-urls" class="card">
        <h2>➕ 添加账号</h2>
        <div class="form-group">
            <label>sfsyUrl / CK 字符串</label>
            <textarea id="input-url" placeholder="粘贴 sfsyUrl 或 CK 格式：&#10;sessionId=xxx;_login_mobile_=13800138000;_login_user_id_=xxx"></textarea>
        </div>
        <button class="btn btn-primary" onclick="addUrl()">添加账号</button>
        <button class="btn btn-success" onclick="syncAll()" style="float:right;">☁️ 全部同步到青龙</button>
    </div>
    <div class="card">
        <h2>📋 账号列表</h2>
        <div id="url-list">
            <div class="empty">
                <div class="icon">📭</div>
                <p>暂无账号，请添加</p>
            </div>
        </div>
    </div>
    <div id="tab-qinglong" class="card hidden">
        <h2>☁️ 青龙面板配置</h2>
        <div id="ql-status"></div>
        <div class="form-group">
            <label>青龙地址</label>
            <input type="text" id="ql-url" placeholder="http://192.168.1.100:5700">
        </div>
        <div class="form-group">
            <label>Client ID</label>
            <input type="text" id="ql-client-id" placeholder="应用 Client ID">
        </div>
        <div class="form-group">
            <label>Client Secret</label>
            <input type="password" id="ql-client-secret" placeholder="应用 Client Secret">
        </div>
        <button class="btn btn-primary" onclick="saveQLConfig()">保存配置</button>
        <button class="btn btn-secondary" onclick="testQL()">测试连接</button>
    </div>
</div>
<script>
var currentTab = 'urls';
document.querySelectorAll('.tab').forEach(function(btn) {
    btn.onclick = function() {
        var tab = this.getAttribute('data-tab');
        currentTab = tab;
        document.querySelectorAll('.tab').forEach(function(b) { b.classList.remove('active'); });
        this.classList.add('active');
        document.getElementById('tab-urls').classList.add('hidden');
        document.getElementById('tab-qinglong').classList.add('hidden');
        document.getElementById('tab-' + tab).classList.remove('hidden');
        if (tab === 'qinglong') loadQLConfig();
    };
});
function api(path, method, data) {
    var opts = {
        method: method || 'GET',
        headers: { 'Content-Type': 'application/json' }
    };
    if (data) opts.body = JSON.stringify(data);
    return fetch(path, opts).then(function(r) { return r.json(); });
}
function loadUrls() {
    api('/api/urls').then(function(res) {
        document.getElementById('stat-local').textContent = res.count;
        var list = document.getElementById('url-list');
        if (res.urls.length === 0) {
            list.innerHTML = '<div class="empty"><div class="icon">📭</div><p>暂无账号，请添加</p></div>';
            return;
        }
        var html = '';
        for (var i = 0; i < res.urls.length; i++) {
            var item = res.urls[i];
            var typeLabel = item.type === 'ck' ? 'CK格式' : 'URL格式';
            html += '<div class="url-item">' +
                '<div class="url-item-header">' +
                '<div><span class="url-phone">' + (item.phone || '未知手机号') + '</span>' +
                '<span class="url-type">' + typeLabel + '</span></div>' +
                '<span class="status-badge status-testing" id="status-' + item.index + '">待检测</span>' +
                '</div>' +
                '<div class="url-preview">' + item.url + '</div>' +
                '<div class="url-actions">' +
                '<button class="btn btn-secondary btn-sm" onclick="testUrl(' + item.index + ')">🔍 测试有效性</button> ' +
                '<button class="btn btn-success btn-sm" onclick="syncOne(' + item.index + ')">☁️ 同步青龙</button> ' +
                '<button class="btn btn-danger btn-sm" onclick="deleteUrl(' + item.index + ')">🗑️ 删除</button>' +
                '</div></div>';
        }
        list.innerHTML = html;
    });
}
function addUrl() {
    var url = document.getElementById('input-url').value.trim();
    if (!url) { alert('请输入 sfsyUrl 或 CK'); return; }
    api('/api/url/add', 'POST', { url: url }).then(function(res) {
        if (res.success) {
            alert('✅ ' + res.message);
            document.getElementById('input-url').value = '';
            loadUrls();
        } else { alert('❌ ' + res.message); }
    });
}
function deleteUrl(index) {
    if (!confirm('确定删除这个账号吗？')) return;
    api('/api/url/delete', 'POST', { index: index }).then(function(res) {
        if (res.success) { loadUrls(); } else { alert('❌ ' + res.message); }
    });
}
function testUrl(index) {
    var badge = document.getElementById('status-' + index);
    if (badge) { badge.textContent = '检测中...'; badge.className = 'status-badge status-testing'; }
    api('/api/url/test', 'POST', { index: index }).then(function(res) {
        if (badge) {
            if (res.valid) { badge.textContent = '✅ 有效'; badge.className = 'status-badge status-ok'; }
            else { badge.textContent = '❌ ' + res.message; badge.className = 'status-badge status-fail'; }
        }
    });
}
function syncOne(index) {
    api('/api/urls').then(function(res) {
        var item = res.urls.find(function(u) { return u.index === index; });
        if (!item) return;
        api('/api/qinglong/sync', 'POST', { url: item.full_url }).then(function(r) {
            if (r.success) { alert('✅ ' + r.message); loadQLStatus(); }
            else { alert('❌ ' + r.message); }
        });
    });
}
function syncAll() {
    if (!confirm('确定同步所有账号到青龙？')) return;
    api('/api/qinglong/sync_all', 'POST', {}).then(function(res) {
        if (res.success) { alert('✅ ' + res.message + '（共 ' + res.total + ' 个）'); loadQLStatus(); }
        else { alert('❌ ' + res.message); }
    });
}
function loadQLConfig() {
    api('/api/qinglong').then(function(res) {
        document.getElementById('ql-url').value = res.url || '';
        document.getElementById('ql-client-id').value = res.client_id || '';
        if (!res.has_secret) { document.getElementById('ql-client-secret').placeholder = ''; }
        else { document.getElementById('ql-client-secret').placeholder = '已保存（显示为 ***）'; }
        updateQLStatus(res.connected, res.ql_count);
    });
}
function saveQLConfig() {
    var url = document.getElementById('ql-url').value.trim();
    var clientId = document.getElementById('ql-client-id').value.trim();
    var clientSecret = document.getElementById('ql-client-secret').value;
    api('/api/qinglong/config', 'POST', { url: url, client_id: clientId, client_secret: clientSecret }).then(function(res) {
        alert(res.message);
        if (res.connected) { loadQLStatus(); }
    });
}
function testQL() {
    var url = document.getElementById('ql-url').value.trim();
    var clientId = document.getElementById('ql-client-id').value.trim();
    var clientSecret = document.getElementById('ql-client-secret').value;
    api('/api/qinglong/config', 'POST', { url: url, client_id: clientId, client_secret: clientSecret }).then(function(res) {
        alert(res.message);
        loadQLStatus();
    });
}
function updateQLStatus(connected, count) {
    document.getElementById('stat-ql').textContent = count || 0;
    document.getElementById('stat-status').textContent = connected ? '✅' : '❌';
    var statusDiv = document.getElementById('ql-status');
    if (connected) {
        statusDiv.innerHTML = '<div class="alert alert-success">✅ 青龙连接正常，当前有 ' + count + ' 个 sfsyUrl 账号</div>';
    } else if (document.getElementById('ql-url').value) {
        statusDiv.innerHTML = '<div class="alert alert-warning">⚠️ 已配置但连接失败，请检查地址和密钥</div>';
    } else {
        statusDiv.innerHTML = '<div class="alert alert-info">💡 请填写青龙面板信息后保存</div>';
    }
}
function loadQLStatus() {
    api('/api/qinglong').then(function(res) { updateQLStatus(res.connected, res.ql_count); });
}
loadUrls();
loadQLStatus();
</script>
</body>
</html>'''


@app.route('/')
def index():
    return Response(INDEX_HTML, mimetype='text/html')


@app.route('/api/urls')
def api_urls():
    """获取 URL 列表"""
    data = load_data()
    result = []
    for i, url_item in enumerate(data['urls']):
        info = parse_sfsy_url(url_item)
        masked_phone = ''
        if info['phone'] and len(info['phone']) >= 11:
            masked_phone = info['phone'][:3] + '****' + info['phone'][7:]
        result.append({
            'index': i,
            'url': url_item[:80] + '...' if len(url_item) > 80 else url_item,
            'full_url': url_item,
            'phone': masked_phone,
            'user_id': info['user_id'][:8] + '...' if len(info['user_id']) > 8 else info['user_id'],
            'type': info['type'],
        })
    return jsonify({'urls': result, 'count': len(result)})


@app.route('/api/url/add', methods=['POST'])
def api_url_add():
    """添加 URL"""
    body = request.get_json()
    url = body.get('url', '').strip()
    
    if not url:
        return jsonify({'success': False, 'message': 'URL 不能为空'})
    
    data = load_data()
    
    # 检查是否已存在
    if url in data['urls']:
        return jsonify({'success': False, 'message': 'URL 已存在', 'is_new': False})
    
    info = parse_sfsy_url(url)
    if not info['valid']:
        return jsonify({'success': False, 'message': 'URL 格式不正确，未识别到手机号或用户ID'})
    
    data['urls'].append(url)
    save_data(data)
    
    return jsonify({'success': True, 'message': '添加成功', 'is_new': True})


@app.route('/api/url/delete', methods=['POST'])
def api_url_delete():
    """删除 URL"""
    body = request.get_json()
    index = body.get('index', -1)
    
    data = load_data()
    if index < 0 or index >= len(data['urls']):
        return jsonify({'success': False, 'message': '索引无效'})
    
    deleted = data['urls'].pop(index)
    save_data(data)
    
    return jsonify({'success': True, 'message': '删除成功'})


@app.route('/api/url/test', methods=['POST'])
def api_url_test():
    """测试 URL 是否有效"""
    body = request.get_json()
    index = body.get('index', -1)
    
    data = load_data()
    if index < 0 or index >= len(data['urls']):
        return jsonify({'success': False, 'message': '索引无效'})
    
    url = data['urls'][index]
    valid, msg = test_url_valid(url)
    
    return jsonify({'success': True, 'valid': valid, 'message': msg})


@app.route('/api/qinglong')
def api_qinglong():
    """获取青龙配置"""
    data = load_data()
    ql = data.get('qinglong', {})
    
    # 测试连接状态
    connected = False
    ql_count = 0
    if ql.get('url') and ql.get('client_id') and ql.get('client_secret'):
        connected, _ = test_ql_connection(ql)
        if connected:
            envs = get_ql_env(ql, 'sfsyUrl')
            for env in envs:
                if env.get('name') == 'sfsyUrl':
                    ql_count = len(env.get('value', '').split('&'))
                    break
    
    return jsonify({
        'url': ql.get('url', ''),
        'client_id': ql.get('client_id', ''),
        'has_secret': bool(ql.get('client_secret', '')),
        'connected': connected,
        'ql_count': ql_count
    })


@app.route('/api/qinglong/config', methods=['POST'])
def api_qinglong_config():
    """保存青龙配置"""
    body = request.get_json()
    url = body.get('url', '').strip()
    client_id = body.get('client_id', '').strip()
    client_secret = body.get('client_secret', '').strip()
    
    data = load_data()
    
    # 如果没填新的 secret，保留原来的
    old_secret = data.get('qinglong', {}).get('client_secret', '')
    if not client_secret and old_secret:
        client_secret = old_secret
    
    data['qinglong'] = {
        'url': url,
        'client_id': client_id,
        'client_secret': client_secret
    }
    save_data(data)
    
    # 测试连接
    connected, msg = test_ql_connection(data['qinglong'])
    
    return jsonify({
        'success': True,
        'connected': connected,
        'message': f'配置已保存，{msg}'
    })


@app.route('/api/qinglong/sync', methods=['POST'])
def api_qinglong_sync():
    """同步单个到青龙"""
    body = request.get_json()
    url = body.get('url', '').strip()
    
    if not url:
        return jsonify({'success': False, 'message': 'URL 不能为空'})
    
    data = load_data()
    ql = data.get('qinglong', {})
    
    if not ql.get('url') or not ql.get('client_id') or not ql.get('client_secret'):
        return jsonify({'success': False, 'message': '请先配置青龙面板'})
    
    success, msg = sync_to_ql(ql, url)
    return jsonify({'success': success, 'message': msg})


@app.route('/api/qinglong/sync_all', methods=['POST'])
def api_qinglong_sync_all():
    """批量同步到青龙"""
    data = load_data()
    urls = data.get('urls', [])
    ql = data.get('qinglong', {})
    
    if not urls:
        return jsonify({'success': False, 'message': '没有可同步的账号'})
    
    if not ql.get('url') or not ql.get('client_id') or not ql.get('client_secret'):
        return jsonify({'success': False, 'message': '请先配置青龙面板'})
    
    success, msg = sync_all_to_ql(ql, urls)
    return jsonify({
        'success': success,
        'message': msg,
        'total': len(urls)
    })


if __name__ == '__main__':
    print("=" * 50)
    print("🚀 顺丰 sfsyUrl 管理面板启动中...")
    print("📱 访问地址: http://127.0.0.1:8765")
    print("=" * 50)
    app.run(host='0.0.0.0', port=8765, debug=False)
