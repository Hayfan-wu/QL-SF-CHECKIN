"""
顺丰速运 sfsyUrl 远程更新（WxPusher 版）
通过微信发送消息到 WxPusher，自动更新青龙面板的 sfsyUrl

使用方法：
  1. 配置环境变量（青龙地址、WxPusher token）
  2. 运行脚本：python sf_wxpusher_update.py
  3. 在微信里给 WxPusher 发送 sfsyUrl/CK
  4. 脚本自动检测并更新到青龙

支持的消息格式：
  - 直接发送 sfsyUrl/CK 字符串 → 追加到现有账号
  - 发送 "更新" + URL → 追加账号
  - 发送 "替换" + URL → 全量替换
  - 发送 "删除" + 手机号 → 删除指定账号
  - 发送 "列表" → 查看当前账号列表
  - 发送 "帮助" → 查看使用说明
"""

import os
import time
import json
import hashlib
from datetime import datetime
from urllib.parse import unquote

import requests
requests.packages.urllib3.disable_warnings()


# ==================== 配置 ====================
class Config:
    """配置类"""
    # 青龙面板配置
    QL_URL = os.getenv('QL_URL', '')
    QL_CLIENT_ID = os.getenv('QL_CLIENT_ID', '')
    QL_CLIENT_SECRET = os.getenv('QL_CLIENT_SECRET', '')
    
    # WxPusher 配置
    WXPUSHER_APP_TOKEN = os.getenv('WXPUSHER_APP_TOKEN', '')
    WXPUSHER_UIDS = os.getenv('WXPUSHER_UIDS', '')  # 允许操作的用户UID，多个用逗号分隔
    
    # 轮询间隔（秒）
    POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', '30'))
    
    # 环境变量名
    ENV_NAME = os.getenv('ENV_NAME', 'sfsyUrl')


# ==================== 青龙面板操作 ====================
class QingLong:
    """青龙面板 API"""
    
    def __init__(self, url: str, client_id: str, client_secret: str):
        self.url = url.rstrip('/')
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self.token_expire = 0
    
    def _get_token(self) -> bool:
        """获取 token"""
        try:
            resp = requests.post(
                f'{self.url}/open/auth/token',
                params={
                    'client_id': self.client_id,
                    'client_secret': self.client_secret
                },
                timeout=10
            )
            data = resp.json()
            if data.get('code') == 200:
                self.token = data['data']['token']
                self.token_expire = time.time() + data['data'].get('expires_in', 7200) - 60
                return True
            return False
        except Exception as e:
            print(f'获取青龙token失败: {e}')
            return False
    
    def _ensure_token(self) -> bool:
        """确保 token 有效"""
        if not self.token or time.time() > self.token_expire:
            return self._get_token()
        return True
    
    def _headers(self):
        return {'Authorization': f'Bearer {self.token}'}
    
    def get_env(self, name: str):
        """获取环境变量"""
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
            print(f'获取环境变量失败: {e}')
            return None
    
    def update_env(self, env_id: int, name: str, value: str, remarks: str = '') -> bool:
        """更新环境变量"""
        if not self._ensure_token():
            return False
        
        try:
            resp = requests.put(
                f'{self.url}/open/envs',
                headers=self._headers(),
                json={
                    'id': env_id,
                    'name': name,
                    'value': value,
                    'remarks': remarks
                },
                timeout=10
            )
            data = resp.json()
            return data.get('code') == 200
        except Exception as e:
            print(f'更新环境变量失败: {e}')
            return False
    
    def add_env(self, name: str, value: str, remarks: str = '') -> bool:
        """新增环境变量"""
        if not self._ensure_token():
            return False
        
        try:
            resp = requests.post(
                f'{self.url}/open/envs',
                headers=self._headers(),
                json=[{
                    'name': name,
                    'value': value,
                    'remarks': remarks
                }],
                timeout=10
            )
            data = resp.json()
            return data.get('code') == 200
        except Exception as e:
            print(f'新增环境变量失败: {e}')
            return False
    
    def get_sfsy_urls(self):
        """获取 sfsyUrl 列表"""
        env = self.get_env(Config.ENV_NAME)
        if not env:
            return []
        value = env.get('value', '')
        return [u.strip() for u in value.split('&') if u.strip()]
    
    def set_sfsy_urls(self, urls, remarks: str = '') -> bool:
        """设置 sfsyUrl（全量替换）"""
        env = self.get_env(Config.ENV_NAME)
        value = '&'.join(urls)
        if not remarks:
            remarks = f'共{len(urls)}个账号 - 远程更新'
        
        if env:
            return self.update_env(env['id'], Config.ENV_NAME, value, remarks)
        else:
            return self.add_env(Config.ENV_NAME, value, remarks)


