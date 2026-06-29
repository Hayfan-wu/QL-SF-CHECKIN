# -*- coding: utf-8 -*-
"""
顺丰速运 Web 管理面板
功能：
  - 扫码登录获取 sfsyUrl
  - 手动粘贴提取 sfsyUrl
  - 青龙面板配置
  - 账号管理
  - 一键同步到青龙

使用方法：
  python sf_web.py
  浏览器自动打开 http://127.0.0.1:8765
"""

import os
import sys
import re
import json
import time
import base64
import threading
import webbrowser
import urllib.parse
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

# ========== 配置 ==========
PORT = 8765
CONFIG_FILE = "qinglong_config.json"
SFSY_URL_FILE = "sfsyUrl.txt"
# ==========================

# 全局状态
scan_sessions = {}  # 扫码会话存储

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def load_urls():
    urls = []
    if os.path.exists(SFSY_URL_FILE):
        with open(SFSY_URL_FILE, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip()]
    return urls

def save_url(url):
    urls = load_urls()
    if url in urls:
        return False
    with open(SFSY_URL_FILE, "a", encoding="utf-8") as f:
        f.write(url + "\n")
    return True

def delete_url(index):
    urls = load_urls()
    if 0 <= index < len(urls):
        urls.pop(index)
        with open(SFSY_URL_FILE, "w", encoding="utf-8") as f:
            for u in urls:
                f.write(u + "\n")
        return True
    return False

def evaluate_url(url):
    score = 0
    keywords = {
        "memberId": 30, "member_id": 30, "userid": 30, "userId": 30,
        "token": 30, "access_token": 30, "accessToken": 30,
        "sign": 20, "signType": 20, "signIn": 15,
        "appid": 15, "appId": 15,
        "channel": 10, "platform": 10,
        "point": 10, "integral": 10,
        "sysCode": 10,
    }
    url_lower = url.lower()
    reasons = []
    for kw, points in keywords.items():
        if kw.lower() in url_lower:
            score += points
            reasons.append(kw)
    if len(url) > 300:
        score += 25
    elif len(url) > 200:
        score += 20
    elif len(url) > 100:
        score += 10
    if "sf-express.com" in url:
        score += 15
    return min(score, 250), reasons

def extract_sfsy_urls(text):
    urls = []
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]\'\\]+'
    found_urls = re.findall(url_pattern, text)
    for url in found_urls:
        url = url.rstrip('.,;:!?)]}')
        if any(d in url for d in ["sf-express.com", "sf-mobile.com", "sfintra.com"]):
            score, reasons = evaluate_url(url)
            if score >= 30:
                urls.append({"url": url, "score": score, "reasons": reasons})
    urls.sort(key=lambda x: x["score"], reverse=True)
    return urls

