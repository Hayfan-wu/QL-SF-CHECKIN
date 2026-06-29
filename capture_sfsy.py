#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
顺丰速运 sfsyUrl 一键抓取工具
功能: 启动本地HTTP代理，自动捕获顺丰速运小程序请求，提取完整登录URL
使用方式:
    1. 运行本脚本
    2. 手机WiFi设置代理为本机IP:8888
    3. 打开顺丰速运小程序，进入积分页面
    4. 脚本自动捕获并显示 sfsyUrl
"""

import os
import sys
import json
import socket
import threading
import re
from urllib.parse import urlparse, parse_qs, unquote
from datetime import datetime

# 尝试导入 mitmproxy
try:
    from mitmproxy import http, ctx
    from mitmproxy.tools.main import mitmdump
    HAS_MITMPROXY = True
except ImportError:
    HAS_MITMPROXY = False

# 尝试导入 requests（用于简单HTTP服务器）
try:
    import requests
except ImportError:
    pass


# ============== 配置 ==============
class Config:
    # 代理端口
    PROXY_PORT = 8888
    # 顺丰域名关键词
    SF_DOMAINS = [
        'mcs-mimp-web.sf-express.com',
        'sf-express.com',
    ]
    # 目标URL关键词（包含这些的URL会被捕获）
    TARGET_KEYWORDS = [
        'shareGiftReceiveRedirect',
        'shareRedirect',
        'memberId',
        '_login_user_id_',
        '_login_mobile_',
        'integral',
        'point',
    ]
    # 输出文件
    OUTPUT_FILE = 'sfsyUrl.txt'
    # 历史记录文件
    HISTORY_FILE = 'sfsy_history.json'


# ============== 颜色输出 ==============
class Color:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

    @staticmethod
    def color(text, color):
        return f'{color}{text}{Color.RESET}'


# ============== URL 捕获器 ==============
class UrlCapturer:
    """URL捕获器 - 管理捕获的URL"""

    def __init__(self):
        self.captured_urls = []
        self.lock = threading.Lock()
        self.found = False
        self.best_url = None

    def add_url(self, url, source='request'):
        """添加捕获的URL"""
        with self.lock:
            # 检查是否重复
            for item in self.captured_urls:
                if item['url'] == url:
                    return

            url_info = {
                'url': url,
                'source': source,
                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'score': self._score_url(url),
            }
            self.captured_urls.append(url_info)

            # 按分数排序
            self.captured_urls.sort(key=lambda x: x['score'], reverse=True)

            # 检查是否是高质量URL
            if self._is_high_quality(url):
                if not self.found or url_info['score'] > (self.best_url['score'] if self.best_url else 0):
                    self.found = True
                    self.best_url = url_info
                    self._print_found(url_info)

    def _score_url(self, url):
        """评估URL的质量分数"""
        score = 0
        url_lower = url.lower()

        # 域名加分
        if 'mcs-mimp-web.sf-express.com' in url_lower:
            score += 50

        # 关键路径加分
        if 'shareGiftReceiveRedirect' in url_lower:
            score += 100
        if 'shareRedirect' in url_lower:
            score += 90
        if '/point/' in url_lower or '/integral' in url_lower:
            score += 40

        # 参数加分
        if 'memberId=' in url_lower or 'memberid=' in url_lower:
            score += 80
        if '_login_user_id_' in url_lower:
            score += 85
        if '_login_mobile_' in url_lower:
            score += 85
        if 'sessionId=' in url_lower or 'sessionid=' in url_lower:
            score += 70
        if 'token=' in url_lower:
            score += 60

        return score

    def _is_high_quality(self, url):
        """判断是否是高质量URL（可以直接使用的）"""
        url_lower = url.lower()
        # 包含登录相关cookie的URL
        if '_login_user_id_=' in url_lower and '_login_mobile_' in url_lower:
            return True
        # 分享链接
        if 'shareGiftReceiveRedirect' in url_lower and ('memberId=' in url_lower or 'menId=' in url_lower):
            return True
        # 包含完整session的URL
        if 'sessionId=' in url_lower and '_login_user_id_' in url_lower:
            return True
        return False

    def _print_found(self, url_info):
        """打印找到的结果"""
        print()
        print(Color.color('=' * 70, Color.YELLOW))
        print(Color.color('🎉 找到可用的 sfsyUrl！', Color.GREEN + Color.BOLD))
        print(Color.color('=' * 70, Color.YELLOW))
        print(f'来源: {url_info["source"]}')
        print(f'时间: {url_info["time"]}')
        print(f'质量分: {url_info["score"]}')
        print()
        print(Color.color('URL内容:', Color.CYAN))
        print(url_info['url'])
        print(Color.color('=' * 70, Color.YELLOW))
        print()

        # 保存到文件
        self._save_to_file(url_info['url'])

    def _save_to_file(self, url):
        """保存到文件"""
        try:
            with open(Config.OUTPUT_FILE, 'w', encoding='utf-8') as f:
                f.write(url)
            print(Color.color(f'✅ 已保存到 {Config.OUTPUT_FILE}', Color.GREEN))
        except Exception as e:
            print(Color.color(f'⚠️ 保存文件失败: {e}', Color.YELLOW))

    def save_history(self):
        """保存历史记录"""
        try:
            history = []
            if os.path.exists(Config.HISTORY_FILE):
                with open(Config.HISTORY_FILE, 'r', encoding='utf-8') as f:
                    history = json.load(f)

            for item in self.captured_urls:
                history.append(item)

            # 只保留最近50条
            history = history[-50:]

            with open(Config.HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_best_url(self):
        """获取最佳URL"""
        if self.best_url:
            return self.best_url['url']
        if self.captured_urls:
            return self.captured_urls[0]['url']
        return None

    def print_summary(self):
        """打印捕获摘要"""
        print()
        print(Color.color('=' * 70, Color.CYAN))
        print(Color.color('📊 捕获结果统计', Color.BOLD))
        print(Color.color('=' * 70, Color.CYAN))
        print(f'共捕获 URL 数量: {len(self.captured_urls)}')
        print(f'找到可用 URL: {"是" if self.found else "否"}')
        print()

        if self.captured_urls:
            print(Color.color('Top 5 URL (按质量排序):', Color.YELLOW))
            for i, item in enumerate(self.captured_urls[:5]):
                display_url = item['url'][:80] + ('...' if len(item['url']) > 80 else '')
                marker = '⭐' if item == self.best_url else '  '
                print(f'{marker} {i+1}. [{item["score"]}分] {display_url}')
            print()

        if self.best_url:
            print(Color.color('✅ 推荐使用的 URL:', Color.GREEN + Color.BOLD))
            print(self.best_url['url'])
            print()
            print(Color.color(f'已保存到: {Config.OUTPUT_FILE}', Color.GREEN))

        print(Color.color('=' * 70, Color.CYAN))


# ============== mitmproxy 插件 ==============
capturer = UrlCapturer()


def response(flow: http.HTTPFlow):
    """mitmproxy 响应钩子"""
    url = flow.request.pretty_url

    # 检查是否是顺丰域名
    is_sf = any(domain in url for domain in Config.SF_DOMAINS)
    if not is_sf:
        return

    # 检查URL关键词
    has_keyword = any(kw.lower() in url.lower() for kw in Config.TARGET_KEYWORDS)

    # 检查响应cookie
    set_cookies = flow.response.headers.get_all('set-cookie')
    cookie_str = '; '.join(set_cookies) if set_cookies else ''
    has_login_cookie = '_login_user_id_' in cookie_str and '_login_mobile_' in cookie_str

    if has_keyword or has_login_cookie:
        capturer.add_url(url, 'response')

        # 如果是登录相关的响应，构造cookie格式的URL
        if has_login_cookie:
            cookie_url = _build_cookie_url(cookie_str)
            if cookie_url:
                capturer.add_url(cookie_url, 'cookie')


def request(flow: http.HTTPFlow):
    """mitmproxy 请求钩子"""
    url = flow.request.pretty_url

    # 检查是否是顺丰域名
    is_sf = any(domain in url for domain in Config.SF_DOMAINS)
    if not is_sf:
        return

    # 检查URL关键词
    has_keyword = any(kw.lower() in url.lower() for kw in Config.TARGET_KEYWORDS)
    if has_keyword:
        capturer.add_url(url, 'request')

    # 检查请求cookie
    cookie_header = flow.request.headers.get('cookie', '')
    if '_login_user_id_' in cookie_header and '_login_mobile_' in cookie_header:
        cookie_url = _build_cookie_url(cookie_header)
        if cookie_url:
            capturer.add_url(cookie_url, 'request_cookie')


def _build_cookie_url(cookie_str):
    """从cookie字符串构造可用的URL格式"""
    try:
        cookies = {}
        for item in cookie_str.split(';'):
            item = item.strip()
            if '=' in item:
                k, v = item.split('=', 1)
                cookies[k.strip()] = v.strip()

        if '_login_user_id_' in cookies and '_login_mobile_' in cookies:
            # 构造cookie格式的sfsyUrl
            parts = []
            for k in ['sessionId', '_login_user_id_', '_login_mobile_', 'session_id']:
                if k in cookies:
                    parts.append(f'{k}={cookies[k]}')
            if parts:
                return ';'.join(parts)
    except Exception:
        pass
    return None


# ============== 获取本机IP ==============
def get_local_ip():
    """获取本机IP地址"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return '127.0.0.1'