# ==================== WxPusher 操作 ====================
class WxPusher:
    """WxPusher 消息收发"""
    
    BASE_URL = 'https://wxpusher.zjiecode.com/api'
    
    def __init__(self, app_token: str, allowed_uids: str = ''):
        self.app_token = app_token
        self.allowed_uids = [u.strip() for u in allowed_uids.split(',') if u.strip()]
        self.last_msg_id = 0
    
    def send_message(self, uid: str, content: str, summary: str = '') -> bool:
        """发送消息给指定用户"""
        try:
            resp = requests.post(
                f'{self.BASE_URL}/send/message',
                json={
                    'appToken': self.app_token,
                    'content': content,
                    'summary': summary or content[:30],
                    'contentType': 1,
                    'uids': [uid]
                },
                timeout=10
            )
            data = resp.json()
            return data.get('code') == 1000
        except Exception as e:
            print(f'发送消息失败: {e}')
            return False
    
    def get_messages(self):
        """获取最新消息列表"""
        try:
            resp = requests.get(
                f'{self.BASE_URL}/fun/wxuser/messages',
                params={
                    'appToken': self.app_token,
                    'page': 1,
                    'pageSize': 20
                },
                timeout=10
            )
            data = resp.json()
            if data.get('code') == 1000:
                return data.get('data', {}).get('records', [])
            return []
        except Exception as e:
            print(f'获取消息失败: {e}')
            return []
    
    def get_new_messages(self):
        """获取新消息（上次处理之后的）"""
        all_msgs = self.get_messages()
        new_msgs = []
        
        for msg in all_msgs:
            msg_id = msg.get('id', 0)
            if msg_id > self.last_msg_id:
                new_msgs.append(msg)
        
        if new_msgs:
            # 更新最后处理的消息ID（取最大的）
            self.last_msg_id = max(m.get('id', 0) for m in new_msgs)
        
        # 按时间正序排列（先处理旧的）
        new_msgs.sort(key=lambda x: x.get('id', 0))
        return new_msgs
    
    def is_allowed(self, uid: str) -> bool:
        """检查用户是否有权限"""
        if not self.allowed_uids:
            return True  # 没配置则所有用户都可以
        return uid in self.allowed_uids


# ==================== sfsyUrl 解析 ====================
def parse_sfsy_url(text: str):
    """从文本中提取 sfsyUrl/CK"""
    text = text.strip()
    
    # 尝试 CK 格式
    if '_login_mobile_=' in text and '_login_user_id_=' in text:
        import re
        # 提取包含登录态的完整 CK（sessionId + _login_mobile_ + _login_user_id_）
        pattern = r'(?:sessionId=[^;&\s]+;?)?_login_mobile_=[^;&\s]+;?_login_user_id_=[^;&\s]+'
        match = re.search(pattern, text)
        if match:
            result = match.group(0)
            # 确保格式正确（用分号分隔，去掉多余分号）
            result = result.strip(';')
            return result
    
    # 尝试 URL 格式
    if 'sf-express.com' in text:
        import re
        match = re.search(r'https?://[^\s]+sf-express\.com[^\s]*', text)
        if match:
            return match.group(0)
    
    return None


