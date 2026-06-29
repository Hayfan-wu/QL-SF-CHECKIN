// 顺丰速运 Web 管理面板 - JavaScript
var currentTab = 'scan';
var scanSessionId = null;
var scanPollTimer = null;

// API 封装
function api(path, method, data) {
    var opts = {
        method: method || 'GET',
        headers: { 'Content-Type': 'application/json' }
    };
    if (data) {
        opts.body = JSON.stringify(data);
    }
    return fetch(path, opts).then(function(res) {
        return res.json();
    });
}

// 切换标签
function switchTab(tab) {
    currentTab = tab;
    var tabs = document.querySelectorAll('.tab');
    for (var i = 0; i < tabs.length; i++) {
        var tabNames = ['scan', 'extract', 'urls', 'qinglong'];
        if (tabs[i].getAttribute('data-tab') === tab) {
            tabs[i].classList.add('active');
        } else {
            tabs[i].classList.remove('active');
        }
    }
    var cards = document.querySelectorAll('.card');
    for (var j = 0; j < cards.length; j++) {
        cards[j].style.display = 'none';
    }
    document.getElementById('tab-' + tab).style.display = 'block';

    if (tab === 'urls') loadUrls();
    if (tab === 'qinglong') loadQLConfig();
}

// 生成星级
function getStars(score) {
    var n = Math.min(5, Math.floor(score / 50) + 1);
    var stars = '';
    for (var i = 0; i < n; i++) stars += '⭐';
    return stars;
}

// ========== 扫码登录 ==========
function startScan() {
    var area = document.getElementById('scan-area');
    area.innerHTML = '<div style="text-align:center; padding: 40px;"><div class="loading"></div><p style="margin-top:15px; color:#6b7280;">正在生成二维码...</p></div>';

    api('/api/scan/start').then(function(res) {
        scanSessionId = res.session_id;

        if (res.qrcodes && res.qrcodes.length > 0) {
            var html = '<div class="qr-container">';
            for (var i = 0; i < res.qrcodes.length; i++) {
                var qr = res.qrcodes[i];
                html += '<div class="qr-item">' +
                    '<img src="' + qr.qr_img + '" alt="扫码登录">' +
                    '<div class="status-badge status-waiting" id="qr-status-' + i + '">等待扫码</div>' +
                    '<div class="api-name">接口 ' + (i + 1) + '</div>' +
                    '</div>';
            }
            html += '</div>';
            html += '<div style="text-align:center; margin-top: 20px;">';
            html += '<p style="color:#6b7280;">请使用微信扫一扫，登录顺丰速运小程序</p>';
            html += '<button class="btn btn-secondary btn-sm" style="margin-top:10px;" id="btn-refresh-qr">🔄 刷新二维码</button>';
            html += '</div>';
            area.innerHTML = html;

            document.getElementById('btn-refresh-qr').onclick = startScan;
            startPolling();
        } else {
            area.innerHTML = '<div class="alert alert-warning">⚠️ 无法生成二维码，扫码接口可能已变更</div>' +
                '<div class="alert alert-info">💡 建议使用「📋 粘贴提取」功能，配合手机抓包APP使用</div>';
        }
    }).catch(function(e) {
        area.innerHTML = '<div class="alert alert-error">❌ 出错了: ' + e.message + '</div>';
    });
}

function startPolling() {
    if (scanPollTimer) clearInterval(scanPollTimer);
    scanPollTimer = setInterval(pollScan, 2000);
}

function pollScan() {
    if (!scanSessionId) return;

    api('/api/scan/poll?session_id=' + scanSessionId).then(function(res) {
        if (res.status === 'success') {
            clearInterval(scanPollTimer);
            var area = document.getElementById('scan-area');
            var html = '<div style="text-align:center; padding: 20px;">';
            html += '<div style="font-size: 48px;">✅</div>';
            html += '<h3 style="color: #059669; margin: 15px 0;">登录成功！</h3>';
            if (res.sfsy_url) {
                html += '<div class="alert alert-success" style="text-align:left;">';
                html += '<strong>sfsyUrl 已获取！</strong><br>';
                html += '<code style="font-size:11px; word-break:break-all;">' + res.sfsy_url.substring(0, 150) + '...</code>';
                html += '</div>';
                html += '<button class="btn btn-success" onclick="syncToQL(\'' + res.sfsy_url + '\')">☁️ 同步到青龙</button>';
            } else {
                html += '<div class="alert alert-warning">登录成功但未能构建完整的 sfsyUrl，建议使用抓包方式获取</div>';
            }
            html += '</div>';
            area.innerHTML = html;
        } else if (res.status === 'expired') {
            clearInterval(scanPollTimer);
            var area2 = document.getElementById('scan-area');
            area2.innerHTML = '<div style="text-align:center; padding: 40px;">' +
                '<div style="font-size: 48px;">⏰</div>' +
                '<h3 style="color: #d97706; margin: 15px 0;">二维码已过期</h3>' +
                '<button class="btn btn-primary" id="btn-restart-qr">🔄 重新生成</button>' +
                '</div>';
            document.getElementById('btn-restart-qr').onclick = startScan;
        } else if (res.status === 'scanned') {
            var badges = document.querySelectorAll('.qr-item .status-badge');
            for (var i = 0; i < badges.length; i++) {
                badges[i].textContent = '已扫码，请确认';
                badges[i].className = 'status-badge status-scanned';
            }
        }
    }).catch(function(e) {
        console.error(e);
    });
}