# 青龙相关
def get_ql_token(config):
    url = config.get("url", "").rstrip("/")
    client_id = config.get("client_id", "")
    client_secret = config.get("client_secret", "")
    if not all([url, client_id, client_secret]):
        return None
    try:
        token_url = f"{url}/open/auth/token?client_id={client_id}&client_secret={client_secret}"
        req = urllib.request.Request(token_url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            if data.get("code") == 200:
                return data["data"]["token"]
    except:
        pass
    return None

def get_ql_env(config, name):
    token = get_ql_token(config)
    if not token:
        return None
    url = config["url"].rstrip("/")
    try:
        env_url = f"{url}/open/envs?searchValue={urllib.parse.quote(name)}"
        req = urllib.request.Request(env_url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            if data.get("code") == 200:
                return data["data"]
    except:
        pass
    return None

def add_ql_env(config, name, value, remarks=""):
    token = get_ql_token(config)
    if not token:
        return False, "获取token失败"
    url = config["url"].rstrip("/")
    try:
        body = json.dumps([{"name": name, "value": value, "remarks": remarks}]).encode()
        req = urllib.request.Request(f"{url}/open/envs", data=body, headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            if data.get("code") == 200:
                return True, "添加成功"
            return False, data.get("message", "添加失败")
    except Exception as e:
        return False, str(e)

def update_ql_env(config, env_id, name, value, remarks=""):
    token = get_ql_token(config)
    if not token:
        return False, "获取token失败"
    url = config["url"].rstrip("/")
    try:
        body = json.dumps({"id": env_id, "name": name, "value": value, "remarks": remarks}).encode()
        req = urllib.request.Request(f"{url}/open/envs", data=body, headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }, method="PUT")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            if data.get("code") == 200:
                return True, "更新成功"
            return False, data.get("message", "更新失败")
    except Exception as e:
        return False, str(e)

def sync_to_qinglong(config, url):
    env_name = "sfsyUrl"
    envs = get_ql_env(config, env_name)
    if envs and len(envs) > 0:
        existing_value = envs[0].get("value", "")
        env_id = envs[0].get("id")
        remarks = envs[0].get("remarks", "")
        urls = [u.strip() for u in existing_value.split("\n") if u.strip()]
        if url in urls:
            return True, "URL已存在，无需重复添加"
        new_value = existing_value + "\n" + url if existing_value else url
        success, msg = update_ql_env(config, env_id, env_name, new_value, remarks)
        return success, msg + f"（共{len(urls)+1}个账号）"
    else:
        success, msg = add_ql_env(config, env_name, url, "顺丰速运签到")
        return success, msg + "（第1个账号）"

# 顺丰扫码登录（尝试多种接口）
SF_QR_APIS = [
    # 路径, 方法, 二维码字段名, 轮询字段名
    ("/commonPost/~memberNonactivity~memberQrCodeLoginService~generateQrCode", "POST", "qrCode", "qrId"),
    ("/commonRoutePost/member/qrcode/generate", "POST", "qrCodeUrl", "qrId"),
    ("/commonRoutePost/member/login/qrcode/create", "POST", "qrCode", "id"),
    ("/point/qrcode/generate", "POST", "qrCode", "qrToken"),
    ("/commonPost/~memberNonactivity~memberLoginService~generateLoginQrCode", "POST", "qrCodeImage", "qrCodeId"),
    ("/wechat/qrcode/generate", "POST", "qrcode", "token"),
]

SF_POLL_APIS = [
    "/commonPost/~memberNonactivity~memberQrCodeLoginService~queryQrCodeStatus",
    "/commonRoutePost/member/qrcode/status",
    "/commonRoutePost/member/login/qrcode/status",
    "/point/qrcode/status",
    "/commonPost/~memberNonactivity~memberLoginService~checkLoginQrCode",
    "/wechat/qrcode/status",
]

SF_BASE = "https://mcs-mimp-web.sf-express.com"

def sf_request(path, data=None, method="POST"):
    """发送顺丰API请求"""
    url = SF_BASE + path
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.40(0x18002829) NetType/WIFI Language/zh_CN",
        "Referer": "https://mcs-mimp-web.sf-express.com/",
        "Origin": "https://mcs-mimp-web.sf-express.com",
        "sysCode": "MINI_PROGRAM",
    }
    try:
        if data:
            body = json.dumps(data).encode()
        else:
            body = None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            return True, result
    except Exception as e:
        return False, str(e)

def find_field(data, *field_names):
    """在嵌套字典中查找字段"""
    if not isinstance(data, dict):
        return None
    # 先在当前层找
    for field in field_names:
        for key in data:
            if key.lower() == field.lower():
                return data[key]
    # 递归找
    for key, value in data.items():
        if isinstance(value, dict):
            result = find_field(value, *field_names)
            if result is not None:
                return result
        elif isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
            for item in value:
                result = find_field(item, *field_names)
                if result is not None:
                    return result
    return None

def generate_qrcode():
    """生成二维码，尝试多种接口"""
    results = []
    
    for i, (path, method, qr_field, id_field) in enumerate(SF_QR_APIS):
        try:
            data = {"channelType": "MINI_PROGRAM"} if method == "POST" else None
            success, result = sf_request(path, data, method)
            if not success:
                continue
            
            # 尝试获取二维码
            qr_code = find_field(result, qr_field, "qrCodeUrl", "qrcodeUrl", "qrCodeImage", "qrcode", "qr_code")
            qr_id = find_field(result, id_field, "qrId", "qrCodeId", "id", "token", "qrToken", "qr_token")
            
            if qr_code:
                # 如果是base64，直接用；如果是URL，可能需要处理
                if qr_code.startswith("http"):
                    # URL 形式的二维码图片
                    qr_img = qr_code
                elif qr_code.startswith("data:image"):
                    qr_img = qr_code
                else:
                    # 可能是 base64
                    qr_img = f"data:image/png;base64,{qr_code}"
                
                results.append({
                    "api_index": i,
                    "api_path": path,
                    "qr_img": qr_img,
                    "qr_id": qr_id or "",
                    "poll_path": SF_POLL_APIS[i] if i < len(SF_POLL_APIS) else SF_POLL_APIS[0],
                })
        except:
            continue
    
    return results

def poll_qrcode_status(qr_id, poll_path):
    """轮询二维码状态"""
    try:
        data = {"qrId": qr_id, "qrCodeId": qr_id, "id": qr_id, "token": qr_id}
        success, result = sf_request(poll_path, data, "POST")
        if not success:
            return "error", None, str(result)
        
        # 查找状态字段
        status = find_field(result, "status", "qrStatus", "codeStatus", "state")
        token = find_field(result, "token", "accessToken", "sessionToken", "sessionId")
        member_id = find_field(result, "memberId", "userId", "member_id", "user_id")
        
        # 状态判断
        status_str = str(status).lower() if status else "unknown"
        
        if "wait" in status_str or "waiting" in status_str or status_str == "0" or status_str == "1":
            return "waiting", None, None
        elif "scanned" in status_str or "confirm" in status_str or status_str == "2":
            return "scanned", None, None
        elif "success" in status_str or "done" in status_str or status_str == "3" or status_str == "100":
            return "success", {"token": token, "memberId": member_id}, None
        elif "expire" in status_str or "expired" in status_str or status_str == "-1" or status_str == "4":
            return "expired", None, None
        else:
            return "waiting", None, None
            
    except Exception as e:
        return "error", None, str(e)

def build_sfsy_url_from_login(login_data):
    """根据登录信息构建sfsyUrl（简化版，实际需要更多接口调用）"""
    # 这里只是构建一个基本的URL格式
    token = login_data.get("token", "")
    member_id = login_data.get("memberId", "")
    
    if not member_id or not token:
        return None
    
    # 构建基础URL
    params = {
        "memberId": member_id,
        "token": token,
        "channel": "MINI_PROGRAM",
        "platform": "MINI_PROGRAM",
        "sysCode": "MINI_PROGRAM",
    }
    
    base_url = "https://mcs-mimp-web.sf-express.com/member/point/index"
    query = urllib.parse.urlencode(params)
    return f"{base_url}?{query}"

# HTTP 处理
class WebHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # 静默日志
    
    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
    
    def send_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)
    
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        
        if path == "/" or path == "/index.html":
            self.send_html(INDEX_HTML)
        elif path == "/api/status":
            # 系统状态
            config = load_config()
            urls = load_urls()
            ql_ok = bool(get_ql_token(config))
            self.send_json({
                "urls_count": len(urls),
                "ql_configured": bool(config.get("url") and config.get("client_id")),
                "ql_connected": ql_ok,
            })
        elif path == "/api/urls":
            # 获取所有URL
            urls = load_urls()
            result = []
            for i, url in enumerate(urls):
                score, reasons = evaluate_url(url)
                result.append({
                    "index": i,
                    "url": url[:120] + "..." if len(url) > 120 else url,
                    "full_url": url,
                    "score": score,
                    "reasons": reasons[:5],
                    "length": len(url),
                })
            self.send_json({"urls": result})
        elif path == "/api/qinglong":
            # 获取青龙配置
            config = load_config()
            token = get_ql_token(config)
            ql_urls = 0
            if token:
                envs = get_ql_env(config, "sfsyUrl")
                if envs:
                    val = envs[0].get("value", "")
                    ql_urls = len([u for u in val.split("\n") if u.strip()])
            self.send_json({
                "url": config.get("url", ""),
                "client_id": config.get("client_id", ""),
                "client_secret": "***" if config.get("client_secret") else "",
                "connected": bool(token),
                "ql_urls_count": ql_urls,
            })
        elif path == "/api/scan/start":
            # 开始扫码
            results = generate_qrcode()
            session_id = str(int(time.time() * 1000))
            scan_sessions[session_id] = {
                "results": results,
                "status": "pending",
                "created_at": time.time(),
            }
            self.send_json({
                "session_id": session_id,
                "qrcodes": [{"api_index": r["api_index"], "qr_img": r["qr_img"]} for r in results[:3]],
                "count": len(results),
            })
        elif path == "/api/scan/poll":
            # 轮询扫码状态
            params = urllib.parse.parse_qs(parsed.query)
            session_id = params.get("session_id", [""])[0]
            
            session = scan_sessions.get(session_id)
            if not session:
                self.send_json({"status": "error", "message": "会话不存在"})
                return
            
            # 尝试每个可用的二维码
            all_waiting = True
            for result in session["results"]:
                qr_id = result.get("qr_id", "")
                poll_path = result.get("poll_path", "")
                if not qr_id:
                    continue
                
                status, data, error = poll_qrcode_status(qr_id, poll_path)
                
                if status == "success":
                    session["status"] = "success"
                    session["login_data"] = data
                    sfsy_url = build_sfsy_url_from_login(data)
                    session["sfsy_url"] = sfsy_url
                    if sfsy_url:
                        save_url(sfsy_url)
                    self.send_json({
                        "status": "success",
                        "sfsy_url": sfsy_url,
                        "login_data": {k: str(v)[:50] for k, v in data.items() if v},
                    })
                    return
                elif status == "scanned":
                    all_waiting = False
                elif status == "expired":
                    continue
                elif status == "error":
                    continue
            
            # 检查超时
            if time.time() - session["created_at"] > 180:
                session["status"] = "expired"
                self.send_json({"status": "expired"})
                return
            
            self.send_json({"status": "waiting" if all_waiting else "scanned"})
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length else "{}"
        try:
            data = json.loads(body)
        except:
            data = {}
        
        if path == "/api/extract":
            # 提取URL
            text = data.get("text", "")
            urls = extract_sfsy_urls(text)
            self.send_json({"urls": urls[:10], "count": len(urls)})
        
        elif path == "/api/save":
            # 保存URL
            url = data.get("url", "")
            if url:
                is_new = save_url(url)
                self.send_json({"success": True, "is_new": is_new})
            else:
                self.send_json({"success": False, "message": "URL为空"})
        
        elif path == "/api/delete":
            # 删除URL
            index = data.get("index", -1)
            success = delete_url(index)
            self.send_json({"success": success})
        
        elif path == "/api/qinglong/config":
            # 保存青龙配置
            config = {
                "url": data.get("url", "").rstrip("/"),
                "client_id": data.get("client_id", ""),
                "client_secret": data.get("client_secret", ""),
            }
            # 测试连接
            token = get_ql_token(config)
            if token:
                save_config(config)
                self.send_json({"success": True, "connected": True})
            else:
                # 连接失败也可以保存
                if data.get("force_save"):
                    save_config(config)
                    self.send_json({"success": True, "connected": False})
                else:
                    self.send_json({"success": False, "message": "连接失败，请检查地址和密钥"})
        
        elif path == "/api/qinglong/sync":
            # 同步到青龙
            config = load_config()
            url = data.get("url", "")
            if not url:
                self.send_json({"success": False, "message": "URL为空"})
                return
            if not config.get("url"):
                self.send_json({"success": False, "message": "请先配置青龙面板"})
                return
            success, msg = sync_to_qinglong(config, url)
            self.send_json({"success": success, "message": msg})
        
        elif path == "/api/qinglong/sync_all":
            # 同步所有到青龙
            config = load_config()
            if not config.get("url"):
                self.send_json({"success": False, "message": "请先配置青龙面板"})
                return
            urls = load_urls()
            success_count = 0
            for url in urls:
                s, _ = sync_to_qinglong(config, url)
                if s:
                    success_count += 1
            self.send_json({"success": True, "synced": success_count, "total": len(urls)})
        
        else:
            self.send_response(404)
            self.end_headers()

