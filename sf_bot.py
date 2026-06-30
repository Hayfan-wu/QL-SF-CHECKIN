"""
顺丰速运 sfsyUrl 机器人（完整版）
支持多渠道消息推送 + 命令交互

功能：
- 多渠道推送：WxPusher、企业微信、钉钉、飞书
- 账号管理：添加、删除、替换、列表、测试
- 签到功能：立即签到、签到状态、积分查询
- WxPusher 双向交互

环境变量配置见 .env.example
"""

import os
import re
import sys
import time
import json
import hashlib
from datetime import datetime
from urllib.parse import unquote, urlparse, parse_qs

import requests
requests.packages.urllib3.disable_warnings()


VERSION = "2.0.0"


# ==================== 配置 ====================
class Config:
    """全局配置"""
    # 青龙面板
    QL_URL = os.getenv('QL_URL', '')
    QL_CLIENT_ID = os.getenv('QL_CLIENT_ID', '')
    QL_CLIENT_SECRET = os.getenv('QL_CLIENT_SECRET', '')
    ENV_NAME = os.getenv('ENV_NAME', 'sfsyUrl')
    
    # WxPusher
    WXPUSHER_APP_TOKEN = os.getenv('WXPUSHER_APP_TOKEN', '')
    WXPUSHER_UIDS = os.getenv('WXPUSHER_UIDS', '')
    WXPUSHER_TOPIC_IDS = os.getenv('WXPUSHER_TOPIC_IDS', '')
    
    # 企业微信
    WECOM_WEBHOOK = os.getenv('WECOM_WEBHOOK', '')
    
    # 钉钉
    DINGTALK_WEBHOOK = os.getenv('DINGTALK_WEBHOOK', '')
    DINGTALK_SECRET = os.getenv('DINGTALK_SECRET', '')
    
    # 飞书
    FEISHU_WEBHOOK = os.getenv('FEISHU_WEBHOOK', '')
    FEISHU_SECRET = os.getenv('FEISHU_SECRET', '')
    
    # 机器人设置
    POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', '30'))
    ADMIN_UIDS = os.getenv('ADMIN_UIDS', os.getenv('WXPUSHER_UIDS', ''))
    
    # 签到设置
    CHECKIN_HOUR = int(os.getenv('CHECKIN_HOUR', '8'))
    CHECKIN_MINUTE = int(os.getenv('CHECKIN_MINUTE', '0'))


# ==================== 工具函数 ====================
def mask_phone(phone: str) -> str:
    """手机号脱敏"""
    if not phone:
        return '未知'
    phone = str(phone)
    if len(phone) >= 11:
        return phone[:3] + '****' + phone[7:]
    return phone


def get_phone_from_url(url: str) -> str:
    """从 URL/CK 中提取手机号"""
    try:
        decoded = unquote(url)
        # 从 CK 提取
        if '_login_mobile_=' in decoded:
            match = re.search(r'_login_mobile_=([^;&\s]+)', decoded)
            if match:
                return match.group(1)
        # 从 URL 参数提取
        elif 'mobile=' in decoded:
            parsed = urlparse(decoded)
            params = parse_qs(parsed.query)
            return params.get('mobile', [''])[0]
    except:
        pass
    return ''


def parse_sfsy_url(text: str):
    """从文本中提取 sfsyUrl/CK"""
    text = text.strip()
    
    # 尝试 CK 格式
    if '_login_mobile_=' in text and '_login_user_id_=' in text:
        pattern = r'(?:sessionId=[^;&\s]+;?)?_login_mobile_=[^;&\s]+;?_login_user_id_=[^;&\s]+'
        match = re.search(pattern, text)
        if match:
            return match.group(0).strip(';')
    
    # 尝试 URL 格式
    if 'sf-express.com' in text:
        match = re.search(r'https?://[^\s]+sf-express\.com[^\s]*', text)
        if match:
            return match.group(0)
    
    return None


