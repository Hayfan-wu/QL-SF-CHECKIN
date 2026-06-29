# -*- coding: utf-8 -*-
"""
顺丰速运 Web 管理面板
功能：扫码登录 / 粘贴提取 / 青龙配置 / 账号管理

使用方法：
  python sf_web.py
  浏览器自动打开 http://127.0.0.1:8765
"""

import os
import sys
import re
import json
import time
import hashlib
import threading
import webbrowser
import urllib.parse
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

# ========== 配置 ==========
PORT = 8765
CONFIG_FILE = "qinglong_config.json"
SFSY_URL_FILE = "sfsyUrl.txt"
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
# ==========================

# 全局状态
scan_sessions = {}


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
                urls.append({"url": url, "score": score, "reasons": reasons, "length": len(url)})
    urls.sort(key=lambda x: x["score"], reverse=True)
    return urls


# ===== 青龙相关 =====
def get_ql_token(config):
    url = config.get("url", "").rstrip("/")
    client_id = config.get("client_id", "")
    client_secret = config.get("client_secret", "")
    if not all([url, client_id, client_secret]):
        return None
    try:
        token_url = url + "/open/auth/token?client_id=" + client_id + "&client_secret=" + client_secret
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
        env_url = url + "/open/envs?searchValue=" + urllib.parse.quote(name)
        req = urllib.request.Request(env_url, headers={"Authorization": "Bearer " + token})
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
        req = urllib.request.Request(url + "/open/envs", data=body, headers={
            "Authorization": "Bearer " + token,
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
        req = urllib.request.Request(url + "/open/envs", data=body, headers={
            "Authorization": "Bearer " + token,
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
        return success, msg + "（共" + str(len(urls) + 1) + "个账号）"
    else:
        success, msg = add_ql_env(config, env_name, url, "顺丰速运签到")
        return success, msg + "（第1个账号）"


# ===== 顺丰扫码登录 =====
SF_BASE = "https://mcs-mimp-web.sf-express.com"
SF_TOKEN = "wwesldfs29aniversaryvdld29"
SF_SYS_CODE = "MCS-MIMP-CORE"

# 小程序端接口 (MINI_PROGRAM)
MINI_QR_APIS = [
    ("/mcs-mimp/commonPost/~memberNonactivity~memberQrCodeLoginService~generateQrCode", "POST", "qrCode", "qrId", "MINI_PROGRAM"),
    ("/mcs-mimp/commonRoutePost/member/qrcode/generate", "POST", "qrCodeUrl", "qrId", "MINI_PROGRAM"),
    ("/mcs-mimp/commonRoutePost/member/login/qrcode/create", "POST", "qrCode", "id", "MINI_PROGRAM"),
    ("/mcs-mimp/point/qrcode/generate", "POST", "qrCode", "qrToken", "MINI_PROGRAM"),
    ("/mcs-mimp/commonPost/~memberNonactivity~memberLoginService~generateLoginQrCode", "POST", "qrCodeImage", "qrCodeId", "MINI_PROGRAM"),
    ("/mcs-mimp/commonPost/~memberNonactivity~integralTaskSignPlusService~generateSignQrCode", "POST", "qrCode", "qrId", "MINI_PROGRAM"),
]

MINI_POLL_APIS = [
    "/mcs-mimp/commonPost/~memberNonactivity~memberQrCodeLoginService~queryQrCodeStatus",
    "/mcs-mimp/commonRoutePost/member/qrcode/status",
    "/mcs-mimp/commonRoutePost/member/login/qrcode/status",
    "/mcs-mimp/point/qrcode/status",
    "/mcs-mimp/commonPost/~memberNonactivity~memberLoginService~checkLoginQrCode",
    "/mcs-mimp/commonPost/~memberNonactivity~integralTaskSignPlusService~checkSignQrCode",
]

# APP端接口 (SFAPP + 签名)
APP_QR_APIS = [
    ("/mcs-mimp/commonPost/~memberNonactivity~memberQrCodeLoginService~generateQrCode", "POST", "qrCode", "qrId", "SFAPP"),
    ("/mcs-mimp/commonRoutePost/member/qrcode/generate", "POST", "qrCodeUrl", "qrId", "SFAPP"),
    ("/mcs-mimp/commonRoutePost/member/login/qrcode/create", "POST", "qrCode", "id", "SFAPP"),
    ("/mcs-mimp/commonPost/~memberNonactivity~memberLoginService~generateLoginQrCode", "POST", "qrCodeImage", "qrCodeId", "SFAPP"),
    ("/mcs-mimp/commonPost/~memberNonactivity~integralTaskSignPlusService~generateSignQrCode", "POST", "qrCode", "qrId", "SFAPP"),
    ("/mcs-mimp/commonPost/~memberActivity~memberAppLoginService~generateQrCode", "POST", "qrCode", "qrId", "SFAPP"),
    ("/mcs-mimp/commonRoutePost/app/login/qrcode/create", "POST", "qrCode", "token", "SFAPP"),
]

APP_POLL_APIS = [
    "/mcs-mimp/commonPost/~memberNonactivity~memberQrCodeLoginService~queryQrCodeStatus",
    "/mcs-mimp/commonRoutePost/member/qrcode/status",
    "/mcs-mimp/commonRoutePost/member/login/qrcode/status",
    "/mcs-mimp/commonPost/~memberNonactivity~memberLoginService~checkLoginQrCode",
    "/mcs-mimp/commonPost/~memberNonactivity~integralTaskSignPlusService~checkSignQrCode",
    "/mcs-mimp/commonPost/~memberActivity~memberAppLoginService~queryQrCodeStatus",
    "/mcs-mimp/commonRoutePost/app/login/qrcode/status",
]


def generate_sign():
    """生成API签名"""
    timestamp = str(int(round(time.time() * 1000)))
    data = "token=" + SF_TOKEN + "&timestamp=" + timestamp + "&sysCode=" + SF_SYS_CODE
    signature = hashlib.md5(data.encode()).hexdigest()
    return {
        "sysCode": SF_SYS_CODE,
        "timestamp": timestamp,
        "signature": signature,
    }


def sf_request(path, data=None, method="POST", platform="MINI_PROGRAM", need_sign=True):
    """发送顺丰API请求"""
    url = SF_BASE + path
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.40(0x18002829) NetType/WIFI Language/zh_CN",
        "Referer": "https://mcs-mimp-web.sf-express.com/",
        "Origin": "https://mcs-mimp-web.sf-express.com",
        "platform": platform,
    }
    # APP端需要签名
    if platform == "SFAPP" and need_sign:
        sign_data = generate_sign()
        headers.update(sign_data)
    else:
        headers["sysCode"] = platform
    try:
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            return True, result
    except Exception as e:
        return False, str(e)


def find_field(data, *field_names):
    if not isinstance(data, dict):
        return None
    for field in field_names:
        for key in data:
            if key.lower() == field.lower():
                return data[key]
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


def generate_qrcode(platform_type="app"):
    results = []
    # 根据类型选择接口
    if platform_type == "app":
        all_apis = APP_QR_APIS
        all_poll = APP_POLL_APIS
    elif platform_type == "mini":
        all_apis = MINI_QR_APIS
        all_poll = MINI_POLL_APIS
    else:
        # 全部尝试，APP优先
        all_apis = APP_QR_APIS + MINI_QR_APIS
        all_poll = APP_POLL_APIS + MINI_POLL_APIS
    
    for i, (path, method, qr_field, id_field, platform) in enumerate(all_apis):
        try:
            data = {"channelType": platform, "platform": platform} if method == "POST" else None
            need_sign = (platform == "SFAPP")
            success, result = sf_request(path, data, method, platform, need_sign)
            if not success:
                continue
            qr_code = find_field(result, qr_field, "qrCodeUrl", "qrcodeUrl", "qrCodeImage", "qrcode", "qr_code", "qrCodeBase64")
            qr_id = find_field(result, id_field, "qrId", "qrCodeId", "id", "token", "qrToken", "qr_token", "scene")
            if qr_code:
                if qr_code.startswith("http"):
                    qr_img = qr_code
                elif qr_code.startswith("data:image"):
                    qr_img = qr_code
                else:
                    qr_img = "data:image/png;base64," + qr_code
                poll_path = all_poll[i] if i < len(all_poll) else all_poll[0]
                results.append({
                    "api_index": i,
                    "api_path": path,
                    "platform": platform,
                    "qr_img": qr_img,
                    "qr_id": qr_id or "",
                    "poll_path": poll_path,
                })
                # 有结果了就先返回，不用等全部
                if len(results) >= 3:
                    break
        except:
            continue
    return results


def poll_qrcode_status(qr_id, poll_path, platform="SFAPP"):
    try:
        data = {"qrId": qr_id, "qrCodeId": qr_id, "id": qr_id, "token": qr_id, "platform": platform}
        need_sign = (platform == "SFAPP")
        success, result = sf_request(poll_path, data, "POST", platform, need_sign)
        if not success:
            return "error", None, str(result)
        status = find_field(result, "status", "qrStatus", "codeStatus", "state")
        token = find_field(result, "token", "accessToken", "sessionToken", "sessionId", "memberToken")
        member_id = find_field(result, "memberId", "userId", "member_id", "user_id", "memberCode")
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
    token = login_data.get("token", "")
    member_id = login_data.get("memberId", "")
    if not member_id or not token:
        return None
    params = {
        "memberId": member_id,
        "token": token,
        "channel": "MINI_PROGRAM",
        "platform": "MINI_PROGRAM",
        "sysCode": "MINI_PROGRAM",
    }
    base_url = "https://mcs-mimp-web.sf-express.com/member/point/index"
    query = urllib.parse.urlencode(params)
    return base_url + "?" + query


# ===== HTTP 处理 =====
class WebHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def serve_file(self, filepath, content_type):
        if os.path.exists(filepath):
            with open(filepath, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return True
        return False

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # 静态文件
        if path == "/" or path == "/index.html":
            self.serve_file(os.path.join(STATIC_DIR, "index.html"), "text/html; charset=utf-8")
            return
        if path == "/app.js":
            self.serve_file(os.path.join(STATIC_DIR, "app.js"), "application/javascript; charset=utf-8")
            return

        # API
        if path == "/api/status":
            config = load_config()
            urls = load_urls()
            ql_ok = bool(get_ql_token(config))
            self.send_json({
                "urls_count": len(urls),
                "ql_configured": bool(config.get("url") and config.get("client_id")),
                "ql_connected": ql_ok,
            })
            return

        if path == "/api/urls":
            urls = load_urls()
            result = []
            for i, url in enumerate(urls):
                score, reasons = evaluate_url(url)
                preview = url[:120] + "..." if len(url) > 120 else url
                result.append({
                    "index": i,
                    "url": preview,
                    "full_url": url,
                    "score": score,
                    "reasons": reasons[:5],
                    "length": len(url),
                })
            self.send_json({"urls": result})
            return

        if path == "/api/qinglong":
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
            return

        if path == "/api/scan/start":
            params = urllib.parse.parse_qs(parsed.query)
            platform = params.get("platform", ["app"])[0]  # app 或 mini
            results = generate_qrcode(platform)
            session_id = str(int(time.time() * 1000))
            scan_sessions[session_id] = {
                "results": results,
                "status": "pending",
                "created_at": time.time(),
                "platform": platform,
            }
            self.send_json({
                "session_id": session_id,
                "qrcodes": [{"api_index": r["api_index"], "qr_img": r["qr_img"], "platform": r["platform"]} for r in results[:3]],
                "count": len(results),
            })
            return

        if path == "/api/scan/poll":
            params = urllib.parse.parse_qs(parsed.query)
            session_id = params.get("session_id", [""])[0]
            session = scan_sessions.get(session_id)
            if not session:
                self.send_json({"status": "error", "message": "会话不存在"})
                return

            all_waiting = True
            for result in session["results"]:
                qr_id = result.get("qr_id", "")
                poll_path = result.get("poll_path", "")
                if not qr_id:
                    continue
                platform = result.get("platform", "SFAPP")
                status, data, error = poll_qrcode_status(qr_id, poll_path, platform)
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

            if time.time() - session["created_at"] > 180:
                session["status"] = "expired"
                self.send_json({"status": "expired"})
                return

            self.send_json({"status": "waiting" if all_waiting else "scanned"})
            return

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
            text = data.get("text", "")
            urls = extract_sfsy_urls(text)
            self.send_json({"urls": urls[:10], "count": len(urls)})
            return

        if path == "/api/save":
            url = data.get("url", "")
            if url:
                is_new = save_url(url)
                self.send_json({"success": True, "is_new": is_new})
            else:
                self.send_json({"success": False, "message": "URL为空"})
            return

        if path == "/api/delete":
            index = data.get("index", -1)
            success = delete_url(index)
            self.send_json({"success": success})
            return

        if path == "/api/qinglong/config":
            config = {
                "url": data.get("url", "").rstrip("/"),
                "client_id": data.get("client_id", ""),
                "client_secret": data.get("client_secret", ""),
            }
            token = get_ql_token(config)
            if token:
                save_config(config)
                self.send_json({"success": True, "connected": True})
            else:
                if data.get("force_save"):
                    save_config(config)
                    self.send_json({"success": True, "connected": False})
                else:
                    self.send_json({"success": False, "message": "连接失败，请检查地址和密钥"})
            return

        if path == "/api/qinglong/sync":
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
            return

        if path == "/api/qinglong/sync_all":
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
            return

        self.send_response(404)
        self.end_headers()


def main():
    print("")
    print("=" * 60)
    print("  顺丰速运 Web 管理面板")
    print("=" * 60)
    print("")
    print("  🌐 地址: http://127.0.0.1:" + str(PORT))
    print("  📁 配置: " + CONFIG_FILE)
    print("  📋 账号: " + SFSY_URL_FILE)
    print("")
    print("  浏览器正在自动打开...")
    print("")
    print("  按 Ctrl+C 停止服务")
    print("")
    print("-" * 60)
    print("")

    def open_browser():
        time.sleep(1)
        webbrowser.open("http://127.0.0.1:" + str(PORT))

    threading.Thread(target=open_browser, daemon=True).start()

    try:
        server = HTTPServer(("0.0.0.0", PORT), WebHandler)
        server.serve_forever()
    except KeyboardInterrupt:
        print("")
        print("  👋 服务已停止")
        server.server_close()


if __name__ == "__main__":
    main()
