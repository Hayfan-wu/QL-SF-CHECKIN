# -*- coding: utf-8 -*-
"""
顺丰速运 sfsyUrl 提取 + 青龙同步工具
配合手机抓包APP（小蓝鸟/HttpCanary/黄鸟等）使用

使用方法：
  1. 手机用抓包APP抓到顺丰的请求
  2. 复制URL或请求内容
  3. 运行本脚本，粘贴进去，自动提取 sfsyUrl
  4. 一键同步到青龙面板
"""

import os
import sys
import re
import json
import time
import urllib.parse
import urllib.request

# ========== 配置 ==========
CONFIG_FILE = "qinglong_config.json"
SFSY_URL_FILE = "sfsyUrl.txt"
# ==========================

def print_banner():
    print("=" * 60)
    print("  顺丰速运 sfsyUrl 提取 + 青龙同步工具")
    print("  配合手机抓包APP使用（小蓝鸟/HttpCanary等）")
    print("=" * 60)
    print()

def load_config():
    """加载青龙配置"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_config(config):
    """保存青龙配置"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def test_ql_connection(config):
    """测试青龙连接"""
    url = config.get("url", "").rstrip("/")
    client_id = config.get("client_id", "")
    client_secret = config.get("client_secret", "")
    
    if not all([url, client_id, client_secret]):
        return False, "配置不完整"
    
    try:
        token_url = f"{url}/open/auth/token?client_id={client_id}&client_secret={client_secret}"
        req = urllib.request.Request(token_url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            if data.get("code") == 200:
                return True, data["data"]["token"]
            return False, data.get("message", "未知错误")
    except Exception as e:
        return False, str(e)

def get_ql_token(config):
    """获取青龙token"""
    url = config.get("url", "").rstrip("/")
    client_id = config.get("client_id", "")
    client_secret = config.get("client_secret", "")
    
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
    """获取青龙环境变量"""
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
    """添加青龙环境变量"""
    token = get_ql_token(config)
    if not token:
        return False, "获取token失败"
    
    url = config["url"].rstrip("/")
    try:
        env_url = f"{url}/open/envs"
        body = json.dumps([{"name": name, "value": value, "remarks": remarks}]).encode()
        req = urllib.request.Request(env_url, data=body, headers={
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
    """更新青龙环境变量"""
    token = get_ql_token(config)
    if not token:
        return False, "获取token失败"
    
    url = config["url"].rstrip("/")
    try:
        env_url = f"{url}/open/envs"
        body = json.dumps({"id": env_id, "name": name, "value": value, "remarks": remarks}).encode()
        req = urllib.request.Request(env_url, data=body, headers={
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

def extract_sfsy_urls(text):
    """从文本中提取所有可能的 sfsyUrl"""
    urls = []
    
    # 提取完整URL
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]\'\\]+'
    found_urls = re.findall(url_pattern, text)
    
    for url in found_urls:
        # 清理URL末尾可能多余的字符
        url = url.rstrip('.,;:!?)]}')
        
        # 只保留顺丰相关的
        if any(d in url for d in ["sf-express.com", "sf-mobile.com", "sfintra.com"]):
            score, reasons = evaluate_url(url)
            if score >= 30:  # 有一定相似度的都收集
                urls.append((url, score, reasons))
    
    # 按分数排序
    urls.sort(key=lambda x: x[1], reverse=True)
    return urls

def evaluate_url(url):
    """评估URL质量"""
    score = 0
    reasons = []
    
    keywords = {
        "memberId": 30, "member_id": 30, "userid": 30, "userId": 30,
        "token": 30, "access_token": 30, "accessToken": 30,
        "sign": 20, "signType": 20, "signIn": 15,
        "appid": 15, "appId": 15, "app_id": 15,
        "channel": 10, "platform": 10,
        "point": 10, "integral": 10,
        "code": 5, "coupon": 5,
        "sysCode": 10,
    }
    
    url_lower = url.lower()
    for kw, points in keywords.items():
        if kw.lower() in url_lower:
            score += points
            reasons.append(kw)
    
    # 长度加分
    if len(url) > 300:
        score += 25
    elif len(url) > 200:
        score += 20
    elif len(url) > 100:
        score += 10
    
    # 域名加分
    if "sf-express.com" in url:
        score += 15
    
    # 扣分项
    if "login" in url_lower and "token" not in url_lower:
        score = max(0, score - 10)
    
    return min(score, 250), reasons

def extract_cookies(text):
    """从文本中提取cookie"""
    cookies = {}
    
    # 匹配 Cookie: xxx=yyy; 格式
    cookie_patterns = [
        r'Cookie[：:]\s*(.+)',
        r'cookie[：:]\s*(.+)',
        r'Set-Cookie[：:]\s*(.+)',
    ]
    
    for pattern in cookie_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            parts = match.split(';')
            for part in parts:
                part = part.strip()
                if '=' in part:
                    k, v = part.split('=', 1)
                    k = k.strip()
                    v = v.strip()
                    if k and v and k not in cookies:
                        cookies[k] = v
    
    return cookies

def build_sfsy_url(url, cookies):
    """从URL和cookie构建完整的sfsyUrl"""
    # 如果URL本身已经有足够信息，直接返回
    score, _ = evaluate_url(url)
    if score >= 150:
        return url
    
    # 否则尝试把cookie信息拼进去
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    
    # 添加重要cookie到参数
    important_cookies = ["memberId", "member_id", "token", "accessToken", "access_token", "userid", "userId"]
    for ck in important_cookies:
        if ck in cookies and ck not in params:
            params[ck] = [cookies[ck]]
    
    # 重建URL
    new_query = urllib.parse.urlencode(params, doseq=True)
    new_url = parsed._replace(query=new_query).geturl()
    
    return new_url

def save_to_file(url):
    """保存到本地文件"""
    # 检查是否已存在
    existing = []
    if os.path.exists(SFSY_URL_FILE):
        with open(SFSY_URL_FILE, "r", encoding="utf-8") as f:
            existing = [line.strip() for line in f if line.strip()]
    
    if url in existing:
        return False  # 已存在
    
    with open(SFSY_URL_FILE, "a", encoding="utf-8") as f:
        f.write(url + "\n")
    return True

def sync_to_qinglong(config, url):
    """同步到青龙"""
    env_name = "sfsyUrl"
    
    # 获取现有环境变量
    envs = get_ql_env(config, env_name)
    
    if envs and len(envs) > 0:
        # 已有环境变量，追加
        existing_value = envs[0].get("value", "")
        env_id = envs[0].get("id")
        remarks = envs[0].get("remarks", "")
        
        # 检查是否已存在
        urls = [u.strip() for u in existing_value.split("\n") if u.strip()]
        if url in urls:
            return True, "URL已存在，无需重复添加"
        
        # 追加
        new_value = existing_value + "\n" + url if existing_value else url
        success, msg = update_ql_env(config, env_id, env_name, new_value, remarks)
        return success, msg + f"（共{len(urls)+1}个账号）"
    else:
        # 新建环境变量
        success, msg = add_ql_env(config, env_name, url, "顺丰速运签到")
        return success, msg + "（第1个账号）"

def config_qinglong():
    """配置青龙面板"""
    print()
    print("【 配置青龙面板 】")
    print()
    print("  请在青龙面板 → 系统设置 → 应用设置 中创建应用")
    print("  权限选择：环境变量（全部勾选）")
    print()
    
    config = load_config()
    
    url = input(f"  青龙地址 (当前: {config.get('url', '未设置')}): ").strip()
    if not url:
        url = config.get("url", "")
    url = url.rstrip("/")
    
    client_id = input(f"  Client ID (当前: {config.get('client_id', '未设置')}): ").strip()
    if not client_id:
        client_id = config.get("client_id", "")
    
    client_secret = input(f"  Client Secret (当前: {config.get('client_secret', '未设置')}): ").strip()
    if not client_secret:
        client_secret = config.get("client_secret", "")
    
    new_config = {
        "url": url,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    
    print()
    print("  正在测试连接...")
    success, msg = test_ql_connection(new_config)
    
    if success:
        print(f"  ✅ 连接成功！")
        save_config(new_config)
        print(f"  ✅ 配置已保存")
    else:
        print(f"  ❌ 连接失败: {msg}")
        print(f"  仍然保存配置吗？(y/n): ", end="")
        choice = input().strip().lower()
        if choice == "y":
            save_config(new_config)
            print(f"  ✅ 配置已保存")
    
    input("\n按回车返回...")

def manual_input():
    """手动输入URL"""
    print()
    print("【 粘贴抓取内容 】")
    print()
    print("  请将手机抓包APP中抓到的内容粘贴到下方")
    print("  可以是URL、请求头、或完整请求内容")
    print("  粘贴完成后，按回车两次结束")
    print()
    
    lines = []
    empty_count = 0
    print("  --- 开始粘贴 ---")
    while True:
        try:
            line = input("  ")
            if not line.strip():
                empty_count += 1
                if empty_count >= 1:
                    break
            else:
                empty_count = 0
                lines.append(line)
        except EOFError:
            break
    
    text = "\n".join(lines)
    
    if not text.strip():
        print()
        print("  ❌ 没有输入内容")
        input("\n按回车返回...")
        return
    
    print()
    print("  正在分析...")
    print()
    
    # 提取URL
    urls = extract_sfsy_urls(text)
    
    if not urls:
        print("  ❌ 没有找到顺丰相关的URL")
        print()
        print("  请确认：")
        print("  1. 抓到的是顺丰速运小程序的请求")
        print("  2. URL包含 sf-express.com 域名")
        input("\n按回车返回...")
        return
    
    print(f"  找到 {len(urls)} 个顺丰相关URL：")
    print()
    
    for i, (url, score, reasons) in enumerate(urls[:10], 1):
        stars = "⭐" * min(5, score // 50 + 1)
        reason_str = ", ".join(reasons[:5])
        print(f"  {i}. {stars} ({score}分) {reason_str}")
        if len(url) > 100:
            print(f"     {url[:100]}...")
        else:
            print(f"     {url}")
        print()
    
    # 选最好的
    best_url = urls[0][0]
    best_score = urls[0][1]
    
    print(f"  🎯 推荐使用第1个（质量最高）")
    print()
    
    choice = input(f"  使用第几个？(默认1): ").strip()
    try:
        idx = int(choice) - 1 if choice else 0
        if 0 <= idx < len(urls):
            best_url = urls[idx][0]
            best_score = urls[idx][1]
    except:
        pass
    
    # 提取cookie增强
    cookies = extract_cookies(text)
    if cookies:
        print()
        print(f"  🍪 还提取到 {len(cookies)} 个Cookie，要合并到URL中吗？(y/n): ", end="")
        merge = input().strip().lower()
        if merge == "y":
            best_url = build_sfsy_url(best_url, cookies)
            print(f"  ✅ 已合并")
    
    print()
    print("=" * 60)
    print()
    print("  ✅ 提取完成！")
    print()
    print(f"  sfsyUrl ({len(best_url)}字符):")
    print()
    
    # 分段显示
    if len(best_url) > 200:
        print(f"  {best_url[:200]}")
        print(f"  {best_url[200:400]}...")
    else:
        print(f"  {best_url}")
    
    print()
    
    # 保存到本地
    is_new = save_to_file(best_url)
    if is_new:
        print(f"  💾 已保存到 {SFSY_URL_FILE}")
    else:
        print(f"  💾 URL已存在于 {SFSY_URL_FILE}")
    
    # 同步到青龙
    config = load_config()
    if config.get("url") and config.get("client_id"):
        print()
        print(f"  ☁️  检测到青龙配置，要同步到青龙吗？(y/n): ", end="")
        sync = input().strip().lower()
        if sync == "y":
            print()
            print("  正在同步...")
            success, msg = sync_to_qinglong(config, best_url)
            if success:
                print(f"  ✅ 同步成功！{msg}")
            else:
                print(f"  ❌ 同步失败: {msg}")
    else:
        print()
        print(f"  💡 提示：配置青龙面板后可以一键同步")
        print(f"     在主菜单选择「3 - 配置青龙面板」")
    
    input("\n按回车返回...")

def view_saved():
    """查看已保存的URL"""
    print()
    print("【 已保存的 sfsyUrl 】")
    print()
    
    if not os.path.exists(SFSY_URL_FILE):
        print("  暂无保存的URL")
        input("\n按回车返回...")
        return
    
    with open(SFSY_URL_FILE, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]
    
    if not urls:
        print("  暂无保存的URL")
    else:
        print(f"  共 {len(urls)} 个账号：")
        print()
        for i, url in enumerate(urls, 1):
            score, reasons = evaluate_url(url)
            stars = "⭐" * min(5, score // 50 + 1)
            preview = url[:80] + "..." if len(url) > 80 else url
            print(f"  {i}. {stars} ({score}分) {preview}")
    
    # 查看青龙上的
    config = load_config()
    if config.get("url") and config.get("client_id"):
        print()
        print("  正在获取青龙上的环境变量...")
        envs = get_ql_env(config, "sfsyUrl")
        if envs:
            env = envs[0]
            value = env.get("value", "")
            count = len([u for u in value.split("\n") if u.strip()])
            print(f"  ☁️  青龙上: {count} 个账号")
    
    input("\n按回车返回...")

def main():
    print_banner()
    
    while True:
        print()
        print("【 主菜单 】")
        print()
        print("  1 - 粘贴抓取内容提取 sfsyUrl ⭐")
        print("  2 - 查看已保存的URL")
        print("  3 - 配置青龙面板")
        print("  0 - 退出")
        print()
        
        choice = input("  请选择: ").strip()
        
        if choice == "1":
            manual_input()
        elif choice == "2":
            view_saved()
        elif choice == "3":
            config_qinglong()
        elif choice == "0" or choice == "":
            print()
            print("  👋 再见！")
            break
        else:
            print()
            print("  ❌ 无效选择")
            time.sleep(1)

if __name__ == "__main__":
    main()