# ==================== 青龙面板 API ====================
class QingLong:
    """青龙面板操作类"""
    
    def __init__(self, url: str, client_id: str, client_secret: str):
        self.url = url.rstrip('/')
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self.token_expire = 0
    
    def _get_token(self) -> bool:
        try:
            resp = requests.post(
                f'{self.url}/open/auth/token',
                params={'client_id': self.client_id, 'client_secret': self.client_secret},
                timeout=10
            )
            data = resp.json()
            if data.get('code') == 200:
                self.token = data['data']['token']
                self.token_expire = time.time() + data['data'].get('expires_in', 7200) - 60
                return True
            return False
        except Exception as e:
            print(f'[青龙] 获取token失败: {e}')
            return False
    
    def _ensure_token(self) -> bool:
        if not self.token or time.time() > self.token_expire:
            return self._get_token()
        return True
    
    def _headers(self):
        return {'Authorization': f'Bearer {self.token}'}
    
    def get_env(self, name: str):
        if not self._ensure_token():
            return None
        try:
            resp = requests.get(
                f'{self.url}/open/envs',
                headers=self._headers(),
                params={'searchValue': name},
                timeout=10
            )
            data = resp.json()
            if data.get('code') == 200:
                for env in data.get('data', []):
                    if env.get('name') == name:
                        return env
            return None
        except Exception as e:
            print(f'[青龙] 获取环境变量失败: {e}')
            return None
    
    def update_env(self, env_id: int, name: str, value: str, remarks: str = '') -> bool:
        if not self._ensure_token():
            return False
        try:
            resp = requests.put(
                f'{self.url}/open/envs',
                headers=self._headers(),
                json={'id': env_id, 'name': name, 'value': value, 'remarks': remarks},
                timeout=10
            )
            return resp.json().get('code') == 200
        except Exception as e:
            print(f'[青龙] 更新环境变量失败: {e}')
            return False
    
    def add_env(self, name: str, value: str, remarks: str = '') -> bool:
        if not self._ensure_token():
            return False
        try:
            resp = requests.post(
                f'{self.url}/open/envs',
                headers=self._headers(),
                json=[{'name': name, 'value': value, 'remarks': remarks}],
                timeout=10
            )
            return resp.json().get('code') == 200
        except Exception as e:
            print(f'[青龙] 新增环境变量失败: {e}')
            return False
    
    def get_urls(self):
        """获取 sfsyUrl 列表"""
        env = self.get_env(Config.ENV_NAME)
        if not env:
            return []
        return [u.strip() for u in env.get('value', '').split('&') if u.strip()]
    
    def set_urls(self, urls, remarks: str = '') -> bool:
        """设置 sfsyUrl（全量替换）"""
        env = self.get_env(Config.ENV_NAME)
        value = '&'.join(urls)
        if not remarks:
            remarks = f'共{len(urls)}个账号 - 机器人更新'
        if env:
            return self.update_env(env['id'], Config.ENV_NAME, value, remarks)
        else:
            return self.add_env(Config.ENV_NAME, value, remarks)
    
    def test_connection(self):
        """测试连接"""
        return self.get_env(Config.ENV_NAME) is not None


