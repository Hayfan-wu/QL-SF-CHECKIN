#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
顺丰速运 sfsyUrl 一键获取 + 青龙同步工具
极简版：自动装依赖 → 自动开代理 → 打开小程序 → 自动抓 → 自动同步青龙
用法: python sf_login.py
"""

import os, sys, json, time, threading, subprocess, socket, re
from datetime import datetime

# ===== 颜色 =====
class C:
    R='\033[91m';G='\033[92m';Y='\033[93m';B='\033[94m'
    M='\033[95m';C='\033[96m';BO='\033[1m';N='\033[0m'
    @staticmethod
    def c(t,c): return f'{c}{t}{C.N}'

# ===== 配置 =====
CONFIG_FILE = 'sf_config.json'
PROXY_PORT = 8899
SF_HOSTS = ['mcs-mimp-web.sf-express.com', 'sf-express.com']
SF_KWS = ['memberId','_login_user_id_','_login_mobile_','sessionId',
          'shareGiftReceiveRedirect','shareRedirect','integral','/point/']

# ===== 全局状态 =====
found_url = None
found_score = 0
stop_flag = threading.Event()

# ============================================================
# 配置读写
# ============================================================
def load_cfg():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE,'r',encoding='utf-8') as f:
                return json.load(f)
        except: pass
    return {}

def save_cfg(cfg):
    with open(CONFIG_FILE,'w',encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

# ============================================================
# 依赖安装
# ============================================================
def check_install_mitmproxy():
    """检查并自动安装 mitmproxy"""
    try:
        import mitmproxy
        return True
    except ImportError:
        pass
    
    print(C.c('📦 正在安装 mitmproxy (首次使用需要)...', C.B))
    print(C.c('   请稍候，大约需要1-2分钟...', C.Y))
    print()
    
    try:
        r = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', 'mitmproxy', '-i',
             'https://pypi.tuna.tsinghua.edu.cn/simple'],
            capture_output=True, text=True, timeout=180
        )
        if r.returncode == 0:
            print(C.c('✅ mitmproxy 安装成功！', C.G))
            return True
        else:
            print(C.c(f'❌ 安装失败: {r.stderr[:200]}', C.R))
            return False
    except Exception as e:
        print(C.c(f'❌ 安装出错: {e}', C.R))
        return False

# ============================================================
# Windows 系统代理
# ============================================================
def win_proxy(enable, port=PROXY_PORT):
    if sys.platform != 'win32':
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r'Software\Microsoft\Windows\CurrentVersion\Internet Settings',
            0, winreg.KEY_ALL_ACCESS)
        if enable:
            winreg.SetValueEx(key, 'ProxyEnable', 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, 'ProxyServer', 0, winreg.REG_SZ, f'127.0.0.1:{port}')
            winreg.SetValueEx(key, 'ProxyOverride', 0, winreg.REG_SZ,
                'localhost;127.0.0.1;*.local;<local>')
        else:
            winreg.SetValueEx(key, 'ProxyEnable', 0, winreg.REG_DWORD, 0)
        winreg.CloseKey(key)
        return True
    except:
        return False

# ============================================================
# URL 质量评分
# ============================================================
def score_url(url):
    s, u = 0, url.lower()
    if 'mcs-mimp-web.sf-express.com' in u: s += 50
    if 'sharegiftreceiveredirect' in u: s += 100
    if 'shareredirect' in u: s += 90
    if 'memberid=' in u: s += 80
    if '_login_user_id_' in u: s += 85
    if '_login_mobile_' in u: s += 85
    if 'sessionid=' in u: s += 70
    if 'token=' in u: s += 60
    return s

def is_quality(url):
    return score_url(url) >= 130

# ============================================================
# mitmproxy 插件回调
# ============================================================
def response(flow):
    global found_url, found_score
    if stop_flag.is_set():
        return
    
    url = flow.request.pretty_url
    host = flow.request.host
    
    if not any(h in host for h in SF_HOSTS):
        return
    
    # 检查 URL
    if any(kw.lower() in url.lower() for kw in SF_KWS):
        sc = score_url(url)
        if sc > found_score:
            found_score = sc
            if is_quality(url):
                found_url = url
                stop_flag.set()
                _print_found(url, sc, 'URL')
    
    # 检查 Set-Cookie
    scookies = flow.response.headers.get_all('set-cookie')
    if scookies:
        cookie_str = ';'.join(c.split(';')[0].strip() for c in scookies)
        if '_login_user_id_' in cookie_str or 'sessionId' in cookie_str:
            # 构造可用的 cookie 格式 URL
            parts = []
            for c in scookies:
                kv = c.split(';')[0].strip()
                if kv and ('sessionId' in kv or '_login_' in kv or 'memberId' in kv):
                    parts.append(kv)
            if parts:
                result = ';'.join(parts)
                sc = score_url(result)
                if sc > found_score:
                    found_score = sc
                    if sc >= 130:
                        found_url = result
                        stop_flag.set()
                        _print_found(result, sc, 'Cookie')

def request(flow):
    global found_url, found_score
    if stop_flag.is_set():
        return
    
    url = flow.request.pretty_url
    host = flow.request.host
    
    if not any(h in host for h in SF_HOSTS):
        return
    
    # 检查请求 cookie
    ck = flow.request.headers.get('cookie', '')
    if ck and '_login_user_id_' in ck:
        # 提取关键 cookie
        parts = []
        for item in ck.split(';'):
            item = item.strip()
            if any(k in item for k in ['sessionId','_login_user_id_','_login_mobile_','memberId']):
                parts.append(item)
        if len(parts) >= 2:
            result = ';'.join(parts)
            sc = score_url(result)
            if sc > found_score:
                found_score = sc
                if sc >= 130:
                    found_url = result
                    stop_flag.set()
                    _print_found(result, sc, '请求Cookie')
    
    # 检查 URL
    if any(kw.lower() in url.lower() for kw in SF_KWS):
        sc = score_url(url)
        if sc > found_score and is_quality(url):
            found_url = url
            found_score = sc
            stop_flag.set()
            _print_found(url, sc, '请求URL')

def _print_found(url, score, source):
    """打印找到的结果（在 mitmproxy 线程中）"""
    print()
    print(C.c('=' * 60, C.Y))
    print(C.c(f'🎉 找到 sfsyUrl！(质量分: {score})', C.G + C.BO))
    print(C.c('=' * 60, C.Y))
    print(f'来源: {source}')
    if len(url) > 120:
        print(f'URL: {url[:120]}...')
    else:
        print(f'URL: {url}')
    print(C.c('=' * 60, C.Y))
    print()

# ============================================================
# 青龙面板 API
# ============================================================
class QLApi:
    def __init__(self, url, cid, cs):
        self.base = url.rstrip('/')
        self.cid = cid
        self.cs = cs
        self.token = ''
    
    def login(self):
        try:
            import requests
            r = requests.get(f'{self.base}/open/auth/token',
                params={'client_id':self.cid,'client_secret':self.cs}, timeout=10)
            d = r.json()
            if d.get('code') == 200:
                self.token = d['data']['token']
                return True
        except: pass
        return False
    
    def get_envs(self, key):
        try:
            import requests
            r = requests.get(f'{self.base}/open/envs',
                headers={'Authorization':f'Bearer {self.token}'},
                params={'searchValue':key}, timeout=10)
            d = r.json()
            if d.get('code') == 200:
                return d.get('data', [])
        except: pass
        return []
    
    def add_env(self, name, value, remarks=''):
        try:
            import requests
            r = requests.post(f'{self.base}/open/envs',
                headers={'Authorization':f'Bearer {self.token}'},
                json=[{"name":name,"value":value,"remarks":remarks}], timeout=10)
            return r.json().get('code') == 200
        except: return False
    
    def update_env(self, eid, name, value, remarks=''):
        try:
            import requests
            r = requests.put(f'{self.base}/open/envs',
                headers={'Authorization':f'Bearer {self.token}'},
                json={"id":eid,"name":name,"value":value,"remarks":remarks}, timeout=10)
            return r.json().get('code') == 200
        except: return False
    
    def sync(self, url, remarks='顺丰速运'):
        if not self.login():
            print(C.c('  ❌ 青龙登录失败', C.R))
            return False
        
        envs = self.get_envs('sfsyUrl')
        if envs:
            env = envs[0]
            old = env.get('value','')
            urls = [u.strip() for u in old.split('&') if u.strip()]
            if url not in urls:
                urls.append(url)
            new_val = '&'.join(urls)
            if self.update_env(env['_id'], 'sfsyUrl', new_val, remarks):
                print(C.c(f'  ✅ 已同步到青龙 (共{len(urls)}个账号)', C.G))
                return True
        else:
            if self.add_env('sfsyUrl', url, remarks):
                print(C.c(f'  ✅ 已同步到青龙', C.G))
                return True
        
        print(C.c('  ❌ 同步失败', C.R))
        return False

# ============================================================
# 主界面
# ============================================================
def banner():
    print()
    print(C.c('╔══════════════════════════════════════╗', C.C))
    print(C.c('║  顺丰 sfsyUrl 一键获取 + 青龙同步    ║', C.C + C.BO))
    print(C.c('║  打开小程序 → 自动抓取 → 一键同步    ║', C.C))
    print(C.c('╚══════════════════════════════════════╝', C.C))
    print()

def menu(cfg):
    print(C.c('【 主菜单 】', C.BO))
    print()
    print(C.c('  1', C.G) + ' - 一键抓取 sfsyUrl (打开微信小程序)')
    print(C.c('  2', C.G) + ' - 配置青龙面板 (自动同步)')
    print(C.c('  3', C.G) + ' - 手动输入URL同步到青龙')
    print(C.c('  4', C.G) + ' - 查看已保存的URL')
    print(C.c('  0', C.Y) + ' - 退出')
    print()
    if cfg.get('ql_url'):
        print(C.c(f'  ✅ 青龙: {cfg["ql_url"]}', C.G))
    else:
        print(C.c(f'  ⚠️  未配置青龙 (同步功能不可用)', C.Y))
    print()

# ============================================================
# 功能1: 一键抓取
# ============================================================
def do_capture(cfg):
    global found_url, found_score
    found_url = None
    found_score = 0
    stop_flag.clear()
    
    print()
    print(C.c('=' * 60, C.Y))
    print(C.c('🚀 一键抓取 sfsyUrl', C.BO))
    print(C.c('=' * 60, C.Y))
    print()
    
    if sys.platform != 'win32':
        print(C.c('⚠️  非 Windows 系统，无法自动设置代理', C.Y))
        print('   请手动设置 HTTP 代理: 127.0.0.1:' + str(PROXY_PORT))
        print('   或使用手机代理方式 (capture_sfsy.py)')
        print()
        input('按回车继续...')
    
    # 检查依赖
    if not check_install_mitmproxy():
        input('按回车返回...')
        return
    
    print()
    print(C.c('📱 操作步骤:', C.BO))
    print()
    print('  1. 确保电脑微信已登录')
    print('  2. 脚本自动设置系统代理')
    print('  3. 打开微信 → 顺丰速运+小程序')
    print('  4. 进入「我的」→「积分」页面')
    print('  5. 等待几秒，自动捕获成功')
    print()
    print(C.c('💡 首次使用需要安装 mitmproxy 证书，脚本会自动提示', C.Y))
    print()
    
    input(C.c('按回车键开始...', C.C))
    
    # 设置代理
    if sys.platform == 'win32':
        print()
        print(C.c('🔧 设置系统代理...', C.B), end=' ')
        if win_proxy(True):
            print(C.c('✅', C.G))
        else:
            print(C.c('❌ 失败，请手动设置', C.R))
    
    # 启动 mitmproxy
    print(C.c('🌐 启动代理服务器...', C.B))
    print()
    
    # 用子进程方式运行 mitmdump
    # 为了方便，我们直接用 mitmproxy 的 Python API
    proxy_thread = threading.Thread(target=_run_mitmproxy, daemon=True)
    proxy_thread.start()
    
    time.sleep(2)
    
    print(C.c('✅ 代理已启动！', C.G))
    print(C.c('💡 请在微信中打开「顺丰速运+」小程序，进入积分页面', C.C + C.BO))
    print(C.c('   正在监听... 找到后自动停止', C.C))
    print()
    
    # 检查证书
    _check_cert()
    
    # 等待结果
    start = time.time()
    try:
        while not stop_flag.is_set():
            time.sleep(1)
            if time.time() - start > 180:  # 3分钟超时
                print()
                print(C.c('⏰ 3分钟超时，未找到高质量URL', C.Y))
                break
    except KeyboardInterrupt:
        pass
    
    stop_flag.set()
    time.sleep(1)
    
    # 关闭代理
    if sys.platform == 'win32':
        print()
        print(C.c('🔧 关闭系统代理...', C.B), end=' ')
        if win_proxy(False):
            print(C.c('✅', C.G))
        else:
            print(C.c('❌', C.R))
    
    # 显示结果
    print()
    if found_url:
        print(C.c('🎉 抓取成功！', C.G + C.BO))
        print()
        print(C.c('sfsyUrl:', C.C + C.BO))
        print(found_url)
        print()
        
        # 保存
        with open('sfsyUrl.txt', 'w', encoding='utf-8') as f:
            f.write(found_url)
        print(C.c('💾 已保存到 sfsyUrl.txt', C.G))
        print()
        
        # 询问是否同步
        if cfg.get('ql_url') and cfg.get('ql_cid') and cfg.get('ql_cs'):
            choice = input(C.c('是否同步到青龙面板? (y/n): ', C.C)).strip().lower()
            if choice == 'y':
                print()
                ql = QLApi(cfg['ql_url'], cfg['ql_cid'], cfg['ql_cs'])
                ql.sync(found_url)
    else:
        print(C.c('❌ 未抓取到可用的 sfsyUrl', C.R))
        print()
        print(C.c('💡 可能原因:', C.Y))
        print('   1. 小程序未完全加载，多刷新几次试试')
        print('   2. mitmproxy 证书未正确安装')
        print('   3. 微信小程序使用了证书绑定')
        print()
        print(C.c('   如果电脑端不行，建议用手机端抓包:', C.C))
        print('   运行 capture_sfsy.py 按提示操作')
    
    print()
    input('按回车返回...')


def _run_mitmproxy():
    """在子线程运行 mitmproxy"""
    try:
        from mitmproxy.tools.main import mitmdump
        
        # 我们需要把当前文件作为插件加载
        # mitmdump 会调用本文件中的 request/response 函数
        sys.argv = [
            'mitmdump',
            '-p', str(PROXY_PORT),
            '-s', __file__,
            '--quiet',
            '--set', 'block_global=false',
        ]
        mitmdump()
    except Exception as e:
        if not stop_flag.is_set():
            print(C.c(f'代理异常: {e}', C.R))


def _check_cert():
    """检查 mitmproxy 证书是否已安装"""
    if sys.platform != 'win32':
        return
    
    # 检查证书文件是否存在
    home = os.path.expanduser('~')
    cert_path = os.path.join(home, '.mitmproxy', 'mitmproxy-ca-cert.cer')
    
    if not os.path.exists(cert_path):
        print(C.c('⚠️  未检测到 mitmproxy 证书', C.Y))
        print('   请按以下步骤安装证书（只需安装一次）:')
        print()
        print('   1. 等待代理启动后，用浏览器访问 http://mitm.it')
        print('   2. 下载 Windows 证书')
        print('   3. 双击安装 → 安装到「受信任的根证书颁发机构」')
        print('   4. 安装完成后刷新小程序页面')
        print()
        print(C.c('   或者运行以下命令自动安装证书（需要管理员权限）', C.C))
        print()
    else:
        # 简单提示
        pass

# ============================================================
# 功能2: 配置青龙
# ============================================================
def do_config_ql(cfg):
    print()
    print(C.c('=' * 60, C.Y))
    print(C.c('⚙️  配置青龙面板', C.BO))
    print(C.c('=' * 60, C.Y))
    print()
    print(C.c('📝 青龙面板 OpenAPI 配置获取方式:', C.BO))
    print()
    print('   1. 打开青龙面板 → 系统设置 → 应用设置')
    print('   2. 点击「添加应用」')
    print('   3. 权限勾选「环境变量」')
    print('   4. 保存后得到 Client ID 和 Client Secret')
    print()
    
    if cfg.get('ql_url'):
        print(f'当前地址: {cfg["ql_url"]}')
        url = input('青龙地址 (回车保留): ').strip() or cfg['ql_url']
    else:
        url = input('青龙地址 (如 http://192.168.1.100:5700): ').strip()
    
    if cfg.get('ql_cid'):
        print(f'当前 Client ID: {cfg["ql_cid"]}')
        cid = input('Client ID (回车保留): ').strip() or cfg['ql_cid']
    else:
        cid = input('Client ID: ').strip()
    
    if cfg.get('ql_cs'):
        cs = input('Client Secret (回车保留当前): ').strip() or cfg['ql_cs']
    else:
        cs = input('Client Secret: ').strip()
    
    if not all([url, cid, cs]):
        print(C.c('❌ 配置不完整', C.R))
        input('按回车返回...')
        return
    
    print()
    print(C.c('🔍 测试连接...', C.B))
    ql = QLApi(url, cid, cs)
    if ql.login():
        print(C.c('✅ 连接成功！', C.G))
        cfg['ql_url'] = url
        cfg['ql_cid'] = cid
        cfg['ql_cs'] = cs
        save_cfg(cfg)
        print(C.c('💾 配置已保存', C.G))
    else:
        print(C.c('❌ 连接失败，请检查地址和密钥', C.R))
    
    print()
    input('按回车返回...')

# ============================================================
# 功能3: 手动同步
# ============================================================
def do_manual(cfg):
    print()
    print(C.c('=' * 60, C.Y))
    print(C.c('✏️  手动输入 URL 同步到青龙', C.BO))
    print(C.c('=' * 60, C.Y))
    print()
    
    if not all([cfg.get('ql_url'), cfg.get('ql_cid'), cfg.get('ql_cs')]):
        print(C.c('❌ 请先配置青龙面板 (选项2)', C.R))
        input('按回车返回...')
        return
    
    url = input('请输入 sfsyUrl: ').strip()
    if not url:
        print(C.c('❌ URL 不能为空', C.R))
        input('按回车返回...')
        return
    
    print()
    ql = QLApi(cfg['ql_url'], cfg['ql_cid'], cfg['ql_cs'])
    ql.sync(url)
    
    # 追加保存
    with open('sfsyUrl.txt', 'a', encoding='utf-8') as f:
        f.write('\n' + url)
    
    print()
    input('按回车返回...')

# ============================================================
# 功能4: 查看
# ============================================================
def do_view(cfg):
    print()
    print(C.c('=' * 60, C.Y))
    print(C.c('📋 已保存的 sfsyUrl', C.BO))
    print(C.c('=' * 60, C.Y))
    print()
    
    # 本地
    if os.path.exists('sfsyUrl.txt'):
        try:
            with open('sfsyUrl.txt','r',encoding='utf-8') as f:
                c = f.read().strip()
            if c:
                urls = [u.strip() for u in c.replace('&','\n').split('\n') if u.strip()]
                print(C.c(f'📁 本地文件: {len(urls)} 个', C.B))
                for i,u in enumerate(urls):
                    d = u[:60] + ('...' if len(u)>60 else '')
                    print(f'   {i+1}. {d}')
                print()
        except: pass
    
    # 青龙
    if all([cfg.get('ql_url'), cfg.get('ql_cid'), cfg.get('ql_cs')]):
        print(C.c(f'☁️  青龙面板: {cfg["ql_url"]}', C.B))
        ql = QLApi(cfg['ql_url'], cfg['ql_cid'], cfg['ql_cs'])
        if ql.login():
            envs = ql.get_envs('sfsyUrl')
            if envs:
                for env in envs:
                    val = env.get('value','')
                    urls = [u.strip() for u in val.split('&') if u.strip()]
                    print(f'   变量: {env.get("name")} | 账号数: {len(urls)}')
                    for i,u in enumerate(urls[:3]):
                        d = u[:50] + ('...' if len(u)>50 else '')
                        print(f'   {i+1}. {d}')
                    if len(urls) > 3:
                        print(f'   ... 共{len(urls)}个')
            else:
                print('   暂无 sfsyUrl 变量')
        else:
            print('   连接失败')
    else:
        print(C.c('  ⚠️  未配置青龙', C.Y))
    
    print()
    input('按回车返回...')

# ============================================================
# 主程序
# ============================================================
def main():
    banner()
    cfg = load_cfg()
    
    while True:
        menu(cfg)
        choice = input(C.c('请选择 (0-4): ', C.C)).strip()
        
        if choice == '1':
            do_capture(cfg)
        elif choice == '2':
            do_config_ql(cfg)
            cfg = load_cfg()
        elif choice == '3':
            do_manual(cfg)
        elif choice == '4':
            do_view(cfg)
        elif choice == '0':
            print()
            print(C.c('👋 再见！', C.G))
            break
        else:
            print(C.c('❌ 无效选项', C.R))
            time.sleep(0.5)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print()
        print(C.c('\n👋 再见！', C.G))
    finally:
        # 确保关闭代理
        if sys.platform == 'win32':
            win_proxy(False)
