#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
顺丰速运 扫码登录一键获取 sfsyUrl
用法: python sf_qrlogin.py
功能: 终端显示二维码 → 微信扫码登录 → 自动获取sfsyUrl → 同步青龙
"""

import os, sys, json, time, hashlib, uuid, re, base64
from datetime import datetime

# ===== 颜色 =====
class C:
    R='\033[91m';G='\033[92m';Y='\033[93m';B='\033[94m'
    M='\033[95m';C='\033[96m';W='\033[97m';BO='\033[1m';N='\033[0m'
    @staticmethod
    def c(t,c): return f'{c}{t}{C.N}'

# ===== 配置 =====
CONFIG_FILE = 'sf_config.json'
BASE_URL = 'https://mcs-mimp-web.sf-express.com'
SYS_CODE = 'MCS-MIMP-CORE'
PLATFORM = 'MINI_PROGRAM'

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


def gen_headers(token='', body_str='', path=''):
    """生成顺丰API请求头（含签名）"""
    import time
    timestamp = str(int(time.time() * 1000))
    sign_str = f'{token}{timestamp}{SYS_CODE}'
    signature = md5(sign_str)
    
    headers = {
        'sysCode': SYS_CODE,
        'timestamp': timestamp,
        'signature': signature,
        'platform': PLATFORM,
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.0 MiniProgram',
        'Referer': 'https://servicewechat.com/wx33c8bfc18e4e2d2f/0/page-frame.html',
    }
    if token:
        headers['token'] = token
    return headers


def sf_post(path, data=None, token='', cookie=''):
    """发送顺丰API请求"""
    import requests
    url = f'{BASE_URL}{path}'
    
    headers = gen_headers(token=token)
    if cookie:
        headers['Cookie'] = cookie
    
    body = json.dumps(data, separators=(',', ':')) if data else '{}'
    
    try:
        r = requests.post(url, data=body, headers=headers, timeout=15)
        return r.json()
    except Exception as e:
        return {'success': False, 'error': str(e)}


def sf_get(path, token='', cookie=''):
    """发送顺丰GET请求"""
    import requests
    url = f'{BASE_URL}{path}'
    headers = gen_headers(token=token)
    if cookie:
        headers['Cookie'] = cookie
    try:
        r = requests.get(url, headers=headers, timeout=15)
        return r.json()
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ============================================================
# 二维码显示（终端ASCII）
# ============================================================
def print_qr_terminal(qr_data):
    """在终端显示二维码"""
    try:
        import qrcode
    except ImportError:
        print(C.c('📦 正在安装 qrcode 库...', C.B))
        import subprocess
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'qrcode', '-q'],
                      capture_output=True, timeout=60)
        import qrcode
    
    qr = qrcode.QRCode(border=2, box_size=1)
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    print()
    print(C.c('  ╔══════════════════════════════════════╗', C.Y))
    print(C.c('  ║       请用微信扫描下方二维码         ║', C.Y + C.BO))
    print(C.c('  ╚══════════════════════════════════════╝', C.Y))
    print()
    
    # 生成ASCII二维码
    matrix = qr.get_matrix()
    lines = []
    for row in matrix:
        line = ''
        for cell in row:
            line += '  ' if cell else '██'
        lines.append('  ' + C.c(line, C.W))
    
    # 打印
    for line in lines:
        print(line)
    
    print()
    print(C.c('  💡 打开微信 → 扫一扫 → 登录顺丰速运', C.C))
    print()


def print_qr_base64(qr_data):
    """备用：生成二维码图片base64保存到文件"""
    try:
        import qrcode
        from io import BytesIO
        
        qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_H,
                          box_size=10, border=2)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buf = BytesIO()
        img.save(buf, format='PNG')
        img_b64 = base64.b64encode(buf.getvalue()).decode()
        
        # 保存到文件
        img_path = 'sf_qrcode.png'
        img.save(img_path)
        print(C.c(f'💾 二维码已保存到: {img_path}', C.G))
        print(C.c('   请用图片查看器打开扫码', C.Y))
        print()
        return img_path
    except Exception as e:
        print(C.c(f'生成二维码失败: {e}', C.R))
        return None


# ============================================================
# 顺丰扫码登录
# ============================================================
class SFQrLogin:
    """顺丰扫码登录"""
    
    def __init__(self):
        self.qr_id = None
        self.qr_url = None
        self.token = ''
        self.cookies = {}
        self.user_info = None
    
    def get_qrcode(self):
        """获取登录二维码"""
        # 方案1: 小程序二维码登录接口
        path = '/commonPost/~memberNonactivity~memberQrCodeService~getLoginQrCode'
        
        device_id = str(uuid.uuid4()).replace('-', '')
        data = {
            'deviceId': device_id,
            'channelType': 'WX_MINI_PROGRAM',
        }
        
        result = sf_post(path, data)
        
        if result.get('success') or result.get('code') == '0000' or result.get('code') == 0:
            d = result.get('result', result.get('data', {}))
            self.qr_id = d.get('qrId') or d.get('qrCodeId') or d.get('id')
            qr_content = d.get('qrCodeUrl') or d.get('qrContent') or d.get('url')
            
            if qr_content:
                self.qr_url = qr_content
                return True
        
        # 方案2: 尝试另一个接口
        path2 = '/commonPost/~memberNonactivity~memberService~getLoginQrCode'
        result2 = sf_post(path2, {'channelType': 'WX_MINI_PROGRAM'})
        
        if result2.get('success') or result2.get('code') == '0000':
            d = result2.get('result', result2.get('data', {}))
            self.qr_id = d.get('qrId') or d.get('id')
            qr_content = d.get('qrCodeUrl') or d.get('content')
            if qr_content:
                self.qr_url = qr_content
                return True
        
        # 如果都没找到，返回备用方案消息
        return False
    
    def check_qr_status(self):
        """检查二维码扫码状态"""
        if not self.qr_id:
            return {'status': 'error', 'msg': '无二维码ID'}
        
        # 方案1
        path = '/commonPost/~memberNonactivity~memberQrCodeService~checkQrCodeStatus'
        data = {
            'qrId': self.qr_id,
        }
        
        result = sf_post(path, data)
        
        code = result.get('code')
        d = result.get('result', result.get('data', {}))
        
        # 判断状态
        if code in ['0000', 0, '0'] or result.get('success'):
            status = d.get('status', '')
            
            # 0=等待扫码 1=已扫码待确认 2=已确认登录成功
            status_map = {
                '0': 'waiting',
                '1': 'scanned',
                '2': 'success',
                'WAIT': 'waiting',
                'SCANNED': 'scanned',
                'SUCCESS': 'success',
            }
            
            status_code = status_map.get(str(status), str(status))
            
            if status_code == 'success':
                # 登录成功，获取token
                self.token = d.get('token') or d.get('accessToken') or ''
                self.user_info = d.get('memberInfo') or d.get('userInfo') or {}
                return {'status': 'success', 'data': d}
            elif status_code == 'scanned':
                return {'status': 'scanned', 'data': d}
            else:
                return {'status': 'waiting', 'data': d}
        
        return {'status': 'unknown', 'raw': result}
    
    def get_member_cookie(self):
        """用token换取完整会员cookie（sfsyUrl）"""
        if not self.token:
            return None
        
        # 调用会员信息接口，获取完整cookie
        path = '/commonPost/~memberNonactivity~memberService~getMemberInfo'
        result = sf_post(path, {}, token=self.token)
        
        if result.get('success') or result.get('code') in ['0000', 0]:
            d = result.get('result', result.get('data', {}))
            member_id = d.get('memberId') or d.get('memId') or d.get('userId') or ''
            mobile = d.get('mobile') or d.get('phone') or ''
            
            # 构造 cookie 格式
            cookie_parts = []
            if self.token:
                cookie_parts.append(f'sessionId={self.token}')
            if member_id:
                cookie_parts.append(f'_login_user_id_={member_id}')
            if mobile:
                cookie_parts.append(f'_login_mobile_={mobile}')
            
            return ';'.join(cookie_parts) if cookie_parts else None
        
        return None
    
    def get_full_session(self):
        """获取完整session（备用方案）"""
        # 调用一个需要登录的接口，获取set-cookie
        import requests
        
        path = '/commonPost/~memberNonactivity~integralTaskSignPlusService~getSignStatus'
        url = f'{BASE_URL}{path}'
        headers = gen_headers(token=self.token)
        
        try:
            r = requests.post(url, data='{}', headers=headers, timeout=15)
            
            # 从响应中提取cookie
            set_cookies = r.headers.get('set-cookie', '')
            if set_cookies:
                return set_cookies
        except:
            pass
        
        return None


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
# 主流程
# ============================================================
def banner():
    print()
    print(C.c('╔══════════════════════════════════════╗', C.C))
    print(C.c('║  顺丰速运 扫码登录获取 sfsyUrl      ║', C.C + C.BO))
    print(C.c('║  扫码 → 获取 → 同步青龙 一条龙      ║', C.C))
    print(C.c('╚══════════════════════════════════════╝', C.C))
    print()


def do_qr_login(cfg):
    """执行扫码登录流程"""
    print()
    print(C.c('=' * 60, C.Y))
    print(C.c('📱 微信扫码登录', C.BO))
    print(C.c('=' * 60, C.Y))
    print()
    
    # 检查依赖
    try:
        import requests
    except ImportError:
        print(C.c('📦 安装 requests...', C.B))
        import subprocess
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'requests', '-q'],
                      capture_output=True, timeout=60)
    
    # 初始化
    login = SFQrLogin()
    
    # 1. 获取二维码
    print(C.c('🔄 正在获取登录二维码...', C.B))
    
    if not login.get_qrcode():
        print()
        print(C.c('❌ 二维码接口暂不可用（顺丰接口可能有变动）', C.R))
        print()
        print(C.c('💡 备选方案:', C.Y))
        print()
        print('   1. 使用代理抓包工具: python sf_login.py')
        print('   2. 手机端抓包工具: python capture_sfsy.py')
        print('   3. 手动抓包后用 sf_login.py 选项3同步')
        print()
        print(C.c('   顺丰扫码登录接口需要根据最新版本适配，', C.C))
        print(C.c('   目前推荐使用代理抓包方式（最稳定）', C.C))
        print()
        input('按回车返回...')
        return
    
    print(C.c('✅ 二维码获取成功！', C.G))
    
    # 2. 显示二维码
    if login.qr_url:
        print_qr_terminal(login.qr_url)
    
    # 3. 轮询扫码状态
    print(C.c('⏳ 等待扫码... (180秒超时)', C.C))
    print()
    
    start = time.time()
    status = 'waiting'
    last_status = ''
    
    try:
        while time.time() - start < 180:
            result = login.check_qr_status()
            status = result.get('status', 'unknown')
            
            if status != last_status:
                if status == 'waiting':
                    sys.stdout.write(C.c('  ⏳ 等待扫码中...', C.Y))
                elif status == 'scanned':
                    sys.stdout.write('\r' + C.c('  ✅ 已扫码，请在手机上确认登录', C.G + C.BO))
                    print()
                elif status == 'success':
                    sys.stdout.write('\r' + C.c('  🎉 登录成功！', C.G + C.BO))
                    print()
                    break
                last_status = status
            
            # 动态点点
            if status == 'waiting':
                for dot in ['.', '..', '...']:
                    sys.stdout.write('\r' + C.c(f'  ⏳ 等待扫码中{dot}', C.Y))
                    sys.stdout.flush()
                    time.sleep(0.5)
                    if last_status != 'waiting':
                        break
            else:
                time.sleep(2)
        
        if status != 'success':
            print()
            print(C.c('⏰ 超时未完成登录', C.Y))
            print()
            input('按回车返回...')
            return
    
    except KeyboardInterrupt:
        print()
        print(C.c('\n⏹️  已取消', C.Y))
        input('按回车返回...')
        return
    
    # 4. 获取完整cookie
    print()
    print(C.c('🔄 正在获取完整登录凭证...', C.B))
    
    sfsy_url = login.get_member_cookie()
    
    if not sfsy_url:
        # 备用方案
        full_cookie = login.get_full_session()
        if full_cookie:
            sfsy_url = full_cookie
    
    if not sfsy_url and login.token:
        # 最少也有token
        sfsy_url = f'sessionId={login.token}'
        if login.user_info:
            mid = login.user_info.get('memberId') or login.user_info.get('memId') or ''
            if mid:
                sfsy_url += f';_login_user_id_={mid}'
    
    if sfsy_url:
        print(C.c('✅ 获取成功！', C.G))
        print()
        print(C.c('sfsyUrl:', C.C + C.BO))
        print(sfsy_url)
        print()
        
        # 保存
        with open('sfsyUrl.txt', 'w', encoding='utf-8') as f:
            f.write(sfsy_url)
        print(C.c('💾 已保存到 sfsyUrl.txt', C.G))
        print()
        
        # 显示用户信息
        if login.user_info:
            name = login.user_info.get('nickName') or login.user_info.get('nickname') or ''
            mobile = login.user_info.get('mobile') or login.user_info.get('phone') or ''
            if name or mobile:
                print(C.c(f'👤 用户: {name or "未知"} {mobile}', C.M))
                print()
        
        # 询问是否同步到青龙
        if cfg.get('ql_url') and cfg.get('ql_cid') and cfg.get('ql_cs'):
            choice = input(C.c('是否同步到青龙面板? (y/n): ', C.C)).strip().lower()
            if choice == 'y':
                print()
                ql = QLApi(cfg['ql_url'], cfg['ql_cid'], cfg['ql_cs'])
                ql.sync(sfsy_url)
                print()
    else:
        print(C.c('❌ 未能获取到完整的登录凭证', C.R))
        print()
        print(C.c('💡 建议使用代理抓包方式获取: python sf_login.py', C.Y))
    
    print()
    input('按回车返回...')


def do_config_ql(cfg):
    """配置青龙"""
    print()
    print(C.c('=' * 60, C.Y))
    print(C.c('⚙️  配置青龙面板', C.BO))
    print(C.c('=' * 60, C.Y))
    print()
    print(C.c('📝 获取方式:', C.BO))
    print('   青龙面板 → 系统设置 → 应用设置 → 添加应用')
    print('   权限勾选「环境变量」→ 保存得到 ID 和 Secret')
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
        print(C.c('❌ 连接失败', C.R))
    
    print()
    input('按回车返回...')


def do_manual(cfg):
    """手动同步"""
    print()
    print(C.c('=' * 60, C.Y))
    print(C.c('✏️  手动输入URL同步到青龙', C.BO))
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
    
    with open('sfsyUrl.txt', 'a', encoding='utf-8') as f:
        f.write('\n' + url)
    
    print()
    input('按回车返回...')


def do_view(cfg):
    """查看已保存的"""
    print()
    print(C.c('=' * 60, C.Y))
    print(C.c('📋 已保存的 sfsyUrl', C.BO))
    print(C.c('=' * 60, C.Y))
    print()
    
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


def main():
    banner()
    cfg = load_cfg()
    
    while True:
        print(C.c('【 主菜单 】', C.BO))
        print()
        print(C.c('  1', C.G) + ' - 扫码登录获取 sfsyUrl ⭐')
        print(C.c('  2', C.G) + ' - 配置青龙面板 (自动同步)')
        print(C.c('  3', C.G) + ' - 手动输入URL同步到青龙')
        print(C.c('  4', C.G) + ' - 查看已保存的URL')
        print(C.c('  0', C.Y) + ' - 退出')
        print()
        if cfg.get('ql_url'):
            print(C.c(f'  ✅ 青龙: {cfg["ql_url"]}', C.G))
        else:
            print(C.c(f'  ⚠️  未配置青龙', C.Y))
        print()
        
        choice = input(C.c('请选择 (0-4): ', C.C)).strip()
        
        if choice == '1':
            do_qr_login(cfg)
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