# ==================== 顺丰签到核心 ====================
class SFCheckin:
    """顺丰签到核心逻辑"""
    
    API_BASE = "https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost"
    
    def __init__(self, sfsy_url: str):
        self.sfsy_url = sfsy_url
        self.session = requests.Session()
        self.user_info = None
        self.points = 0
    
    def _parse_ck(self, url: str) -> dict:
        """解析 CK/URL 获取登录信息"""
        cookies = {}
        decoded = unquote(url)
        
        if '_login_mobile_' in decoded and '_login_user_id_' in decoded:
            # CK 格式
            for match in re.finditer(r'([^=;\s]+)=([^=;&\s]*)', decoded):
                key, value = match.group(1), match.group(2)
                if key in ('sessionId', '_login_mobile_', '_login_user_id_', 'JSESSIONID'):
                    cookies[key] = value
                    if key == 'sessionId':
                        cookies['JSESSIONID'] = value
        elif 'sf-express.com' in decoded:
            # URL 格式 - 需要访问获取 cookie
            pass
        
        return cookies
    
    def login(self) -> bool:
        """登录（验证有效性）"""
        try:
            cookies = self._parse_ck(self.sfsy_url)
            
            if not cookies.get('_login_user_id_'):
                # URL 格式，先访问获取 cookie
                resp = self.session.get(self.sfsy_url, timeout=15, allow_redirects=True)
                cookies = dict(self.session.cookies)
            
            # 设置 cookie
            for k, v in cookies.items():
                self.session.cookies.set(k, v)
            
            # 测试登录态 - 请求用户信息
            user_info = self._get_user_info()
            if user_info:
                self.user_info = user_info
                return True
            return False
        except Exception as e:
            print(f'[签到] 登录失败: {e}')
            return False
    
    def _common_post(self, path: str, body: dict = None):
        """通用 POST 请求"""
        timestamp = str(int(time.time() * 1000))
        token = "MCSMIMP2024"
        sys_code = "MCS-MIMP-CORE"
        sign_str = f"{token}{timestamp}{sys_code}"
        signature = hashlib.md5(sign_str.encode()).hexdigest()
        
        headers = {
            'Content-Type': 'application/json',
            'sysCode': sys_code,
            'timestamp': timestamp,
            'signature': signature,
            'platform': 'MINI_PROGRAM',
            'channel': 'mini-program',
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15'
        }
        
        resp = self.session.post(
            f'{self.API_BASE}/{path}',
            json=body or {},
            headers=headers,
            timeout=15
        )
        return resp.json() if resp.text else {}
    
    def _get_user_info(self):
        """获取用户信息"""
        try:
            data = self._common_post(
                "~memberIntegral~userInfoServices~personalInfoNew",
                {}
            )
            if data.get('success') or data.get('result'):
                result = data.get('obj') or data.get('data') or data.get('result') or {}
                return result
            return None
        except:
            return None
    
    def get_points(self) -> int:
        """获取积分"""
        try:
            data = self._common_post(
                "~memberCoupon~couponPoint~queryValidPointRules",
                {}
            )
            result = data.get('obj') or data.get('data') or data.get('result') or {}
            if isinstance(result, dict):
                return result.get('totalPoint') or result.get('validPoint') or 0
            return 0
        except:
            return 0
    
    def do_checkin(self) -> dict:
        """执行签到，返回结果详情"""
        results = []
        total_points = 0
        success_count = 0
        fail_count = 0
        
        # 签到任务列表
        tasks = [
            ("签到", "~memberIntegral~integralTask~signInV2", {}),
            ("浏览商品", "~memberIntegral~integralTask~browseGoodsFinish", {"taskCode": "LLSP001"}),
            ("浏览首页", "~memberIntegral~integralTask~browseHomeFinish", {"taskCode": "LLSY001"}),
            ("浏览签到页", "~memberIntegral~integralTask~browseSignFinish", {"taskCode": "LLQD001"}),
        ]
        
        for name, path, body in tasks:
            try:
                data = self._common_post(path, body)
                success = data.get('success') or data.get('result') or data.get('code') == 0
                point = data.get('integral') or data.get('point') or data.get('score') or 0
                msg = data.get('msg') or data.get('message') or ''
                
                if success or '成功' in msg or '已完成' in msg:
                    success_count += 1
                    total_points += point if isinstance(point, int) else 0
                    results.append(f"✅ {name}: +{point}积分" if point else f"✅ {name}")
                else:
                    fail_count += 1
                    results.append(f"❌ {name}: {msg[:20] if msg else '失败'}")
            except Exception as e:
                fail_count += 1
                results.append(f"❌ {name}: 异常")
        
        # 获取当前积分
        self.points = self.get_points()
        
        return {
            'success': success_count > 0,
            'success_count': success_count,
            'fail_count': fail_count,
            'total_points': total_points,
            'current_points': self.points,
            'details': results,
            'phone': get_phone_from_url(self.sfsy_url)
        }


