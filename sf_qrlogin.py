#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
顺丰速运 sfsyUrl 综合获取工具 v2.0
多种获取方式，自动降级，一键同步青龙
- 方式1: 扫码登录（10+接口自动尝试）
- 方式2: 代理抓包（mitmproxy 自动开系统代理）
- 方式3: 手动输入同步
用法: python sf_qrlogin.py
"""

import os, sys, json, time, hashlib, uuid, re, base64, threading, subprocess
from datetime import datetime

# ===== 颜色 =====
class C:
    R='\033[91m';G='\033[92m';Y='\033[93m';B='\033[94m'
    M='\033[95m';C='\033[96m';W='\033[97m';BO='\033[1m';N='\033[0m'
    @staticmethod
    def c(t,c): return f'{c}{t}{C.N}'
    @staticmethod
    def ok(t): return C.c(f'✅ {t}', C.G)
    @staticmethod
    def fail(t): return C.c(f'❌ {t}', C.R)
    @staticmethod
    def warn(t): return C.c(f'⚠️  {t}', C.Y)
    @staticmethod
    def info(t): return C.c(f'ℹ️  {t}', C.B)

# ===== 配置 =====
CONFIG_FILE = 'sf_config.json'
BASE_URL = 'https://mcs-mimp-web.sf-express.com'
SYS_CODE = 'MCS-MIMP-CORE'
PROXY_PORT = 8899

# ============================================================
# 工具函数
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

def md5(s):
    return hashlib.md5(s.encode('utf-8')).hexdigest().lower()

def gen_headers(token='', sys_code=SYS_CODE):
    timestamp = str(int(time.time() * 1000))
    sign_str = f'{token}{timestamp}{sys_code}'
    signature = md5(sign_str)
    return {
        'sysCode': sys_code,
        'timestamp': timestamp,
        'signature': signature,
        'platform': 'MINI_PROGRAM',
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.40 MiniProgram',
    }

def sf_post(path, data=None, token='', base_url=BASE_URL, sys_code=SYS_CODE):
    import requests
    url = f'{base_url}{path}'
    headers = gen_headers(token=token, sys_code=sys_code)
    body = json.dumps(data or {}, separators=(',', ':'))
    try:
        r = requests.post(url, data=body, headers=headers, timeout=15)
        return r.json()
    except Exception as e:
        return {'success': False, 'error': str(e)}

def is_success(result):
    """判断顺丰接口返回是否成功"""
    if result.get('success') is True:
        return True
    code = str(result.get('code', ''))
    if code in ['0000', '0', '200', 'SUCCESS']:
        return True
    if result.get('result') and isinstance(result.get('result'), dict):
        return True
    return False

def get_data(result):
    """从接口返回中提取数据"""
    if isinstance(result.get('result'), dict):
        return result['result']
    if isinstance(result.get('data'), dict):
        return result['data']
    return result

# ============================================================
# 二维码显示
# ============================================================
def print_qr(qr_data):
    """终端显示二维码"""
    try:
        import qrcode
    except ImportError:
        print(C.info('正在安装 qrcode 库...'))
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'qrcode', '-q',
                       '-i', 'https://pypi.tuna.tsinghua.edu.cn/simple'],
                      capture_output=True, timeout=60)
        import qrcode
    
    qr = qrcode.QRCode(border=2, box_size=1)
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    print()
    print(C.c('  ╔' + '═' * 36 + '╗', C.Y))
    print(C.c('  ║' + C.c('    微信扫码登录顺丰速运    ', C.Y + C.BO).center(42) + C.c('║', C.Y)))
    print(C.c('  ╚' + '═' * 36 + '╝', C.Y))
    print()
    
    matrix = qr.get_matrix()
    for row in matrix:
        line = ''
        for cell in row:
            line += '  ' if cell else '██'
        print('  ' + C.c(line, C.W))
    
    print()
    print(C.c('  💡 打开微信 → 扫一扫 → 确认登录', C.C))
    print()

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
# 顺丰扫码登录（多接口尝试）
# ============================================================
class SFQrLogin:
    def __init__(self):
        self.qr_id = None
        self.qr_content = None
        self.token = ''
        self.user_info = {}
        self.check_path = None  # 记录用哪个接口获取的，用对应的检查接口
    
    # 所有可能的二维码接口组合
    QR_INTERFACES = [
        # (获取二维码路径, 检查状态路径, 二维码字段, ID字段, sysCode)
        ('/commonPost/~memberNonactivity~memberQrCodeService~getLoginQrCode',
         '/commonPost/~memberNonactivity~memberQrCodeService~checkQrCodeStatus',
         'qrCodeUrl', 'qrId', SYS_CODE),
        ('/commonPost/~memberNonactivity~memberService~getQrCode',
         '/commonPost/~memberNonactivity~memberService~checkQrCode',
         'qrCode', 'qrCodeId', SYS_CODE),
        ('/commonPost/~memberNonactivity~memberService~getLoginQrCode',
         '/commonPost/~memberNonactivity~memberService~checkLoginQrCode',
         'content', 'id', SYS_CODE),
        ('/commonPost/~memberNonactivity~integralTaskSignPlusService~getQrCode',
         '/commonPost/~memberNonactivity~integralTaskSignPlusService~checkQrCode',
         'qrUrl', 'qrId', SYS_CODE),
        ('/commonRoutePost/memberEs/qrcode/getLoginQrcode',
         '/commonRoutePost/memberEs/qrcode/checkQrcodeStatus',
         'qrcodeUrl', 'qrcodeId', SYS_CODE),
        ('/commonPost/~memberActivity~memberQrService~getLoginQr',
         '/commonPost/~memberActivity~memberQrService~checkQrStatus',
         'qrContent', 'qrNo', SYS_CODE),
        ('/mcs-mimp/commonPost/~memberNonactivity~memberQrCodeService~getLoginQrCode',
         '/mcs-mimp/commonPost/~memberNonactivity~memberQrCodeService~checkQrCodeStatus',
         'qrCodeUrl', 'qrId', SYS_CODE),
        ('/commonPost/~memberNonactivity~loginService~getQrCode',
         '/commonPost/~memberNonactivity~loginService~checkQrCode',
         'url', 'code', SYS_CODE),
        ('/commonPost/~memberNonactivity~authService~getLoginQrcode',
         '/commonPost/~memberNonactivity~authService~checkLoginQrcode',
         'qrcode', 'qrcodeId', SYS_CODE),
        ('/commonPost/~memberNonactivity~wxMiniappService~getLoginQrCode',
         '/commonPost/~memberNonactivity~wxMiniappService~checkQrCode',
         'qrImgUrl', 'qrKey', SYS_CODE),
    ]
    
    def get_qrcode(self):
        """尝试多个接口获取二维码"""
        device_id = str(uuid.uuid4()).replace('-', '')
        
        print()
        print(C.c('🔍 正在尝试多种二维码接口...', C.B))
        print()
        
        for i, (qr_path, check_path, qr_field, id_field, sys_code) in enumerate(self.QR_INTERFACES):
            sys.stdout.write(f'\r  尝试接口 {i+1}/{len(self.QR_INTERFACES)}: {qr_path[-40:]}')
            sys.stdout.flush()
            
            # 构造请求数据
            data_list = [
                {'deviceId': device_id, 'channelType': 'WX_MINI_PROGRAM'},
                {'channelType': 'MINI_PROGRAM'},
                {'source': 'WX_MINI_APP'},
                {},
            ]
            
            for data in data_list:
                result = sf_post(qr_path, data, sys_code=sys_code)
                
                if is_success(result):
                    d = get_data(result)
                    qr_content = (d.get(qr_field) or d.get(qr_field.lower())
                                 or d.get('qrCode') or d.get('qrcode') or d.get('url')
                                 or d.get('content') or d.get('qrUrl'))
                    qr_id = (d.get(id_field) or d.get(id_field.lower())
                            or d.get('qrId') or d.get('id') or d.get('code')
                            or d.get('qrcodeId') or d.get('qrKey'))
                    
                    if qr_content and qr_id:
                        self.qr_content = qr_content
                        self.qr_id = qr_id
                        self.check_path = check_path
                        self._qr_field = qr_field
                        self._id_field = id_field
                        self._sys_code = sys_code
                        
                        sys.stdout.write('\r' + ' ' * 60 + '\r')
                        print(C.ok(f'接口 {i+1} 成功！'))
                        return True
        
        sys.stdout.write('\r' + ' ' * 60 + '\r')
        return False
    
    def check_status(self):
        """检查扫码状态"""
        if not self.qr_id or not self.check_path:
            return {'status': 'error'}
        
        result = sf_post(self.check_path, {self._id_field: self.qr_id},
                        sys_code=self._sys_code)
        
        if not is_success(result):
            return {'status': 'unknown', 'raw': result}
        
        d = get_data(result)
        status = str(d.get('status', d.get('qrStatus', d.get('state', ''))))
        
        # 状态映射
        status_lower = status.lower()
        if status in ['0', 'WAIT', 'waiting', 'PENDING'] or 'wait' in status_lower:
            return {'status': 'waiting', 'data': d}
        elif status in ['1', 'SCANNED', 'scanned', 'CONFIRMING'] or 'scan' in status_lower:
            return {'status': 'scanned', 'data': d}
        elif status in ['2', 'SUCCESS', 'success', 'OK', 'LOGIN_SUCCESS'] or 'success' in status_lower:
            # 登录成功，提取token
            self.token = (d.get('token') or d.get('accessToken') or d.get('sessionId')
                         or d.get('session_token', ''))
            self.user_info = (d.get('memberInfo') or d.get('userInfo')
                             or d.get('member', d))
            return {'status': 'success', 'data': d}
        elif status in ['-1', 'EXPIRED', 'expired', 'INVALID']:
            return {'status': 'expired', 'data': d}
        
        # 如果有token直接认为成功
        if d.get('token') or d.get('accessToken'):
            self.token = d.get('token') or d.get('accessToken')
            self.user_info = d.get('memberInfo', d)
            return {'status': 'success', 'data': d}
        
        return {'status': 'waiting', 'data': d}
    
    def get_sfsy_url(self):
        """获取可用的 sfsyUrl"""
        if not self.token:
            return None
        
        # 方式1: 从用户信息提取
        mid = (self.user_info.get('memberId') or self.user_info.get('memId')
              or self.user_info.get('userId') or self.user_info.get('id', ''))
        mobile = self.user_info.get('mobile') or self.user_info.get('phone', '')
        
        # 方式2: 调用会员信息接口
        if not mid:
            paths = [
                '/commonPost/~memberNonactivity~memberService~getMemberInfo',
                '/commonPost/~memberNonactivity~memberService~queryMemberInfo',
                '/commonPost/~memberNonactivity~integralTaskSignPlusService~getMemberInfo',
            ]
            for p in paths:
                r = sf_post(p, {}, token=self.token)
                if is_success(r):
                    d = get_data(r)
                    mid = d.get('memberId') or d.get('memId') or d.get('userId') or ''
                    mobile = d.get('mobile') or d.get('phone') or ''
                    if mid:
                        break
        
        # 构造 cookie 格式
        parts = []
        parts.append(f'sessionId={self.token}')
        if mid:
            parts.append(f'_login_user_id_={mid}')
        if mobile:
            parts.append(f'_login_mobile_={mobile}')
        
        return ';'.join(parts)

# ============================================================
# 代理抓包模式
# ============================================================
class ProxyCapture:
    def __init__(self):
        self.urls = []
        self.best = None
        self.stop = threading.Event()
        self.lock = threading.Lock()
    
    def score(self, url):
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
    
    def add_url(self, url, source=''):
        with self.lock:
            for u in self.urls:
                if u['url'] == url:
                    return
            sc = self.score(url)
            self.urls.append({'url': url, 'score': sc, 'source': source})
            self.urls.sort(key=lambda x: x['score'], reverse=True)
            if sc >= 120:
                if not self.best or sc > self.best['score']:
                    self.best = {'url': url, 'score': sc}
                    self.stop.set()
                    self._print_found(url, sc, source)
    
    def _print_found(self, url, sc, source):
        print()
        print(C.c('=' * 56, C.Y))
        print(C.c(f'🎉 找到 sfsyUrl！(质量分: {sc})', C.G + C.BO))
        print(C.c('=' * 56, C.Y))
        print(f'  来源: {source}')
        if len(url) > 100:
            print(f'  URL: {url[:100]}...')
        else:
            print(f'  URL: {url}')
        print(C.c('=' * 56, C.Y))
        print()
    
    def run(self):
        """运行代理抓包"""
        # 检查 mitmproxy
        try:
            from mitmproxy.tools.main import mitmdump
        except ImportError:
            print(C.info('正在安装 mitmproxy...'))
            subprocess.run([sys.executable, '-m', 'pip', 'install', 'mitmproxy',
                           '-i', 'https://pypi.tuna.tsinghua.edu.cn/simple'],
                          capture_output=True, timeout=180)
            from mitmproxy.tools.main import mitmdump
        
        # 设置系统代理
        if sys.platform == 'win32':
            print(C.info('设置系统代理...'), end=' ')
            if win_proxy(True):
                print(C.c('✅', C.G))
            else:
                print(C.c('❌', C.R))
            print()
        
        print(C.c('🌐 代理服务器已启动 (端口: {})'.format(PROXY_PORT), C.C))
        print(C.c('💡 请打开微信 → 顺丰速运+小程序 → 积分页面', C.C + C.BO))
        print(C.c('   找到后自动停止... (Ctrl+C 手动停止)', C.C))
        print()
        
        # 检查证书
        home = os.path.expanduser('~')
        cert = os.path.join(home, '.mitmproxy', 'mitmproxy-ca-cert.cer')
        if not os.path.exists(cert):
            print(C.warn('未检测到 mitmproxy 证书'))
            print('  请访问 http://mitm.it 下载安装证书到「受信任的根证书颁发机构」')
            print('  安装完成后刷新小程序页面')
            print()
        
        # 启动 mitmproxy
        proxy_capture = self
        
        # 定义 mitmproxy 回调
        def response(flow):
            if proxy_capture.stop.is_set():
                return
            host = flow.request.host
            if not any(d in host for d in ['sf-express.com']):
                return
            url = flow.request.pretty_url
            kws = ['memberId','_login_user_id_','_login_mobile_','sessionId',
                   'shareGiftReceiveRedirect','shareRedirect','integral','/point/']
            if any(k.lower() in url.lower() for k in kws):
                proxy_capture.add_url(url, 'URL')
            
            # 检查 set-cookie
            scs = flow.response.headers.get_all('set-cookie')
            if scs:
                cs = ';'.join(c.split(';')[0].strip() for c in scs)
                if '_login_user_id_' in cs or 'sessionId' in cs:
                    parts = []
                    for c in scs:
                        kv = c.split(';')[0].strip()
                        if kv and any(k in kv for k in ['sessionId','_login_','memberId']):
                            parts.append(kv)
                    if parts:
                        proxy_capture.add_url(';'.join(parts), 'Cookie')
        
        def request(flow):
            if proxy_capture.stop.is_set():
                return
            host = flow.request.host
            if not any(d in host for d in ['sf-express.com']):
                return
            ck = flow.request.headers.get('cookie', '')
            if ck and '_login_user_id_' in ck:
                parts = []
                for item in ck.split(';'):
                    item = item.strip()
                    if any(k in item for k in ['sessionId','_login_user_id_','_login_mobile_','memberId']):
                        parts.append(item)
                if len(parts) >= 2:
                    proxy_capture.add_url(';'.join(parts), '请求Cookie')
        
        # 注入回调到全局命名空间
        import __main__
        __main__.response = response
        __main__.request = request
        
        # 运行 mitmproxy
        t = threading.Thread(target=lambda: mitmdump([
            '-p', str(PROXY_PORT), '-s', __file__, '--quiet',
            '--set', 'block_global=false',
        ]), daemon=True)
        t.start()
        
        # 等待结果
        try:
            start = time.time()
            while not self.stop.is_set():
                time.sleep(1)
                if time.time() - start > 180:
                    print()
                    print(C.warn('3分钟超时'))
                    break
        except KeyboardInterrupt:
            pass
        
        self.stop.set()
        time.sleep(1)
        
        # 关闭代理
        if sys.platform == 'win32':
            print()
            print(C.info('关闭系统代理...'), end=' ')
            if win_proxy(False):
                print(C.c('✅', C.G))
            else:
                print(C.c('❌', C.R))
        
        return self.best['url'] if self.best else (self.urls[0]['url'] if self.urls else None)

# ============================================================
# 青龙面板
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
            print(C.fail('青龙登录失败'))
            return False
        envs = self.get_envs('sfsyUrl')
        if envs:
            env = envs[0]
            old = env.get('value','')
            urls = [u.strip() for u in old.split('&') if u.strip()]
            if url not in urls:
                urls.append(url)
            if self.update_env(env['_id'], 'sfsyUrl', '&'.join(urls), remarks):
                print(C.ok(f'已同步到青龙 (共{len(urls)}个账号)'))
                return True
        else:
            if self.add_env('sfsyUrl', url, remarks):
                print(C.ok('已同步到青龙'))
                return True
        print(C.fail('同步失败'))
        return False

# ============================================================
# 保存 sfsyUrl
# ============================================================
def save_sfsy_url(url):
    with open('sfsyUrl.txt', 'w', encoding='utf-8') as f:
        f.write(url)
    print(C.ok(f'已保存到 sfsyUrl.txt'))

def ask_sync(cfg, url):
    """询问是否同步到青龙"""
    if all([cfg.get('ql_url'), cfg.get('ql_cid'), cfg.get('ql_cs')]):
        print()
        choice = input(C.c('是否同步到青龙面板? (y/n): ', C.C)).strip().lower()
        if choice == 'y':
            print()
            ql = QLApi(cfg['ql_url'], cfg['ql_cid'], cfg['ql_cs'])
            ql.sync(url)

# ============================================================
# 功能入口
# ============================================================
def do_qr_login(cfg):
    """扫码登录"""
    print()
    print(C.c('=' * 56, C.Y))
    print(C.c('📱 方式一：微信扫码登录', C.BO))
    print(C.c('=' * 56, C.Y))
    
    # 检查依赖
    try:
        import requests
    except ImportError:
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'requests', '-q'],
                      capture_output=True, timeout=60)
    
    login = SFQrLogin()
    
    if not login.get_qrcode():
        print()
        print(C.fail('扫码登录接口暂不可用'))
        print()
        print(C.c('💡 建议切换到代理抓包模式（更稳定）', C.Y))
        choice = input(C.c('是否切换到代理抓包模式? (y/n): ', C.C)).strip().lower()
        if choice == 'y':
            return do_proxy_capture(cfg)
        print()
        input('按回车返回...')
        return
    
    # 显示二维码
    if login.qr_content:
        print_qr(login.qr_content)
    
    print(C.c('⏳ 等待扫码... (180秒超时)', C.C))
    print()
    
    start = time.time()
    status = 'waiting'
    last = ''
    dot_state = 0
    
    try:
        while time.time() - start < 180:
            r = login.check_status()
            status = r.get('status', 'waiting')
            
            if status != last:
                if status == 'waiting':
                    pass  # 下面统一显示点点
                elif status == 'scanned':
                    print('\r' + C.c('  ✅ 已扫码，请在手机上确认登录', C.G + C.BO) + ' ' * 20)
                elif status == 'success':
                    print('\r' + C.c('  🎉 登录成功！', C.G + C.BO) + ' ' * 30)
                    break
                elif status == 'expired':
                    print('\r' + C.c('  ⏰ 二维码已过期', C.Y) + ' ' * 30)
                    break
                last = status
            
            if status == 'waiting':
                dots = '.' * ((dot_state % 3) + 1)
                sys.stdout.write('\r  ⏳ 等待扫码中' + dots + ' ' * 10)
                sys.stdout.flush()
                dot_state += 1
                time.sleep(0.8)
            else:
                time.sleep(2)
        
        if status not in ['success']:
            print()
            print()
            print(C.warn('未完成登录'))
            print()
            print(C.c('💡 试试代理抓包模式？更稳定', C.C))
            choice = input(C.c('切换到代理抓包模式? (y/n): ', C.C)).strip().lower()
            if choice == 'y':
                return do_proxy_capture(cfg)
            input('按回车返回...')
            return
    
    except KeyboardInterrupt:
        print()
        print(C.warn('已取消'))
        input('按回车返回...')
        return
    
    # 获取 sfsyUrl
    print()
    print(C.info('正在获取登录凭证...'))
    
    sfsy_url = login.get_sfsy_url()
    
    if sfsy_url:
        print()
        print(C.c('🎉 获取成功！', C.G + C.BO))
        print()
        print(C.c('sfsyUrl:', C.C + C.BO))
        print(sfsy_url)
        print()
        
        save_sfsy_url(sfsy_url)
        
        if login.user_info:
            name = login.user_info.get('nickName') or login.user_info.get('nickname', '')
            mobile = login.user_info.get('mobile') or login.user_info.get('phone', '')
            if name or mobile:
                print()
                print(C.c(f'👤 用户: {name or "未知"} {mobile}', C.M))
        
        ask_sync(cfg, sfsy_url)
    else:
        print(C.fail('未能获取完整凭证'))
        print(C.c('💡 建议使用代理抓包方式', C.Y))
    
    print()
    input('按回车返回...')


def do_proxy_capture(cfg):
    """代理抓包"""
    print()
    print(C.c('=' * 56, C.Y))
    print(C.c('🌐 方式二：代理抓包获取', C.BO))
    print(C.c('=' * 56, C.Y))
    print()
    print(C.c('📱 操作步骤:', C.BO))
    print()
    print('  1. 确保电脑微信已登录')
    print('  2. 脚本自动设置系统代理')
    print('  3. 打开微信 → 顺丰速运+小程序')
    print('  4. 进入「我的」→「积分」页面')
    print('  5. 自动捕获 sfsyUrl')
    print()
    
    input(C.c('按回车开始...', C.C))
    
    cap = ProxyCapture()
    url = cap.run()
    
    print()
    if url:
        print(C.c('🎉 捕获成功！', C.G + C.BO))
        print()
        print(C.c('sfsyUrl:', C.C + C.BO))
        print(url)
        print()
        save_sfsy_url(url)
        ask_sync(cfg, url)
    else:
        print(C.fail('未捕获到可用的 sfsyUrl'))
        print()
        print(C.c('💡 尝试下拉刷新小程序页面，或切换页面', C.Y))
    
    print()
    input('按回车返回...')


def do_config_ql(cfg):
    """配置青龙"""
    print()
    print(C.c('=' * 56, C.Y))
    print(C.c('⚙️  配置青龙面板', C.BO))
    print(C.c('=' * 56, C.Y))
    print()
    print(C.c('📝 获取方式:', C.BO))
    print('  青龙面板 → 系统设置 → 应用设置 → 添加应用')
    print('  权限勾选「环境变量」→ 保存得到 ID 和 Secret')
    print()
    
    if cfg.get('ql_url'):
        print(f'  当前地址: {cfg["ql_url"]}')
        url = input('  青龙地址 (回车保留): ').strip() or cfg['ql_url']
    else:
        url = input('  青龙地址 (如 http://192.168.1.100:5700): ').strip()
    
    if cfg.get('ql_cid'):
        print(f'  当前 Client ID: {cfg["ql_cid"]}')
        cid = input('  Client ID (回车保留): ').strip() or cfg['ql_cid']
    else:
        cid = input('  Client ID: ').strip()
    
    if cfg.get('ql_cs'):
        cs = input('  Client Secret (回车保留当前): ').strip() or cfg['ql_cs']
    else:
        cs = input('  Client Secret: ').strip()
    
    if not all([url, cid, cs]):
        print(C.fail('配置不完整'))
        input('按回车返回...')
        return
    
    print()
    print(C.info('测试连接...'))
    ql = QLApi(url, cid, cs)
    if ql.login():
        print(C.ok('连接成功！'))
        cfg['ql_url'] = url
        cfg['ql_cid'] = cid
        cfg['ql_cs'] = cs
        save_cfg(cfg)
        print(C.ok('配置已保存'))
    else:
        print(C.fail('连接失败，请检查地址和密钥'))
    
    print()
    input('按回车返回...')


def do_manual(cfg):
    """手动同步"""
    print()
    print(C.c('=' * 56, C.Y))
    print(C.c('✏️  方式三：手动输入同步', C.BO))
    print(C.c('=' * 56, C.Y))
    print()
    
    if not all([cfg.get('ql_url'), cfg.get('ql_cid'), cfg.get('ql_cs')]):
        print(C.fail('请先配置青龙面板 (选项4)'))
        input('按回车返回...')
        return
    
    url = input('  请输入 sfsyUrl: ').strip()
    if not url:
        print(C.fail('URL 不能为空'))
        input('按回车返回...')
        return
    
    print()
    ql = QLApi(cfg['ql_url'], cfg['ql_cid'], cfg['ql_cs'])
    ql.sync(url)
    
    with open('sfsyUrl.txt', 'a', encoding='utf-8') as f:
        f.write('\n' + url)
    
    print()
    input('按回车返回...')


def do_view(cfg):
    """查看"""
    print()
    print(C.c('=' * 56, C.Y))
    print(C.c('📋 已保存的 sfsyUrl', C.BO))
    print(C.c('=' * 56, C.Y))
    print()
    
    if os.path.exists('sfsyUrl.txt'):
        try:
            with open('sfsyUrl.txt','r',encoding='utf-8') as f:
                c = f.read().strip()
            if c:
                urls = [u.strip() for u in c.replace('&','\n').split('\n') if u.strip()]
                print(C.c(f'📁 本地文件: {len(urls)} 个', C.B))
                for i,u in enumerate(urls):
                    d = u[:55] + ('...' if len(u)>55 else '')
                    print(f'   {i+1}. {d}')
                print()
        except: pass
    
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
                        d = u[:45] + ('...' if len(u)>45 else '')
                        print(f'   {i+1}. {d}')
                    if len(urls) > 3:
                        print(f'   ... 共{len(urls)}个')
            else:
                print('   暂无 sfsyUrl 变量')
        else:
            print('   连接失败')
    else:
        print(C.warn('未配置青龙'))
    
    print()
    input('按回车返回...')

# ============================================================
# 主程序
# ============================================================
def banner():
    print()
    print(C.c('╔' + '═' * 46 + '╗', C.C))
    print(C.c('║', C.C) + C.c('   顺丰速运 sfsyUrl 获取工具 v2.0    ', C.C + C.BO).center(52) + C.c('║', C.C))
    print(C.c('║', C.C) + C.c('   扫码 / 代理抓包 / 手动 三合一    ', C.C).center(52) + C.c('║', C.C))
    print(C.c('╚' + '═' * 46 + '╝', C.C))
    print()

def main():
    banner()
    cfg = load_cfg()
    
    while True:
        print(C.c('【 主菜单 】', C.BO))
        print()
        print(C.c('  1', C.G) + ' - 扫码登录获取 ⭐ (推荐先试)')
        print(C.c('  2', C.G) + ' - 代理抓包获取 (稳定可靠)')
        print(C.c('  3', C.G) + ' - 手动输入URL同步')
        print(C.c('  4', C.G) + ' - 配置青龙面板')
        print(C.c('  5', C.G) + ' - 查看已保存的URL')
        print(C.c('  0', C.Y) + ' - 退出')
        print()
        if cfg.get('ql_url'):
            print(C.c(f'  ✅ 青龙: {cfg["ql_url"]}', C.G))
        else:
            print(C.warn('未配置青龙 (同步功能不可用)'))
        print()
        
        choice = input(C.c('请选择 (0-5): ', C.C)).strip()
        
        if choice == '1':
            do_qr_login(cfg)
        elif choice == '2':
            do_proxy_capture(cfg)
        elif choice == '3':
            do_manual(cfg)
        elif choice == '4':
            do_config_ql(cfg)
            cfg = load_cfg()
        elif choice == '5':
            do_view(cfg)
        elif choice == '0':
            print()
            print(C.c('👋 再见！', C.G))
            break
        else:
            print(C.fail('无效选项'))
            time.sleep(0.5)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print()
        print(C.c('\n👋 再见！', C.G))
    finally:
        if sys.platform == 'win32':
            win_proxy(False)