def get_phone_from_url(url: str) -> str:
    """从 URL/CK 中提取手机号"""
    try:
        decoded = unquote(url)
        if '_login_mobile_=' in decoded:
            import re
            match = re.search(r'_login_mobile_=([^;&\s]+)', decoded)
            if match:
                return match.group(1)
        elif 'mobile=' in decoded:
            from urllib.parse import parse_qs, urlparse
            parsed = urlparse(decoded)
            params = parse_qs(parsed.query)
            return params.get('mobile', [''])[0]
    except:
        pass
    return ''


def mask_phone(phone: str) -> str:
    """手机号脱敏"""
    if len(phone) >= 11:
        return phone[:3] + '****' + phone[7:]
    return phone or '未知'


# ==================== 消息处理 ====================
def handle_message(msg: dict, ql: QingLong, pusher: WxPusher):
    """处理单条消息"""
    uid = msg.get('uid', '')
    content = msg.get('content', '').strip()
    create_time = msg.get('createTime', '')
    
    if not uid or not content:
        return
    
    # 检查权限
    if not pusher.is_allowed(uid):
        pusher.send_message(uid, '❌ 你没有操作权限')
        return
    
    print(f'[{create_time}] 收到消息 (UID: {uid[:8]}...): {content[:50]}')
    
    # 解析命令
    cmd = content.split()[0] if content else ''
    rest = content[len(cmd):].strip() if cmd else content
    
    response = ''
    
    if cmd in ['帮助', 'help', '?', '？']:
        # 帮助
        response = '''📖 使用帮助

直接发送 sfsyUrl/CK → 追加账号
更新 + URL → 追加账号
替换 + URL → 全量替换所有账号
删除 + 手机号 → 删除指定账号
列表 → 查看当前所有账号
帮助 → 查看帮助

示例：
更新 sessionId=xxx;_login_mobile_=13800138000;_login_user_id_=xxx
删除 13800138000
列表'''
    
    elif cmd in ['列表', 'list', 'ls']:
        # 查看账号列表
        urls = ql.get_sfsy_urls()
        if not urls:
            response = '📋 当前没有任何账号'
        else:
            lines = [f'📋 当前共 {len(urls)} 个账号：', '']
            for i, url in enumerate(urls, 1):
                phone = get_phone_from_url(url)
                lines.append(f'{i}. {mask_phone(phone)}')
            response = '\n'.join(lines)
    
    elif cmd in ['删除', 'del', 'remove']:
        # 删除账号
        phone_to_delete = rest.strip()
        if not phone_to_delete:
            response = '❌ 请提供要删除的手机号\n示例：删除 13800138000'
        else:
            urls = ql.get_sfsy_urls()
            new_urls = []
            deleted_count = 0
            for url in urls:
                phone = get_phone_from_url(url)
                if phone != phone_to_delete:
                    new_urls.append(url)
                else:
                    deleted_count += 1
            
            if deleted_count == 0:
                response = f'❌ 未找到手机号为 {phone_to_delete} 的账号'
            else:
                success = ql.set_sfsy_urls(new_urls)
                if success:
                    response = f'✅ 已删除 {deleted_count} 个账号（{mask_phone(phone_to_delete)}）\n剩余 {len(new_urls)} 个账号'
                else:
                    response = '❌ 删除失败，请检查青龙连接'
    
    elif cmd in ['替换', 'replace', 'set']:
        # 全量替换
        url = parse_sfsy_url(rest)
        if not url:
            response = '❌ 未识别到有效的 sfsyUrl/CK\n请检查格式是否正确'
        else:
            phone = get_phone_from_url(url)
            success = ql.set_sfsy_urls([url])
            if success:
                response = f'✅ 已全量替换为 1 个账号\n{mask_phone(phone)}'
            else:
                response = '❌ 更新失败，请检查青龙连接'
    
    elif cmd in ['更新', '追加', 'add', 'update', '新增']:
        # 追加账号
        url = parse_sfsy_url(rest)
        if not url:
            response = '❌ 未识别到有效的 sfsyUrl/CK\n请检查格式是否正确'
        else:
            urls = ql.get_sfsy_urls()
            phone = get_phone_from_url(url)
            
            # 检查是否已存在（按手机号去重）
            exists = False
            for existing_url in urls:
                existing_phone = get_phone_from_url(existing_url)
                if existing_phone and existing_phone == phone:
                    exists = True
                    break
            
            if exists:
                response = f'⚠️  账号已存在（{mask_phone(phone)}），无需重复添加'
            else:
                urls.append(url)
                success = ql.set_sfsy_urls(urls)
                if success:
                    response = f'✅ 已添加账号：{mask_phone(phone)}\n当前共 {len(urls)} 个账号'
                else:
                    response = '❌ 更新失败，请检查青龙连接'
    
    else:
        # 直接发送 URL → 尝试追加
        url = parse_sfsy_url(content)
        if url:
            urls = ql.get_sfsy_urls()
            phone = get_phone_from_url(url)
            
            exists = False
            for existing_url in urls:
                existing_phone = get_phone_from_url(existing_url)
                if existing_phone and existing_phone == phone:
                    exists = True
                    break
            
            if exists:
                response = f'⚠️  账号已存在（{mask_phone(phone)}），无需重复添加'
            else:
                urls.append(url)
                success = ql.set_sfsy_urls(urls)
                if success:
                    response = f'✅ 已添加账号：{mask_phone(phone)}\n当前共 {len(urls)} 个账号\n（发送「帮助」查看更多命令）'
                else:
                    response = '❌ 更新失败，请检查青龙连接'
        else:
            response = '❓ 未识别的命令或无效的 URL\n发送「帮助」查看使用说明'
    
    # 回复消息
    if response:
        pusher.send_message(uid, response)