# ==================== 多渠道推送 ====================
class Notifier:
    """多渠道消息推送"""
    
    def __init__(self):
        self.channels = []
        
        if Config.WXPUSHER_APP_TOKEN:
            self.channels.append('wxpusher')
        if Config.WECOM_WEBHOOK:
            self.channels.append('wecom')
        if Config.DINGTALK_WEBHOOK:
            self.channels.append('dingtalk')
        if Config.FEISHU_WEBHOOK:
            self.channels.append('feishu')
    
    def send(self, title: str, content: str, uid: str = None):
        """发送消息到所有已配置的渠道"""
        results = {}
        
        if 'wxpusher' in self.channels:
            results['wxpusher'] = self._send_wxpusher(title, content, uid)
        if 'wecom' in self.channels:
            results['wecom'] = self._send_wecom(title, content)
        if 'dingtalk' in self.channels:
            results['dingtalk'] = self._send_dingtalk(title, content)
        if 'feishu' in self.channels:
            results['feishu'] = self._send_feishu(title, content)
        
        return results
    
    def _send_wxpusher(self, title: str, content: str, uid: str = None) -> bool:
        """WxPusher 推送"""
        try:
            uids = []
            if uid:
                uids = [uid]
            elif Config.WXPUSHER_UIDS:
                uids = [u.strip() for u in Config.WXPUSHER_UIDS.split(',') if u.strip()]
            
            topic_ids = []
            if Config.WXPUSHER_TOPIC_IDS:
                topic_ids = [t.strip() for t in Config.WXPUSHER_TOPIC_IDS.split(',') if t.strip()]
            
            if not uids and not topic_ids:
                return False
            
            full_content = f"{title}\n\n{content}"
            
            payload = {
                'appToken': Config.WXPUSHER_APP_TOKEN,
                'content': full_content,
                'summary': title[:30],
                'contentType': 1,
            }
            if uids:
                payload['uids'] = uids
            if topic_ids:
                payload['topicIds'] = topic_ids
            
            resp = requests.post(
                'https://wxpusher.zjiecode.com/api/send/message',
                json=payload,
                timeout=10
            )
            return resp.json().get('code') == 1000
        except Exception as e:
            print(f'[WxPusher] 发送失败: {e}')
            return False
    
    def _send_wecom(self, title: str, content: str) -> bool:
        """企业微信群机器人"""
        try:
            quote_content = content.replace('\n', '\n> ')
            markdown = f"### {title}\n\n> {quote_content}"
            resp = requests.post(
                Config.WECOM_WEBHOOK,
                json={
                    'msgtype': 'markdown',
                    'markdown': {'content': markdown}
                },
                timeout=10
            )
            return resp.json().get('errcode') == 0
        except Exception as e:
            print(f'[企业微信] 发送失败: {e}')
            return False
    
    def _send_dingtalk(self, title: str, content: str) -> bool:
        """钉钉群机器人"""
        try:
            import base64
            import hmac
            import hashlib
            import urllib.parse
            
            url = Config.DINGTALK_WEBHOOK
            
            if Config.DINGTALK_SECRET:
                timestamp = str(round(time.time() * 1000))
                secret_enc = Config.DINGTALK_SECRET.encode('utf-8')
                string_to_sign = f'{timestamp}\n{Config.DINGTALK_SECRET}'
                string_to_sign_enc = string_to_sign.encode('utf-8')
                hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
                sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
                url = f'{url}&timestamp={timestamp}&sign={sign}'
            
            text = f"{title}\n\n{content}"
            resp = requests.post(
                url,
                json={
                    'msgtype': 'text',
                    'text': {'content': text}
                },
                timeout=10
            )
            return resp.json().get('errcode') == 0
        except Exception as e:
            print(f'[钉钉] 发送失败: {e}')
            return False
    
    def _send_feishu(self, title: str, content: str) -> bool:
        """飞书群机器人"""
        try:
            text = f"{title}\n\n{content}"
            resp = requests.post(
                Config.FEISHU_WEBHOOK,
                json={
                    'msg_type': 'text',
                    'content': {'text': text}
                },
                timeout=10
            )
            return resp.json().get('code') == 0
        except Exception as e:
            print(f'[飞书] 发送失败: {e}')
            return False


# ==================== WxPusher 消息接收 ====================
class WxPusherReceiver:
    """WxPusher 消息接收（轮询）"""
    
    def __init__(self, app_token: str, admin_uids: str = ''):
        self.app_token = app_token
        self.admin_uids = [u.strip() for u in admin_uids.split(',') if u.strip()]
        self.last_msg_id = 0
    
    def is_admin(self, uid: str) -> bool:
        if not self.admin_uids:
            return True
        return uid in self.admin_uids
    
    def get_new_messages(self):
        """获取新消息"""
        try:
            resp = requests.get(
                'https://wxpusher.zjiecode.com/api/fun/wxuser/messages',
                params={'appToken': self.app_token, 'page': 1, 'pageSize': 20},
                timeout=10
            )
            data = resp.json()
            if data.get('code') != 1000:
                return []
            
            records = data.get('data', {}).get('records', [])
            new_msgs = []
            
            for msg in records:
                msg_id = msg.get('id', 0)
                if msg_id > self.last_msg_id:
                    new_msgs.append(msg)
            
            if new_msgs:
                self.last_msg_id = max(m.get('id', 0) for m in new_msgs)
            
            new_msgs.sort(key=lambda x: x.get('id', 0))
            return new_msgs
        except Exception as e:
            print(f'[WxPusher] 获取消息失败: {e}')
            return []
    
    def init_last_id(self):
        """初始化最后消息ID（跳过历史消息）"""
        try:
            resp = requests.get(
                'https://wxpusher.zjiecode.com/api/fun/wxuser/messages',
                params={'appToken': self.app_token, 'page': 1, 'pageSize': 5},
                timeout=10
            )
            data = resp.json()
            if data.get('code') == 1000:
                records = data.get('data', {}).get('records', [])
                if records:
                    self.last_msg_id = max(m.get('id', 0) for m in records)
        except:
            pass