# HTML 页面
INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>顺丰速运 - 账号管理面板</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    min-height: 100vh;
    padding: 20px;
}
.container {
    max-width: 1200px;
    margin: 0 auto;
}
.header {
    text-align: center;
    color: white;
    padding: 30px 0;
}
.header h1 {
    font-size: 32px;
    margin-bottom: 10px;
}
.header p { opacity: 0.9; }
.tabs {
    display: flex;
    gap: 10px;
    margin-bottom: 20px;
    flex-wrap: wrap;
}
.tab {
    padding: 12px 24px;
    background: rgba(255,255,255,0.2);
    color: white;
    border: none;
    border-radius: 10px;
    cursor: pointer;
    font-size: 15px;
    transition: all 0.3s;
}
.tab:hover { background: rgba(255,255,255,0.3); }
.tab.active {
    background: white;
    color: #667eea;
    font-weight: 600;
}
.card {
    background: white;
    border-radius: 16px;
    padding: 30px;
    box-shadow: 0 10px 40px rgba(0,0,0,0.1);
    margin-bottom: 20px;
}
.card h2 {
    font-size: 22px;
    color: #333;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 10px;
}
.btn {
    padding: 10px 20px;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 500;
    transition: all 0.3s;
}
.btn-primary {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
}
.btn-primary:hover { transform: translateY(-2px); box-shadow: 0 5px 20px rgba(102,126,234,0.4); }
.btn-success { background: #10b981; color: white; }
.btn-success:hover { background: #059669; }
.btn-danger { background: #ef4444; color: white; }
.btn-danger:hover { background: #dc2626; }
.btn-secondary { background: #e5e7eb; color: #374151; }
.btn-secondary:hover { background: #d1d5db; }
.btn-sm { padding: 6px 12px; font-size: 12px; }
.qr-container {
    display: flex;
    gap: 30px;
    flex-wrap: wrap;
    justify-content: center;
}
.qr-item {
    text-align: center;
    padding: 20px;
    border: 2px solid #e5e7eb;
    border-radius: 12px;
    transition: all 0.3s;
}
.qr-item:hover { border-color: #667eea; }
.qr-item img {
    width: 200px;
    height: 200px;
    margin-bottom: 10px;
}
.qr-item .api-name {
    font-size: 12px;
    color: #9ca3af;
    margin-top: 5px;
}
.status-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 500;
}
.status-waiting { background: #fef3c7; color: #d97706; }
.status-success { background: #d1fae5; color: #059669; }
.status-error { background: #fee2e2; color: #dc2626; }
.status-scanned { background: #dbeafe; color: #2563eb; }
textarea {
    width: 100%;
    min-height: 150px;
    padding: 12px;
    border: 2px solid #e5e7eb;
    border-radius: 8px;
    font-family: monospace;
    font-size: 13px;
    resize: vertical;
    transition: border-color 0.3s;
}
textarea:focus { outline: none; border-color: #667eea; }
.url-list { list-style: none; }
.url-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 15px;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    margin-bottom: 10px;
    transition: all 0.3s;
}
.url-item:hover { border-color: #667eea; background: #f9fafb; }
.url-info { flex: 1; }
.url-preview {
    font-family: monospace;
    font-size: 12px;
    color: #374151;
    word-break: break-all;
    margin-bottom: 5px;
}
.url-meta {
    display: flex;
    gap: 15px;
    font-size: 12px;
    color: #6b7280;
}
.url-actions { display: flex; gap: 8px; }
.stars { color: #fbbf24; }
.form-group { margin-bottom: 20px; }
.form-group label {
    display: block;
    margin-bottom: 8px;
    font-weight: 500;
    color: #374151;
}
.form-group input {
    width: 100%;
    padding: 10px 12px;
    border: 2px solid #e5e7eb;
    border-radius: 8px;
    font-size: 14px;
    transition: border-color 0.3s;
}
.form-group input:focus { outline: none; border-color: #667eea; }
.form-row { display: flex; gap: 15px; }
.form-row .form-group { flex: 1; }
.alert {
    padding: 12px 16px;
    border-radius: 8px;
    margin-bottom: 15px;
    font-size: 14px;
}
.alert-info { background: #dbeafe; color: #1e40af; }
.alert-success { background: #d1fae5; color: #065f46; }
.alert-warning { background: #fef3c7; color: #92400e; }
.alert-error { background: #fee2e2; color: #991b1b; }
.stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 15px;
    margin-bottom: 20px;
}
.stat-card {
    padding: 20px;
    background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%);
    border-radius: 12px;
    text-align: center;
}
.stat-card .number {
    font-size: 36px;
    font-weight: bold;
    color: #667eea;
}
.stat-card .label {
    font-size: 13px;
    color: #6b7280;
    margin-top: 5px;
}
.powered {
    text-align: center;
    color: rgba(255,255,255,0.7);
    font-size: 12px;
    padding: 20px;
}
.loading {
    display: inline-block;
    width: 20px;
    height: 20px;
    border: 3px solid #e5e7eb;
    border-top-color: #667eea;
    border-radius: 50%;
    animation: spin 1s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>📦 顺丰速运账号管理面板</h1>
        <p>扫码登录 · 抓包提取 · 青龙同步 · 账号管理</p>
    </div>

    <div class="tabs">
        <button class="tab active" onclick="switchTab('scan')">📱 扫码登录</button>
        <button class="tab" onclick="switchTab('extract')">📋 粘贴提取</button>
        <button class="tab" onclick="switchTab('urls')">📁 账号管理</button>
        <button class="tab" onclick="switchTab('qinglong')">☁️ 青龙配置</button>
    </div>

    <!-- 扫码登录 -->
    <div id="tab-scan" class="card">
        <h2>📱 扫码登录获取 sfsyUrl</h2>
        <div class="alert alert-info">
            使用微信「扫一扫」扫描下方二维码，登录顺丰速运小程序
        </div>
        <div id="scan-area">
            <div style="text-align:center; padding: 40px;">
                <button class="btn btn-primary" onclick="startScan()" style="font-size: 18px; padding: 15px 40px;">
                    🚀 开始扫码登录
                </button>
            </div>
        </div>
    </div>

    <!-- 粘贴提取 -->
    <div id="tab-extract" class="card" style="display:none;">
        <h2>📋 粘贴抓取内容提取</h2>
        <div class="alert alert-info">
            将手机抓包APP（小蓝鸟/HttpCanary等）抓到的内容粘贴到下方，自动提取 sfsyUrl
        </div>
        <textarea id="extract-text" placeholder="粘贴请求URL、请求头、或完整请求内容..."></textarea>
        <div style="margin-top: 15px; display: flex; gap: 10px;">
            <button class="btn btn-primary" onclick="extractUrls()">🔍 提取 sfsyUrl</button>
            <button class="btn btn-secondary" onclick="document.getElementById('extract-text').value=''">清空</button>
        </div>
        <div id="extract-result" style="margin-top: 20px;"></div>
    </div>

    <!-- 账号管理 -->
    <div id="tab-urls" class="card" style="display:none;">
        <h2>📁 账号管理</h2>
        <div class="stats">
            <div class="stat-card">
                <div class="number" id="stat-local">0</div>
                <div class="label">本地账号数</div>
            </div>
            <div class="stat-card">
                <div class="number" id="stat-ql">0</div>
                <div class="label">青龙账号数</div>
            </div>
        </div>
        <div style="margin-bottom: 15px; display: flex; gap: 10px;">
            <button class="btn btn-success" onclick="syncAll()">☁️ 一键同步全部到青龙</button>
            <button class="btn btn-secondary" onclick="loadUrls()">🔄 刷新</button>
        </div>
        <div id="url-list"></div>
    </div>

    <!-- 青龙配置 -->
    <div id="tab-qinglong" class="card" style="display:none;">
        <h2>☁️ 青龙面板配置</h2>
        <div class="alert alert-info">
            配置青龙面板信息后，可以一键同步 sfsyUrl 到青龙
        </div>
        <div class="form-group">
            <label>青龙面板地址</label>
            <input type="text" id="ql-url" placeholder="http://192.168.1.100:5700">
        </div>
        <div class="form-row">
            <div class="form-group">
                <label>Client ID</label>
                <input type="text" id="ql-client-id" placeholder="应用ID">
            </div>
            <div class="form-group">
                <label>Client Secret</label>
                <input type="password" id="ql-client-secret" placeholder="应用密钥">
            </div>
        </div>
        <div style="display: flex; gap: 10px;">
            <button class="btn btn-primary" onclick="saveQLConfig()">💾 保存并测试连接</button>
            <button class="btn btn-secondary" onclick="loadQLConfig()">🔄 加载配置</button>
        </div>
        <div id="ql-status" style="margin-top: 15px;"></div>
    </div>

    <div class="powered">顺丰速运签到工具 · QL-SF-CHECKIN</div>
</div>

<script>
let currentTab = 'scan';
let scanSessionId = null;
let scanPollTimer = null;

function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll('.tab').forEach((t, i) => {
        const names = ['scan', 'extract', 'urls', 'qinglong'];
        t.classList.toggle('active', names[i] === tab);
    });
    document.querySelectorAll('.card').forEach(c => c.style.display = 'none');
    document.getElementById('tab-' + tab).style.display = 'block';
    
    if (tab === 'urls') loadUrls();
    if (tab === 'qinglong') loadQLConfig();
}

async function api(path, method = 'GET', data = null) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (data) opts.body = JSON.stringify(data);
    const res = await fetch(path, opts);
    return res.json();
}

// 扫码登录
async function startScan() {
    const area = document.getElementById('scan-area');
    area.innerHTML = '<div style="text-align:center; padding: 40px;"><div class="loading"></div><p style="margin-top:15px; color:#6b7280;">正在生成二维码...</p></div>';
    
    try {
        const res = await api('/api/scan/start');
        scanSessionId = res.session_id;
        
        if (res.qrcodes && res.qrcodes.length > 0) {
            let html = '<div class="qr-container">';
            res.qrcodes.forEach((qr, i) => {
                html += `<div class="qr-item">
                    <img src="${qr.qr_img}" alt="扫码登录">
                    <div class="status-badge status-waiting" id="qr-status-${i}">等待扫码</div>
                    <div class="api-name">接口 ${i + 1}</div>
                </div>`;
            });
            html += '</div>';
            html += '<div style="text-align:center; margin-top: 20px;">';
            html += '<p style="color:#6b7280;">请使用微信扫一扫，登录顺丰速运小程序</p>';
            html += '<button class="btn btn-secondary btn-sm" style="margin-top:10px;" onclick="startScan()">🔄 刷新二维码</button>';
            html += '</div>';
            area.innerHTML = html;
            
            // 开始轮询
            startPolling();
        } else {
            area.innerHTML = '<div class="alert alert-warning">⚠️ 无法生成二维码，扫码接口可能已变更</div>';
            area.innerHTML += '<div class="alert alert-info">💡 建议使用「粘贴提取」功能，配合手机抓包APP使用</div>';
        }
    } catch (e) {
        area.innerHTML = `<div class="alert alert-error">❌ 出错了: ${e.message}</div>`;
    }
}

function startPolling() {
    if (scanPollTimer) clearInterval(scanPollTimer);
    scanPollTimer = setInterval(pollScan, 2000);
}

async function pollScan() {
    if (!scanSessionId) return;
    
    try {
        const res = await api('/api/scan/poll?session_id=' + scanSessionId);
        
        if (res.status === 'success') {
            clearInterval(scanPollTimer);
            const area = document.getElementById('scan-area');
            let html = '<div style="text-align:center; padding: 20px;">';
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
            const area = document.getElementById('scan-area');
            area.innerHTML = '<div style="text-align:center; padding: 40px;">';
            area.innerHTML += '<div style="font-size: 48px;">⏰</div>';
            area.innerHTML += '<h3 style="color: #d97706; margin: 15px 0;">二维码已过期</h3>';
            area.innerHTML += '<button class="btn btn-primary" onclick="startScan()">🔄 重新生成</button>';
            area.innerHTML += '</div>';
        } else if (res.status === 'scanned') {
            document.querySelectorAll('.qr-item .status-badge').forEach(b => {
                b.textContent = '已扫码，请确认';
                b.className = 'status-badge status-scanned';
            });
        }
    } catch (e) {
        console.error(e);
    }
}

// 提取URL
async function extractUrls() {
    const text = document.getElementById('extract-text').value;
    if (!text.trim()) {
        alert('请先粘贴内容');
        return;
    }
    
    const resultDiv = document.getElementById('extract-result');
    resultDiv.innerHTML = '<div class="loading"></div> 正在分析...';
    
    try {
        const res = await api('/api/extract', 'POST', { text });
        
        if (res.urls && res.urls.length > 0) {
            let html = `<div class="alert alert-success">找到 ${res.count} 个顺丰相关URL</div>`;
            res.urls.forEach((item, i) => {
                const stars = '⭐'.repeat(Math.min(5, Math.floor(item.score / 50) + 1));
                html += `<div class="url-item">
                    <div class="url-info">
                        <div class="url-preview">${item.url}</div>
                        <div class="url-meta">
                            <span class="stars">${stars}</span>
                            <span>质量分: ${item.score}/250</span>
                            <span>${item.length}字符</span>
                            <span>${item.reasons.join(', ')}</span>
                        </div>
                    </div>
                    <div class="url-actions">
                        <button class="btn btn-success btn-sm" onclick="saveUrl('${item.url.replace(/'/g, "\\'")}')">💾 保存</button>
                        <button class="btn btn-primary btn-sm" onclick="syncToQL('${item.url.replace(/'/g, "\\'")}')">☁️ 同步青龙</button>
                    </div>
                </div>`;
            });
            resultDiv.innerHTML = html;
        } else {
            resultDiv.innerHTML = '<div class="alert alert-warning">没有找到有效的顺丰URL，请确认粘贴的内容包含 sf-express.com 域名</div>';
        }
    } catch (e) {
        resultDiv.innerHTML = `<div class="alert alert-error">出错了: ${e.message}</div>`;
    }
}

async function saveUrl(url) {
    try {
        const res = await api('/api/save', 'POST', { url });
        if (res.success) {
            alert(res.is_new ? '保存成功！' : 'URL已存在');
            loadUrls();
        } else {
            alert('保存失败');
        }
    } catch (e) {
        alert('出错: ' + e.message);
    }
}

async function syncToQL(url) {
    try {
        const res = await api('/api/qinglong/sync', 'POST', { url });
        if (res.success) {
            alert('✅ ' + res.message);
            loadUrls();
        } else {
            alert('❌ ' + res.message);
        }
    } catch (e) {
        alert('出错: ' + e.message);
    }
}

// 账号管理
async function loadUrls() {
    try {
        const res = await api('/api/urls');
        const listDiv = document.getElementById('url-list');
        document.getElementById('stat-local').textContent = res.urls.length;
        
        if (res.urls.length === 0) {
            listDiv.innerHTML = '<div class="alert alert-info">暂无保存的账号</div>';
            return;
        }
        
        let html = '';
        res.urls.forEach(item => {
            const stars = '⭐'.repeat(Math.min(5, Math.floor(item.score / 50) + 1));
            html += `<div class="url-item">
                <div class="url-info">
                    <div class="url-preview">${item.url}</div>
                    <div class="url-meta">
                        <span class="stars">${stars}</span>
                        <span>质量分: ${item.score}/250</span>
                        <span>${item.length}字符</span>
                    </div>
                </div>
                <div class="url-actions">
                    <button class="btn btn-primary btn-sm" onclick="syncToQL(\`${item.full_url}\`)">☁️ 同步青龙</button>
                    <button class="btn btn-danger btn-sm" onclick="deleteUrl(${item.index})">🗑️ 删除</button>
                </div>
            </div>`;
        });
        listDiv.innerHTML = html;
    } catch (e) {
        console.error(e);
    }
    
    // 加载青龙状态
    try {
        const ql = await api('/api/qinglong');
        document.getElementById('stat-ql').textContent = ql.ql_urls_count || 0;
    } catch (e) {}
}

async function deleteUrl(index) {
    if (!confirm('确定删除这个账号吗？')) return;
    try {
        await api('/api/delete', 'POST', { index });
        loadUrls();
    } catch (e) {
        alert('出错: ' + e.message);
    }
}

async function syncAll() {
    if (!confirm('确定同步所有账号到青龙？')) return;
    try {
        const res = await api('/api/qinglong/sync_all', 'POST', {});
        if (res.success) {
            alert(`✅ 同步完成！成功 ${res.synced}/${res.total} 个`);
            loadUrls();
        } else {
            alert('❌ ' + res.message);
        }
    } catch (e) {
        alert('出错: ' + e.message);
    }
}

// 青龙配置
async function loadQLConfig() {
    try {
        const res = await api('/api/qinglong');
        document.getElementById('ql-url').value = res.url || '';
        document.getElementById('ql-client-id').value = res.client_id || '';
        if (res.client_secret) {
            document.getElementById('ql-client-secret').placeholder = '已保存（显示为***）';
        }
        
        const statusDiv = document.getElementById('ql-status');
        if (res.connected) {
            statusDiv.innerHTML = '<div class="alert alert-success">✅ 青龙连接正常，当前有 ' + res.ql_urls_count + ' 个 sfsyUrl 账号</div>';
        } else if (res.url) {
            statusDiv.innerHTML = '<div class="alert alert-warning">⚠️ 已配置但连接失败，请检查地址和密钥</div>';
        }
    } catch (e) {}
}

async function saveQLConfig() {
    const url = document.getElementById('ql-url').value;
    const client_id = document.getElementById('ql-client-id').value;
    const client_secret = document.getElementById('ql-client-secret').value;
    
    if (!url || !client_id || !client_secret) {
        alert('请填写完整信息');
        return;
    }
    
    const statusDiv = document.getElementById('ql-status');
    statusDiv.innerHTML = '<div class="loading"></div> 正在测试连接...';
    
    try {
        const res = await api('/api/qinglong/config', 'POST', { url, client_id, client_secret });
        if (res.success) {
            if (res.connected) {
                statusDiv.innerHTML = '<div class="alert alert-success">✅ 配置保存成功，连接正常！</div>';
            } else {
                statusDiv.innerHTML = '<div class="alert alert-warning">⚠️ 配置已保存但连接失败，请检查地址和密钥</div>';
            }
        } else {
            statusDiv.innerHTML = '<div class="alert alert-error">❌ ' + res.message + '</div>';
        }
    } catch (e) {
        statusDiv.innerHTML = `<div class="alert alert-error">❌ 出错: ${e.message}</div>`;
    }
}

// 初始化
loadQLConfig();
</script>
</body>
</html>
"""

def main():
    print()
    print("=" * 60)
    print("  顺丰速运 Web 管理面板")
    print("=" * 60)
    print()
    print(f"  🌐 地址: http://127.0.0.1:{PORT}")
    print(f"  📁 配置: {CONFIG_FILE}")
    print(f"  📋 账号: {SFSY_URL_FILE}")
    print()
    print("  浏览器正在自动打开...")
    print()
    print("  按 Ctrl+C 停止服务")
    print()
    print("-" * 60)
    print()
    
    # 自动打开浏览器
    def open_browser():
        time.sleep(1)
        webbrowser.open(f"http://127.0.0.1:{PORT}")
    
    threading.Thread(target=open_browser, daemon=True).start()
    
    try:
        server = HTTPServer(("0.0.0.0", PORT), WebHandler)
        server.serve_forever()
    except KeyboardInterrupt:
        print()
        print("  👋 服务已停止")
        server.server_close()

if __name__ == "__main__":
    main()