# ==================== 主程序 ====================
def main():
    print("=" * 60)
    print("📨 顺丰 sfsyUrl 远程更新服务（WxPusher版）")
    print("=" * 60)
    
    config = Config()
    
    # 检查配置
    if not config.QL_URL or not config.QL_CLIENT_ID or not config.QL_CLIENT_SECRET:
        print("❌ 青龙面板配置不完整")
        print("   请设置环境变量：QL_URL, QL_CLIENT_ID, QL_CLIENT_SECRET")
        return
    
    if not config.WXPUSHER_APP_TOKEN:
        print("❌ WxPusher AppToken 未配置")
        print("   请设置环境变量：WXPUSHER_APP_TOKEN")
        return
    
    # 初始化
    ql = QingLong(config.QL_URL, config.QL_CLIENT_ID, config.QL_CLIENT_SECRET)
    pusher = WxPusher(config.WXPUSHER_APP_TOKEN, config.WXPUSHER_UIDS)
    
    # 测试青龙连接
    print("🔍 测试青龙连接...")
    test_env = ql.get_env(config.ENV_NAME)
    if test_env is not None:
        urls = ql.get_sfsy_urls()
        print(f"✅ 青龙连接正常，当前 {len(urls)} 个账号")
    else:
        print("❌ 青龙连接失败，请检查配置")
        return
    
    # 初始化消息 ID（跳过启动前的消息）
    msgs = pusher.get_messages()
    if msgs:
        pusher.last_msg_id = max(m.get('id', 0) for m in msgs)
        print(f"📨 已跳过 {len(msgs)} 条历史消息")
    
    print()
    print(f"⏰ 轮询间隔：{config.POLL_INTERVAL} 秒")
    print("💬 发送「帮助」到 WxPusher 查看使用说明")
    print("🚀 服务启动，等待消息...")
    print()
    
    # 主循环
    while True:
        try:
            new_msgs = pusher.get_new_messages()
            for msg in new_msgs:
                try:
                    handle_message(msg, ql, pusher)
                except Exception as e:
                    print(f'处理消息出错: {e}')
            
            time.sleep(config.POLL_INTERVAL)
        
        except KeyboardInterrupt:
            print("\n👋 服务已停止")
            break
        except Exception as e:
            print(f'主循环出错: {e}')
            time.sleep(config.POLL_INTERVAL)


if __name__ == '__main__':
    main()