# ==================== 命令处理器 ====================
class CommandHandler:
    """命令处理器"""
    
    def __init__(self, ql: QingLong, notifier: Notifier):
        self.ql = ql
        self.notifier = notifier
    
    def handle(self, text: str, uid: str = None) -> str:
        """处理命令，返回回复内容"""
        text = text.strip()
        if not text:
            return self._help()
        
        # 解析命令
        parts = text.split(None, 1)
        cmd = parts[0].lower()
        args = parts[1].strip() if len(parts) > 1 else ''
        
        # 命令映射
        commands = {
            '帮助': self._help,
            'help': self._help,
            '?': self._help,
            '？': self._help,
            '列表': self._list,
            'list': self._list,
            'ls': self._list,
            '添加': lambda: self._add(args),
            'add': lambda: self._add(args),
            '更新': lambda: self._add(args),
            '替换': lambda: self._replace(args),
            'replace': lambda: self._replace(args),
            'set': lambda: self._replace(args),
            '删除': lambda: self._delete(args),
            'del': lambda: self._delete(args),
            'remove': lambda: self._delete(args),
            '测试': lambda: self._test(args),
            'test': lambda: self._test(args),
            '签到': self._checkin,
            'checkin': self._checkin,
            'sign': self._checkin,
            '积分': self._points,
            'points': self._points,
            '状态': self._status,
            'status': self._status,
            '版本': self._version,
            'version': self._version,
        }
        
        # 直接发送 URL/CK → 添加账号
        if parse_sfsy_url(text):
            return self._add(text)
        
        handler = commands.get(cmd)
        if handler:
            try:
                return handler()
            except Exception as e:
                return f'❌ 命令执行失败: {str(e)}'
        
        return f'❓ 未识别的命令：{cmd}\n发送「帮助」查看可用命令'
    
    def _help(self) -> str:
        return """📖 顺丰签到机器人 - 使用帮助

📋 【账号管理】
添加 + URL/CK   → 追加账号
替换 + URL/CK   → 全量替换
删除 + 手机号   → 删除指定账号
列表            → 查看所有账号
测试            → 测试所有账号有效性

🔔 【签到功能】
签到            → 立即执行签到
积分            → 查询当前积分
状态            → 查看系统状态

ℹ️ 【其他】
版本            → 查看版本号
帮助            → 查看帮助

💡 直接发送 sfsyUrl 或 CK 即可添加账号"""
    
    def _version(self) -> str:
        return f"📦 顺丰签到机器人 v{VERSION}"
    
    def _status(self) -> str:
        urls = self.ql.get_urls()
        channels = self.notifier.channels
        channel_names = {
            'wxpusher': 'WxPusher',
            'wecom': '企业微信',
            'dingtalk': '钉钉',
            'feishu': '飞书'
        }
        active_channels = [channel_names.get(c, c) for c in channels]
        
        lines = [
            "📊 系统状态",
            "",
            f"账号数量: {len(urls)} 个",
            f"推送渠道: {', '.join(active_channels) if active_channels else '无'}",
            f"轮询间隔: {Config.POLL_INTERVAL} 秒",
            f"签到时间: 每天 {Config.CHECKIN_HOUR:02d}:{Config.CHECKIN_MINUTE:02d}",
            f"版本: v{VERSION}",
        ]
        return '\n'.join(lines)
    
    def _list(self) -> str:
        urls = self.ql.get_urls()
        if not urls:
            return '📋 当前没有任何账号'
        
        lines = [f'📋 当前共 {len(urls)} 个账号：', '']
        for i, url in enumerate(urls, 1):
            phone = get_phone_from_url(url)
            lines.append(f'{i}. {mask_phone(phone)}')
        return '\n'.join(lines)
    
    def _add(self, text: str) -> str:
        url = parse_sfsy_url(text)
        if not url:
            return '❌ 未识别到有效的 sfsyUrl/CK\n请检查格式是否正确'
        
        urls = self.ql.get_urls()
        phone = get_phone_from_url(url)
        
        # 按手机号去重
        for existing in urls:
            if get_phone_from_url(existing) == phone and phone:
                return f'⚠️  账号已存在（{mask_phone(phone)}），无需重复添加'
        
        urls.append(url)
        success = self.ql.set_urls(urls)
        if success:
            return f'✅ 已添加账号：{mask_phone(phone)}\n当前共 {len(urls)} 个账号'
        return '❌ 添加失败，请检查青龙连接'
    
    def _replace(self, text: str) -> str:
        url = parse_sfsy_url(text)
        if not url:
            return '❌ 未识别到有效的 sfsyUrl/CK'
        
        phone = get_phone_from_url(url)
        success = self.ql.set_urls([url])
        if success:
            return f'✅ 已全量替换为 1 个账号\n{mask_phone(phone)}'
        return '❌ 替换失败，请检查青龙连接'
    
    def _delete(self, phone_to_delete: str) -> str:
        phone_to_delete = phone_to_delete.strip()
        if not phone_to_delete:
            return '❌ 请提供要删除的手机号\n示例：删除 13800138000'
        
        urls = self.ql.get_urls()
        new_urls = []
        deleted = 0
        
        for url in urls:
            if get_phone_from_url(url) != phone_to_delete:
                new_urls.append(url)
            else:
                deleted += 1
        
        if deleted == 0:
            return f'❌ 未找到手机号为 {phone_to_delete} 的账号'
        
        success = self.ql.set_urls(new_urls)
        if success:
            return f'✅ 已删除 {deleted} 个账号（{mask_phone(phone_to_delete)}）\n剩余 {len(new_urls)} 个账号'
        return '❌ 删除失败，请检查青龙连接'
    
    def _test(self, text: str = '') -> str:
        urls = self.ql.get_urls()
        if not urls:
            return '📋 当前没有任何账号'
        
        lines = [f'🧪 账号有效性测试（共 {len(urls)} 个）', '']
        valid = 0
        invalid = 0
        
        for i, url in enumerate(urls, 1):
            phone = get_phone_from_url(url)
            checker = SFCheckin(url)
            ok = checker.login()
            
            if ok:
                valid += 1
                lines.append(f'{i}. ✅ {mask_phone(phone)}')
            else:
                invalid += 1
                lines.append(f'{i}. ❌ {mask_phone(phone)} - 已失效')
        
        lines.extend(['', f'✅ 有效: {valid} 个', f'❌ 失效: {invalid} 个'])
        return '\n'.join(lines)
    
    def _checkin(self) -> str:
        urls = self.ql.get_urls()
        if not urls:
            return '📋 当前没有任何账号'
        
        lines = [f'🔔 立即签到（共 {len(urls)} 个账号）', '']
        total_gain = 0
        success_count = 0
        
        for i, url in enumerate(urls, 1):
            phone = get_phone_from_url(url)
            checker = SFCheckin(url)
            
            if not checker.login():
                lines.append(f'{i}. ❌ {mask_phone(phone)} - 登录失效')
                continue
            
            result = checker.do_checkin()
            success_count += 1
            total_gain += result.get('total_points', 0)
            
            lines.append(f'{i}. {mask_phone(phone)}: +{result["total_points"]}分 (当前{result["current_points"]}分)')
        
        lines.extend([
            '',
            f'📊 成功: {success_count}/{len(urls)}',
            f'🎁 共获得: {total_gain} 积分',
        ])
        return '\n'.join(lines)
    
    def _points(self) -> str:
        urls = self.ql.get_urls()
        if not urls:
            return '📋 当前没有任何账号'
        
        lines = [f'💰 积分查询（共 {len(urls)} 个账号）', '']
        total = 0
        valid = 0
        
        for i, url in enumerate(urls, 1):
            phone = get_phone_from_url(url)
            checker = SFCheckin(url)
            
            if checker.login():
                points = checker.get_points()
                total += points
                valid += 1
                lines.append(f'{i}. {mask_phone(phone)}: {points} 积分')
            else:
                lines.append(f'{i}. ❌ {mask_phone(phone)} - 已失效')
        
        lines.extend(['', f'📊 有效账号: {valid}/{len(urls)}', f'💰 总积分: {total}'])
        return '\n'.join(lines)


