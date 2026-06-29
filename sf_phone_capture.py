# -*- coding: utf-8 -*-
"""
顺丰速运 sfsyUrl 手机抓包工具（极简版）
使用方法：
  1. 运行本脚本
  2. 手机连同一个WiFi，设置代理（脚本显示的IP:8899）
  3. 手机浏览器访问 http://mitm.it 安装证书
  4. 打开顺丰速运小程序，进入积分页面
  5. 自动捕获到 sfsyUrl，复制即可用
"""

import os
import sys
import json
import time
import threading
import urllib.parse
import urllib.request
import subprocess
from pathlib import Path

# ========== 配置 ==========
PROXY_PORT = 8899
CAPTURE_FILE = "captured_url.txt"
HISTORY_FILE = "sfsy_history.json"
# ==========================

def print_banner():
    print("=" * 55)
    print("  顺丰速运 sfsyUrl 手机抓包工具")
    print("=" * 55)
    print()

def get_local_ip():
    """获取本机局域网IP"""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        try:
            return socket.gethostbyname(socket.gethostname())
        except:
            return "127.0.0.1"

def check_mitmproxy():
    """检查并安装 mitmproxy"""
    try:
        from mitmproxy import version
        print(f"[✓] mitmproxy 已安装 (v{version.VERSION})")
        return True
    except ImportError:
        print("[!] mitmproxy 未安装，正在安装...")
        print("    请稍候，大约1-2分钟...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "mitmproxy",
                 "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            print("[✓] mitmproxy 安装成功")
            return True
        except Exception as e:
            print(f"[✗] 安装失败: {e}")
            return False

def evaluate_url(url):
    """评估URL质量，返回分数和说明"""
    score = 0
    reasons = []
    
    # 关键词加分
    keywords = {
        "memberId": 30, "member_id": 30, "userid": 30,
        "token": 30, "access_token": 30, "accessToken": 30,
        "sign": 20, "signType": 20,
        "appid": 15, "appId": 15,
        "channel": 10, "platform": 10,
        "point": 10, "integral": 10, "signin": 10,
        "code": 5, "coupon": 5,
    }
    
    url_lower = url.lower()
    for kw, points in keywords.items():
        if kw.lower() in url_lower:
            score += points
            reasons.append(kw)
    
    # 长度加分（信息越多越可能完整）
    if len(url) > 200:
        score += 20
    elif len(url) > 100:
        score += 10
    
    # 域名加分
    if "sf-express.com" in url:
        score += 15
    if "mcs-mimp" in url or "mcs.+" in url:
        score += 10
    
    # 扣分项
    if "mitm.it" in url:
        score = 0
    if "login" in url_lower and "token" not in url_lower:
        score = max(0, score - 10)
    
    return min(score, 250), reasons

def is_sf_request(url):
    """判断是否是顺丰相关请求"""
    sf_domains = [
        "sf-express.com",
        "sf-mobile.com",
        "sfintra.com",
        "sf-link.com",
    ]
    return any(domain in url for domain in sf_domains)

def find_best_url(captured_urls):
    """从捕获的URL中找出最好的"""
    best_url = None
    best_score = 0
    best_reasons = []
    
    for url in captured_urls:
        if not is_sf_request(url):
            continue
        score, reasons = evaluate_url(url)
        if score > best_score:
            best_score = score
            best_url = url
            best_reasons = reasons
    
    return best_url, best_score, best_reasons

def save_history(url, score):
    """保存历史记录"""
    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except:
            history = []
    
    # 去重
    for item in history:
        if item.get("url") == url:
            return
    
    history.insert(0, {
        "url": url,
        "score": score,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    
    # 最多保留50条
    history = history[:50]
    
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

# mitmproxy 拦截脚本
MITM_SCRIPT = r'''
import re
import json
import os
import sys
import urllib.parse

captured = []
best_url = None
best_score = 0
stop_event = None

def set_stop_event(evt):
    global stop_event
    stop_event = evt

def evaluate_url(url):
    score = 0
    keywords = {
        "memberId": 30, "member_id": 30, "userid": 30,
        "token": 30, "access_token": 30, "accessToken": 30,
        "sign": 20, "signType": 20,
        "appid": 15, "appId": 15,
        "channel": 10, "platform": 10,
        "point": 10, "integral": 10, "signin": 10,
    }
    url_lower = url.lower()
    for kw, points in keywords.items():
        if kw.lower() in url_lower:
            score += points
    if len(url) > 200:
        score += 20
    elif len(url) > 100:
        score += 10
    return min(score, 250)

def is_sf_request(url):
    domains = ["sf-express.com", "sf-mobile.com", "sfintra.com"]
    return any(d in url for d in domains)

def request(flow):
    global best_url, best_score
    
    url = flow.request.url
    if not is_sf_request(url):
        return
    
    score = evaluate_url(url)
    
    if score > best_score:
        best_score = score
        best_url = url
        captured.append(url)
        
        # 分数够高就保存并通知
        if score >= 100:
            save_path = os.path.join(os.getcwd(), "captured_url.txt")
            try:
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(url)
            except:
                pass
            
            print()
            print("=" * 60)
            print("  🎉 捕获到高质量 URL！")
            print(f"  分数: {score}/250")
            print("=" * 60)
            print(f"  {url[:120]}..." if len(url) > 120 else f"  {url}")
            print("=" * 60)
            print()
            print("  已保存到 captured_url.txt")
            print("  按 Ctrl+C 停止抓包")
            print()
'''

def run_proxy():
    """启动代理抓包"""
    print("[*] 正在启动代理服务...")
    print()
    
    ip = get_local_ip()
    print(f"  📱 手机 WiFi 代理设置：")
    print(f"     服务器：{ip}")
    print(f"     端口：  {PROXY_PORT}")
    print()
    print(f"  🔐 安装证书：")
    print(f"     手机浏览器访问：http://mitm.it")
    print(f"     下载并安装证书（选择 iPhone/Android）")
    print()
    print(f"  🎯 抓包步骤：")
    print(f"     1. 手机设置好代理和证书")
    print(f"     2. 打开顺丰速运小程序")
    print(f"     3. 进入「积分」或「我的」页面")
    print(f"     4. 等待自动捕获...")
    print()
    print(f"  ⏹️  停止：按 Ctrl+C")
    print()
    print("-" * 55)
    print()
    
    # 写入临时脚本文件
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_mitm_script.py")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(MITM_SCRIPT)
    
    # 清空之前的捕获文件
    if os.path.exists(CAPTURE_FILE):
        os.remove(CAPTURE_FILE)
    
    try:
        # 启动 mitmdump
        cmd = [
            sys.executable, "-m", "mitmproxy.tools.main.mitmdump",
            "--listen-port", str(PROXY_PORT),
            "-s", script_path,
            "--set", "block_global=false",
            "--set", "ssl_insecure=true",
        ]
        
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        # 读取输出
        start_time = time.time()
        found = False
        
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            
            # 显示启动信息
            if "listening" in line.lower() or "Proxy server" in line:
                print(f"  ✅ 代理已启动，等待手机连接...")
                print()
            
            # 显示捕获到的URL
            if "sf-express.com" in line and "http" in line:
                # 提取URL
                import re
                urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', line)
                for url in urls:
                    if is_sf_request(url):
                        score, reasons = evaluate_url(url)
                        if score >= 50:
                            print(f"  [+] 捕获 ({score}分): {url[:80]}...")
            
            # 检测到高质量URL
            if "捕获到高质量" in line:
                found = True
                print(line)
            
            # 超时提示
            elapsed = time.time() - start_time
            if elapsed > 60 and not found:
                if int(elapsed) % 30 == 0:
                    print(f"  ⏳ 已等待 {int(elapsed)}秒，还没捕获到...")
                    print(f"     请确认手机代理已设置并打开小程序积分页面")
        
        proc.wait()
        
    except KeyboardInterrupt:
        print()
        print("  ⏹️  正在停止代理...")
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except:
            try:
                proc.kill()
            except:
                pass
    
    finally:
        # 清理临时脚本
        if os.path.exists(script_path):
            try:
                os.remove(script_path)
            except:
                pass
    
    # 读取捕获结果
    result_url = None
    if os.path.exists(CAPTURE_FILE):
        with open(CAPTURE_FILE, "r", encoding="utf-8") as f:
            result_url = f.read().strip()
    
    return result_url

def main():
    print_banner()
    
    if not check_mitmproxy():
        print()
        print("[✗] 无法安装 mitmproxy，请手动安装：")
        print("    pip install mitmproxy")
        input("\n按回车退出...")
        return
    
    print()
    print("-" * 55)
    print()
    
    url = run_proxy()
    
    print()
    print("=" * 55)
    
    if url:
        print()
        print("  ✅ 捕获成功！")
        print()
        print(f"  URL（已复制到 captured_url.txt）：")
        print()
        # 分段显示
        if len(url) > 150:
            print(f"  {url[:150]}")
            print(f"  {url[150:300] if len(url) > 300 else url[150:]}")
            if len(url) > 300:
                print(f"  ...（共{len(url)}字符）")
        else:
            print(f"  {url}")
        print()
        
        # 保存历史
        score, _ = evaluate_url(url)
        save_history(url, score)
        
        # 保存到主文件
        main_file = "sfsyUrl.txt"
        print(f"  保存到 {main_file} 了吗？ ", end="")
        try:
            with open(main_file, "a", encoding="utf-8") as f:
                f.write(url + "\n")
            print("✅ 已追加")
        except Exception as e:
            print(f"❌ 失败: {e}")
        
    else:
        print()
        print("  ❌ 没有捕获到有效的 sfsyUrl")
        print()
        print("  可能的原因：")
        print("  1. 手机代理没设置对")
        print("  2. 证书没安装好")
        print("  3. 没打开顺丰小程序积分页面")
        print()
    
    print()
    input("按回车退出...")

if __name__ == "__main__":
    main()