// ========== 粘贴提取 ==========
function extractUrls() {
    var text = document.getElementById('extract-text').value;
    if (!text.trim()) {
        alert('请先粘贴内容');
        return;
    }

    var resultDiv = document.getElementById('extract-result');
    resultDiv.innerHTML = '<div class="loading"></div> 正在分析...';

    api('/api/extract', 'POST', { text: text }).then(function(res) {
        if (res.urls && res.urls.length > 0) {
            var html = '<div class="alert alert-success">找到 ' + res.count + ' 个顺丰相关URL</div>';
            for (var i = 0; i < res.urls.length; i++) {
                var item = res.urls[i];
                html += '<div class="url-item">' +
                    '<div class="url-info">' +
                    '<div class="url-preview">' + item.url + '</div>' +
                    '<div class="url-meta">' +
                    '<span class="stars">' + getStars(item.score) + '</span>' +
                    '<span>质量分: ' + item.score + '/250</span>' +
                    '<span>' + item.length + '字符</span>' +
                    '<span>' + item.reasons.join(', ') + '</span>' +
                    '</div></div>' +
                    '<div class="url-actions">' +
                    '<button class="btn btn-success btn-sm" data-action="save" data-url="' + encodeURIComponent(item.url) + '">💾 保存</button> ' +
                    '<button class="btn btn-primary btn-sm" data-action="sync" data-url="' + encodeURIComponent(item.url) + '">☁️ 同步青龙</button>' +
                    '</div></div>';
            }
            resultDiv.innerHTML = html;

            // 绑定按钮事件
            var btns = resultDiv.querySelectorAll('button[data-action]');
            for (var j = 0; j < btns.length; j++) {
                btns[j].onclick = function() {
                    var url = decodeURIComponent(this.getAttribute('data-url'));
                    var action = this.getAttribute('data-action');
                    if (action === 'save') saveUrl(url);
                    else if (action === 'sync') syncToQL(url);
                };
            }
        } else {
            resultDiv.innerHTML = '<div class="alert alert-warning">没有找到有效的顺丰URL，请确认粘贴的内容包含 sf-express.com 域名</div>';
        }
    }).catch(function(e) {
        resultDiv.innerHTML = '<div class="alert alert-error">出错了: ' + e.message + '</div>';
    });
}

function saveUrl(url) {
    api('/api/save', 'POST', { url: url }).then(function(res) {
        if (res.success) {
            alert(res.is_new ? '保存成功！' : 'URL已存在');
            loadUrls();
        } else {
            alert('保存失败');
        }
    }).catch(function(e) {
        alert('出错: ' + e.message);
    });
}

function syncToQL(url) {
    api('/api/qinglong/sync', 'POST', { url: url }).then(function(res) {
        if (res.success) {
            alert('✅ ' + res.message);
            loadUrls();
        } else {
            alert('❌ ' + res.message);
        }
    }).catch(function(e) {
        alert('出错: ' + e.message);
    });
}

// ========== 账号管理 ==========
function loadUrls() {
    api('/api/urls').then(function(res) {
        var listDiv = document.getElementById('url-list');
        document.getElementById('stat-local').textContent = res.urls.length;

        if (res.urls.length === 0) {
            listDiv.innerHTML = '<div class="alert alert-info">暂无保存的账号</div>';
            return;
        }

        var html = '';
        for (var i = 0; i < res.urls.length; i++) {
            var item = res.urls[i];
            html += '<div class="url-item">' +
                '<div class="url-info">' +
                '<div class="url-preview">' + item.url + '</div>' +
                '<div class="url-meta">' +
                '<span class="stars">' + getStars(item.score) + '</span>' +
                '<span>质量分: ' + item.score + '/250</span>' +
                '<span>' + item.length + '字符</span>' +
                '</div></div>' +
                '<div class="url-actions">' +
                '<button class="btn btn-primary btn-sm" data-action="sync-one" data-idx="' + item.index + '" data-url="' + encodeURIComponent(item.full_url) + '">☁️ 同步青龙</button> ' +
                '<button class="btn btn-danger btn-sm" data-action="del-one" data-idx="' + item.index + '">🗑️ 删除</button>' +
                '</div></div>';
        }
        listDiv.innerHTML = html;

        // 绑定事件
        var btns = listDiv.querySelectorAll('button[data-action]');
        for (var j = 0; j < btns.length; j++) {
            btns[j].onclick = function() {
                var action = this.getAttribute('data-action');
                var idx = parseInt(this.getAttribute('data-idx'));
                var url = decodeURIComponent(this.getAttribute('data-url') || '');
                if (action === 'sync-one') syncToQL(url);
                else if (action === 'del-one') deleteUrl(idx);
            };
        }
    }).catch(function(e) {
        console.error(e);
    });

    // 加载青龙状态
    api('/api/qinglong').then(function(res) {
        document.getElementById('stat-ql').textContent = res.ql_urls_count || 0;
    }).catch(function() {});
}