# ============== 打印横幅 ==============
def print_banner():
    """打印启动横幅"""
    banner = r"""
   _____  ______  _______  _______  __   __  __    __
  / ____||  ____||__   __||__   __| \ \ / / |  \  /  |
 | (___  | |__      | |      | |     \ V /  |   \/   |
  \___ \ |  __|     | |      | |      > <   | |\  /| |
  ____) || |____    | |      | |     / . \  | | \/ | |
 |_____/ |______|   |_|      |_|    /_/ \_\ |_|    |_|

   顺丰速运 sfsyUrl 一键抓取工具 v1.0.0
"""
    print(Color.color(banner, Color.CYAN))


def print_guide():
    """打印使用指南"""
    local_ip = get_local_ip()
    port = Config.PROXY_PORT

    print()
    print(Color.color('=' * 70, Color.YELLOW))
    print(Color.color('📱 使用步骤', Color.BOLD))
    print(Color.color('=' * 70, Color.YELLOW))
    print()
    print(f'  {Color.color("1.", Color.GREEN)} 确保手机和电脑在同一WiFi网络下')
    print(f'  {Color.color("2.", Color.GREEN)} 手机WiFi设置代理:')
    print(f'     主机名: {Color.color(local_ip, Color.CYAN + Color.BOLD)}')
    print(f'     端口:   {Color.color(str(port), Color.CYAN + Color.BOLD)}')
    print(f'  {Color.color("3.", Color.GREEN)} 手机浏览器访问 http://mitm.it 安装证书')
    print(f'     (mitmproxy 首次使用需要安装证书)')
    print(f'  {Color.color("4.", Color.GREEN)} 打开微信 → 顺丰速运+小程序')
    print(f'  {Color.color("5.", Color.GREEN)} 进入「我的」→「积分」→ 任务列表')
    print(f'  {Color.color("6.", Color.GREEN)} 脚本会自动捕获并显示 sfsyUrl')
    print()
    print(Color.color('💡 提示: 找到URL后按 Ctrl+C 退出', Color.YELLOW))
    print(Color.color('=' * 70, Color.YELLOW))
    print()
    print(Color.color('🔍 正在监听顺丰速运请求...', Color.BLUE + Color.BOLD))
    print()