# ==================== 定时签到调度器 ====================
class Scheduler:
    """简单的定时任务调度器"""
    
    def __init__(self, hour: int, minute: int):
        self.hour = hour
        self.minute = minute
        self.last_run_date = None
    
    def should_run(self) -> bool:
        """判断是否应该执行签到"""
        now = datetime.now()
        today = now.date()
        
        # 今天已经运行过了
        if self.last_run_date == today:
            return False
        
        # 到达指定时间
        if now.hour > self.hour or (now.hour == self.hour and now.minute >= self.minute):
            self.last_run_date = today
            return True
        
        return False


# ==================== 主程序 ====================
def main():
    print("=" * 60)
    print(f"🤖 顺丰签到机器人 v{VERSION}")
    print("=" * 60)
    
    # 初始化
    ql = QingLong(Config.QL_URL, Config.QL_CLIENT_ID, Config.QL_CLIENT_SECRET)
    notifier = Notifier()
    handler = CommandHandler(ql, notifier)
    scheduler = Scheduler(Config.CHECKIN_HOUR, Config.CHECKIN_MINUTE)
    
    # 测试青龙连接
    print("🔍 测试青龙连接...")
    if not ql.test_connection():
        print("❌ 青龙连接失败，请检查配置")
        sys.exit(1)
    
    urls = ql.get_urls()
    print(f"✅ 青龙连接正常，当前 {len(urls)} 个账号")
    
    # 显示已配置的推送渠道
    channel_names = {
        'wxpusher': 'WxPusher',
        'wecom': '企业微信',
        'dingtalk': '钉钉',
        'feishu': '飞书'
    }
    active = [channel_names.get(c, c) for c in notifier.channels]
    print(f"📨 推送渠道: {', '.join(active) if active else '无'}")
    
    # 初始化 WxPusher 接收器
    receiver = None
    if Config.WXPUSHER_APP_TOKEN:
        receiver = WxPusherReceiver(Config.WXPUSHER_APP_TOKEN, Config.ADMIN_UIDS)
        receiver.init_last_id()
        print(f"💬 WxPusher 交互已启用")
    
    print()
    print(f"⏰ 签到时间: 每天 {Config.CHECKIN_HOUR:02d}:{Config.CHECKIN_MINUTE:02d}")
    print(f"⏱️  轮询间隔: {Config.POLL_INTERVAL} 秒")
    print("🚀 服务启动...")
    print("=" * 60)
    print()
    
    # 启动通知
    if notifier.channels:
        status_text = handler._status()
        notifier.send("🤖 顺丰签到机器人已启动", status_text)
    
    # 主循环
    while True:
        try:
            # 1. 定时签到
            if scheduler.should_run():
                print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 执行每日签到...")
                result = handler._checkin()
                if notifier.channels:
                    notifier.send("🔔 每日签到完成", result)
                print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 签到完成")
            
            # 2. 处理 WxPusher 消息
            if receiver:
                new_msgs = receiver.get_new_messages()
                for msg in new_msgs:
                    uid = msg.get('uid', '')
                    content = msg.get('content', '').strip()
                    create_time = msg.get('createTime', '')
                    
                    if not content:
                        continue
                    
                    # 权限检查
                    if not receiver.is_admin(uid):
                        receiver._send_wxpusher_reply(uid, '❌ 你没有操作权限')
                        continue
                    
                    print(f"[{create_time}] 收到命令: {content[:30]}")
                    
                    # 处理命令
                    reply = handler.handle(content, uid)
                    
                    # 回复消息
                    if reply:
                        notifier.send("顺丰签到机器人", reply, uid)
                        print(f"  ↳ 已回复: {reply[:30]}...")
            
            time.sleep(Config.POLL_INTERVAL)
        
        except KeyboardInterrupt:
            print("\n👋 服务已停止")
            break
        except Exception as e:
            print(f'主循环异常: {e}')
            time.sleep(Config.POLL_INTERVAL)


if __name__ == '__main__':
    main()