function deleteUrl(index) {
    if (!confirm('确定删除这个账号吗？')) return;
    api('/api/delete', 'POST', { index: index }).then(function() {
        loadUrls();
    }).catch(function(e) {
        alert('出错: ' + e.message);
    });
}

function syncAll() {
    if (!confirm('确定同步所有账号到青龙？')) return;
    api('/api/qinglong/sync_all', 'POST', {}).then(function(res) {
        if (res.success) {
            alert('✅ 同步完成！成功 ' + res.synced + '/' + res.total + ' 个');
            loadUrls();
        } else {
            alert('❌ ' + res.message);
        }
    }).catch(function(e) {
        alert('出错: ' + e.message);
    });
}

// ========== 青龙配置 ==========
function loadQLConfig() {
    api('/api/qinglong').then(function(res) {
        document.getElementById('ql-url').value = res.url || '';
        document.getElementById('ql-client-id').value = res.client_id || '';
        if (res.client_secret) {
            document.getElementById('ql-client-secret').placeholder = '已保存（显示为***）';
        }

        var statusDiv = document.getElementById('ql-status');
        if (res.connected) {
            statusDiv.innerHTML = '<div class="alert alert-success">✅ 青龙连接正常，当前有 ' + res.ql_urls_count + ' 个 sfsyUrl 账号</div>';
        } else if (res.url) {
            statusDiv.innerHTML = '<div class="alert alert-warning">⚠️ 已配置但连接失败，请检查地址和密钥</div>';
        }
    }).catch(function() {});
}

function saveQLConfig() {
    var url = document.getElementById('ql-url').value;
    var clientId = document.getElementById('ql-client-id').value;
    var clientSecret = document.getElementById('ql-client-secret').value;

    if (!url || !clientId || !clientSecret) {
        alert('请填写完整信息');
        return;
    }

    var statusDiv = document.getElementById('ql-status');
    statusDiv.innerHTML = '<div class="loading"></div> 正在测试连接...';

    api('/api/qinglong/config', 'POST', {
        url: url,
        client_id: clientId,
        client_secret: clientSecret
    }).then(function(res) {
        if (res.success) {
            if (res.connected) {
                statusDiv.innerHTML = '<div class="alert alert-success">✅ 配置保存成功，连接正常！</div>';
            } else {
                statusDiv.innerHTML = '<div class="alert alert-warning">⚠️ 配置已保存但连接失败，请检查地址和密钥</div>';
            }
        } else {
            statusDiv.innerHTML = '<div class="alert alert-error">❌ ' + res.message + '</div>';
        }
    }).catch(function(e) {
        statusDiv.innerHTML = '<div class="alert alert-error">❌ 出错: ' + e.message + '</div>';
    });
}

// ========== 初始化 ==========
document.addEventListener('DOMContentLoaded', function() {
    // 标签切换
    var tabs = document.querySelectorAll('.tab');
    for (var i = 0; i < tabs.length; i++) {
        tabs[i].onclick = function() {
            switchTab(this.getAttribute('data-tab'));
        };
    }

    // 扫码登录
    var btnStart = document.getElementById('btn-start-scan');
    if (btnStart) btnStart.onclick = startScan;

    // 粘贴提取
    var btnExtract = document.getElementById('btn-extract');
    if (btnExtract) btnExtract.onclick = extractUrls;
    var btnClear = document.getElementById('btn-clear-text');
    if (btnClear) btnClear.onclick = function() {
        document.getElementById('extract-text').value = '';
    };

    // 账号管理
    var btnSyncAll = document.getElementById('btn-sync-all');
    if (btnSyncAll) btnSyncAll.onclick = syncAll;
    var btnRefresh = document.getElementById('btn-refresh-urls');
    if (btnRefresh) btnRefresh.onclick = loadUrls;

    // 青龙配置
    var btnSaveQL = document.getElementById('btn-save-ql');
    if (btnSaveQL) btnSaveQL.onclick = saveQLConfig;
    var btnLoadQL = document.getElementById('btn-load-ql');
    if (btnLoadQL) btnLoadQL.onclick = loadQLConfig;

    // 加载初始数据
    loadQLConfig();
});