# ============== 简单HTTP代理（备用方案） ==============
def run_simple_proxy():
    """简单HTTP代理（不依赖mitmproxy）"""
    import http.server
    import socketserver
    import urllib.request

    class ProxyHandler(http.server.BaseHTTPRequestHandler):
        def do_CONNECT(self):
            """HTTPS 连接（仅透传，不解密）"""
            try:
                address = self.path.split(':')
                host = address[0]
                port = int(address[1]) if len(address) > 1 else 443

                # 检查是否是顺丰域名
                is_sf = any(domain in host for domain in Config.SF_DOMAINS)
                if is_sf:
                    print(f'🔗 HTTPS 连接: {self.path}')

                # 建立远程连接
                remote_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                remote_sock.connect((host, port))

                self.send_response(200, 'Connection Established')
                self.end_headers()

                # 双向转发
                self._tunnel(self.connection, remote_sock)
            except Exception as e:
                print(f'CONNECT 错误: {e}')
                try:
                    self.send_error(502)
                except Exception:
                    pass

        def do_GET(self):
            self._handle_http('GET')

        def do_POST(self):
            self._handle_http('POST')

        def _handle_http(self, method):
            try:
                url = self.path
                is_sf = any(domain in url for domain in Config.SF_DOMAINS)

                if is_sf:
                    has_keyword = any(kw.lower() in url.lower() for kw in Config.TARGET_KEYWORDS)
                    if has_keyword:
                        capturer.add_url(url, method.lower())

                # 转发请求
                req = urllib.request.Request(url, method=method)
                for header, value in self.headers.items():
                    if header.lower() not in ['host', 'connection']:
                        req.add_header(header, value)

                content_length = int(self.headers.get('Content-Length', 0))
                if content_length > 0:
                    body = self.rfile.read(content_length)
                    req.data = body

                with urllib.request.urlopen(req, timeout=30) as resp:
                    self.send_response(resp.status)
                    for header, value in resp.headers.items():
                        if header.lower() not in ['transfer-encoding', 'connection']:
                            self.send_header(header, value)
                    self.end_headers()

                    # 检查响应cookie
                    set_cookies = resp.headers.get_all('Set-Cookie', [])
                    cookie_str = '; '.join(set_cookies)
                    if '_login_user_id_' in cookie_str and '_login_mobile_' in cookie_str:
                        cookie_url = _build_cookie_url(cookie_str)
                        if cookie_url:
                            capturer.add_url(cookie_url, 'response_cookie')

                    # 转发响应体
                    while True:
                        chunk = resp.read(8192)
                        if not chunk:
                            break
                        self.wfile.write(chunk)

            except Exception as e:
                print(f'HTTP 代理错误: {e}')
                try:
                    self.send_error(502)
                except Exception:
                    pass

        def _tunnel(self, client, remote):
            """隧道转发"""
            import select

            sockets = [client, remote]
            while True:
                readable, _, _ = select.select(sockets, [], [], 1)
                for sock in readable:
                    try:
                        data = sock.recv(8192)
                        if not data:
                            return
                        if sock is client:
                            remote.sendall(data)
                        else:
                            client.sendall(data)
                    except Exception:
                        return

        def log_message(self, format, *args):
            # 静默日志
            pass

    local_ip = get_local_ip()
    print(f'🌐 简单代理模式 (不支持HTTPS解密)')
    print(f'   代理地址: {local_ip}:{Config.PROXY_PORT}')
    print(f'   注意: 此模式只能捕获HTTP请求，HTTPS仅显示连接信息')
    print(f'   推荐安装 mitmproxy 以支持HTTPS解密')
    print()

    with socketserver.ThreadingTCPServer(('', Config.PROXY_PORT), ProxyHandler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print('\n\n🛑 用户中断')
            capturer.print_summary()
            capturer.save_history()


# ============== mitmproxy 模式 ==============
def run_mitmproxy():
    """使用 mitmproxy 运行"""
    print_guide()

    try:
        # 启动 mitmdump
        sys.argv = [
            'mitmdump',
            '-p', str(Config.PROXY_PORT),
            '-s', __file__,  # 加载本文件作为插件
            '--quiet',
        ]
        mitmdump()
    except KeyboardInterrupt:
        print('\n\n🛑 用户中断')
        capturer.print_summary()
        capturer.save_history()
    except Exception as e:
        print(Color.color(f'❌ mitmproxy 启动失败: {e}', Color.RED))
        print(Color.color('正在尝试简单代理模式...', Color.YELLOW))
        run_simple_proxy()


# ============== 检查并安装依赖 ==============
def check_dependencies():
    """检查依赖"""
    print('🔍 检查依赖...')

    if HAS_MITMPROXY:
        print(Color.color('✅ mitmproxy 已安装', Color.GREEN))
        return True
    else:
        print(Color.color('⚠️ mitmproxy 未安装', Color.YELLOW))
        print('   推荐安装以支持HTTPS解密捕获:')
        print('   pip install mitmproxy')
        print()

        choice = input('是否安装 mitmproxy? (y/n): ').strip().lower()
        if choice == 'y':
            print('正在安装 mitmproxy...')
            os.system(f'{sys.executable} -m pip install mitmproxy')
            print('安装完成，请重新运行脚本')
            sys.exit(0)
        else:
            print('将使用简单代理模式（仅支持HTTP）')
            return False


# ============== 主函数 ==============
def main():
    print_banner()

    # 检查是否作为 mitmproxy 插件加载
    if len(sys.argv) > 1 and sys.argv[1] in ['--mitmproxy-plugin', '-s']:
        # mitmproxy 插件模式，不执行主逻辑
        return

    # 检查依赖
    has_mitm = check_dependencies()

    print()

    if has_mitm:
        run_mitmproxy()
    else:
        run_simple_proxy()


if __name__ == '__main__':
    main()
