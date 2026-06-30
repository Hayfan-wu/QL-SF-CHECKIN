"""
顺丰速运日常积分任务（APP端）
Author: 爱学习的呆子
Version: 2.0.0
Date: 2026-06-30

说明：精简版，仅保留APP端签到+任务+保活功能
"""

import hashlib
import json
import os
import time
from typing import Dict, List, Optional
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning

# 禁用SSL警告
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# ==================== 配置 ====================
CONCURRENT_NUM = int(os.getenv('SFBF', '1'))
if CONCURRENT_NUM > 20:
    CONCURRENT_NUM = 20
elif CONCURRENT_NUM < 1:
    CONCURRENT_NUM = 1

print_lock = Lock()


@dataclass
class Config:
    """全局配置"""
    APP_NAME: str = "顺丰速运"
    VERSION: str = "2.0.0"
    ENV_NAME: str = "sfsyUrl"
    PROXY_API_URL: str = os.getenv('SF_PROXY_API_URL', '')
    
    # API签名配置
    TOKEN: str = 'wwesldfs29aniversaryvdld29'
    SYS_CODE: str = 'MCS-MIMP-CORE'
    
    # 任务跳过列表
    SKIP_TASKS: List[str] = None
    
    # WxPusher 推送
    WXPUSHER_APP_TOKEN: str = os.getenv('WXPUSHER_APP_TOKEN', '')
    WXPUSHER_UIDS: str = os.getenv('WXPUSHER_UIDS', '')
    WXPUSHER_TOPIC_IDS: str = os.getenv('WXPUSHER_TOPIC_IDS', '')
    WXPUSHER_ONLY_EXPIRED: bool = os.getenv('WXPUSHER_ONLY_EXPIRED', 'true').lower() == 'true'
    
    # 保活模式
    SF_KEEPALIVE: bool = os.getenv('SF_KEEPALIVE', 'false').lower() == 'true'
    
    def __post_init__(self):
        if self.SKIP_TASKS is None:
            self.SKIP_TASKS = [
                '用行业模板寄件下单', '用积分兑任意礼品', '参与积分活动',
                '每月累计寄件', '完成每月任务', '去使用AI寄件',
                '寄一单国际件', '去新增一个收件偏好', '开通储值卡自动扣',
                '设置你的顺丰ID', '去使用AI小丰寄件',
            ]


# ==================== 日志 ====================
class Logger:
    """日志管理器"""
    
    ICONS = {
        'task_found': '🎯', 'task_skip': '⏭️', 'task_complete': '✅',
        'reward_get': '🎁', 'info': '📝', 'success': '✨',
        'error': '❌', 'warning': '⚠️', 'user': '👤', 'money': '💰',
    }
    
    def __init__(self):
        self.messages: List[str] = []
        self.current_account_msg: List[str] = []
        self.lock = Lock()
    
    def _print(self, msg: str):
        with print_lock:
            print(msg)
    
    def _log(self, icon: str, content: str):
        msg = f"{icon} {content}"
        self._print(msg)
        with self.lock:
            self.current_account_msg.append(msg)
            self.messages.append(msg)
    
    def task_found(self, name, status=2): self._log(self.ICONS['task_found'], f"发现任务: {name} (状态: {status})")
    def task_skip(self, name): self._log(self.ICONS['task_skip'], f"[{name}] 已跳过")
    def task_complete(self, name): self._log(self.ICONS['task_complete'], f"[{name}] 提交成功")
    def reward_get(self, name): self._log(self.ICONS['reward_get'], f"[{name}] 奖励领取成功")
    def info(self, msg): self._log(self.ICONS['info'], msg)
    def success(self, msg): self._log(self.ICONS['success'], msg)
    def error(self, msg): self._log(self.ICONS['error'], msg)
    def warning(self, msg): self._log(self.ICONS['warning'], msg)
    def user_info(self, phone): self._log(self.ICONS['user'], f"登录成功: {phone[:3]}****{phone[7:]}")
    def points_info(self, points, label="当前积分"): self._log(self.ICONS['money'], f"{label}: {points}")
    
    def reset_account(self):
        """重置当前账号消息"""
        with self.lock:
            self.current_account_msg = []
    
    def get_account_messages(self) -> str:
        with self.lock:
            return '\n'.join(self.current_account_msg)


# ==================== HTTP 客户端 ====================
class SFHttpClient:
    """顺丰API HTTP客户端"""
    
    BASE_URL = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/'
    
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.verify = False
        self.headers = {
            'Host': 'mcs-mimp-web.sf-express.com',
            'Content-Type': 'application/json',
            'platform': 'SFAPP',
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 mediaCode=SFEXPRESSAPP-iOS-ML',
            'channel': 'point240613',
            'Origin': 'https://mcs-mimp-web.sf-express.com',
        }
        self.proxy_manager = None
        if config.PROXY_API_URL:
            self.proxy_manager = ProxyManager(config)
            self._set_proxy()
    
    def _set_proxy(self):
        """设置代理"""
        if self.proxy_manager:
            proxy = self.proxy_manager.get_proxy()
            if proxy:
                self.session.proxies = {'http': f'http://{proxy}', 'https': f'http://{proxy}'}
    
    def _sign(self) -> Dict:
        """生成签名"""
        timestamp = str(int(time.time() * 1000))
        data = f'token={self.config.TOKEN}&timestamp={timestamp}&sysCode={self.config.SYS_CODE}'
        signature = hashlib.md5(data.encode()).hexdigest()
        return {
            'sysCode': self.config.SYS_CODE,
            'timestamp': timestamp,
            'signature': signature,
        }
    
    def request(self, path: str, data: Dict = None, retries: int = 3) -> Optional[Dict]:
        """发送请求
        
        Args:
            path: 接口路径（~开头的相对路径）
            data: 请求体
            retries: 重试次数
            
        Returns:
            响应JSON字典，失败返回None
        """
        url = self.BASE_URL + path
        headers = self.headers.copy()
        headers.update(self._sign())
        
        for attempt in range(retries):
            try:
                resp = self.session.post(url, headers=headers, json=data or {}, timeout=15)
                result = resp.json()
                return result
            except Exception as e:
                if attempt < retries - 1:
                    if self.proxy_manager:
                        self.proxy_manager.force_refresh()
                        self._set_proxy()
                    time.sleep(1)
                else:
                    return None
        return None
    
    def login(self, account_url: str) -> tuple[bool, str, str]:
        """登录
        
        Args:
            account_url: sfsyUrl 或 CK 格式字符串
            
        Returns:
            tuple[是否成功, userId, mobile]
        """
        user_id = ''
        mobile = ''
        
        # 解析 CK 格式（sessionId=xxx;_login_user_id_=xxx;_login_mobile_=xxx）
        if account_url.startswith('sessionId=') or ';_login_' in account_url:
            pairs = account_url.split(';')
            for pair in pairs:
                if '=' in pair:
                    key, val = pair.strip().split('=', 1)
                    if key == 'sessionId':
                        self.session.cookies.set('sessionId', val)
                        self.session.cookies.set('JSESSIONID', val)
                    elif key == '_login_user_id_':
                        user_id = val
                        self.session.cookies.set('_login_user_id_', val)
                    elif key == '_login_mobile_':
                        mobile = val
                        self.session.cookies.set('_login_mobile_', val)
        else:
            # URL 格式
            try:
                resp = self.session.get(account_url, timeout=15, headers=self.headers)
                for c in resp.cookies:
                    if c.name == '_login_user_id_':
                        user_id = c.value
                    elif c.name == '_login_mobile_':
                        mobile = c.value
            except:
                pass
        
        # 验证登录状态
        if user_id and mobile:
            return True, user_id, mobile
        return False, user_id, mobile


# ==================== 代理管理 ====================
class ProxyManager:
    """代理IP管理器"""
    
    def __init__(self, config: Config):
        self.config = config
        self.current_proxy = None
        self.last_refresh_time = 0
        self.min_refresh_interval = 3
    
    def get_proxy(self) -> Optional[str]:
        """获取代理"""
        if not self.config.PROXY_API_URL:
            return None
        if self.current_proxy and (time.time() - self.last_refresh_time) < self.min_refresh_interval:
            return self.current_proxy
        return self._refresh_proxy()
    
    def force_refresh(self) -> Optional[str]:
        """强制刷新代理"""
        return self._refresh_proxy()
    
    def _refresh_proxy(self) -> Optional[str]:
        """刷新代理"""
        try:
            resp = requests.get(self.config.PROXY_API_URL, timeout=10)
            text = resp.text.strip()
            if ':' in text and len(text) < 50:
                self.current_proxy = text
                self.last_refresh_time = time.time()
                return self.current_proxy
        except:
            pass
        return self.current_proxy


# ==================== 任务执行器 ====================
class TaskExecutor:
    """任务执行器"""
    
    def __init__(self, http: SFHttpClient, logger: Logger, config: Config, user_id: str):
        self.http = http
        self.logger = logger
        self.config = config
        self.user_id = user_id
        self.total_points = 0
        self.taskCode = ''
        self.taskType = ''
        self.taskCategory = ''
    
    def generate_device_id(self) -> str:
        """生成设备ID"""
        import random, string
        return ''.join(random.choices(string.ascii_letters + string.digits + '_-', k=50))
    
    # ---------- 签到 ----------
    
    def sign_in(self) -> tuple[bool, str]:
        """APP端签到（automaticSignFetchPackage 兼容性最好）
        
        Returns:
            tuple[是否成功, 错误信息]
        """
        path = '~memberNonactivity~integralTaskSignPlusService~automaticSignFetchPackage'
        data = {'comeFrom': 'vioin', 'channelFrom': 'WEIXIN'}
        
        resp = self.http.request(path, data)
        if resp and resp.get('success'):
            obj = resp.get('obj') or {}
            count_day = obj.get('countDay', '?')
            points = obj.get('integralTaskSignGood', [{}])
            point = points[0].get('point', 0) if points else 0
            self.logger.success(f"签到成功！连续签到 {count_day} 天，获得 {point} 积分")
            return True, ''
        
        error_msg = resp.get('errorMessage', '签到失败') if resp else '请求失败'
        if '今日已签到' in error_msg or '已签到' in error_msg:
            self.logger.info("今日已签到")
            return True, ''
        
        self.logger.error(f"签到失败: {error_msg}")
        return False, error_msg
    
    # ---------- 任务列表 ----------
    
    def get_task_list(self) -> List[Dict]:
        """获取任务列表
        
        Returns:
            任务列表
        """
        path = '~memberNonactivity~integralTaskStrategyService~queryPointTaskAndSignFromES'
        all_tasks = []
        device_id = self.generate_device_id()
        
        # 尝试多个 channelType
        for channel_type in ['1', '2', '3', '4']:
            data = {'channelType': channel_type, 'deviceId': device_id}
            resp = self.http.request(path, data)
            
            if resp and resp.get('success') and resp.get('obj'):
                obj = resp['obj']
                if channel_type == '1':
                    self.total_points = obj.get('totalPoint', 0)
                
                tasks = obj.get('taskTitleLevels', [])
                for task in tasks:
                    task['_channel'] = channel_type
                    all_tasks.append(task)
            time.sleep(0.5)
        
        return all_tasks
    
    # ---------- 任务执行 ----------
    
    def _set_task_attrs(self, task: Dict):
        """从任务中提取关键属性"""
        self.taskCode = task.get('taskCode', '')
        self.taskType = task.get('taskType', '')
        self.taskCategory = task.get('taskCategory', '')
    
    def _extract_task_id_from_url(self, url: str) -> str:
        """从URL中提取任务ID"""
        if 'taskId=' in url:
            start = url.find('taskId=') + 7
            end = url.find('&', start)
            if end == -1:
                end = len(url)
            return url[start:end]
        return ''
    
    def execute_task(self) -> bool:
        """执行任务（完成任务）"""
        if not self.taskCode:
            return False
        
        path = '~memberNonactivity~integralTaskStrategyService~completeTask'
        data = {'taskCode': self.taskCode}
        
        resp = self.http.request(path, data)
        if resp and resp.get('success'):
            return True
        
        # 换一个接口试试
        path2 = '~memberNonactivity~integralTaskService~completeTask'
        resp2 = self.http.request(path2, data)
        if resp2 and resp2.get('success'):
            return True
        
        return False
    
    def receive_task_reward(self) -> bool:
        """领取任务奖励"""
        if not self.taskCode:
            return False
        
        path = '~memberNonactivity~integralTaskStrategyService~receiveTaskReward'
        data = {'taskCode': self.taskCode}
        
        resp = self.http.request(path, data)
        if resp and resp.get('success'):
            return True
        
        # 换一个接口试试
        path2 = '~memberNonactivity~integralTaskService~receiveReward'
        resp2 = self.http.request(path2, data)
        if resp2 and resp2.get('success'):
            return True
        
        return False
    
    def _update_points(self):
        """更新积分"""
        path = '~memberNonactivity~integralTaskStrategyService~queryPointTaskAndSignFromES'
        data = {'channelType': '1', 'deviceId': self.generate_device_id()}
        resp = self.http.request(path, data)
        if resp and resp.get('success') and resp.get('obj'):
            self.total_points = resp['obj'].get('totalPoint', self.total_points)
    
    def handle_welfare_task(self, task_name: str) -> bool:
        """处理生活特权福利任务"""
        # 先领取福利
        path = '~memberNonactivity~integralTaskStrategyService~receiveWelfareTask'
        data = {'taskCode': self.taskCode, 'taskName': task_name}
        
        resp = self.http.request(path, data)
        if resp and resp.get('success'):
            return True
        return False
    
    # ---------- 保活 ----------
    
    def keep_alive(self) -> tuple[bool, str, int]:
        """保活模式 - 轻量请求保持 session 活跃
        
        Returns:
            tuple[是否成功, 错误信息, 当前积分]
        """
        path = '~memberNonactivity~integralTaskStrategyService~queryPointTaskAndSignFromES'
        data = {'channelType': '1', 'deviceId': self.generate_device_id()}
        
        resp = self.http.request(path, data)
        if resp and resp.get('success') and resp.get('obj'):
            points = resp['obj'].get('totalPoint', 0)
            self.logger.info(f"[保活模式] 保活成功，当前积分：{points}")
            return True, '', points
        
        error_msg = resp.get('errorMessage', '保活失败') if resp else '请求失败'
        return False, error_msg, 0
    
    # ---------- 执行所有任务 ----------
    
    def run_all_tasks(self) -> tuple[int, int]:
        """执行所有任务
        
        Returns:
            tuple[执行前积分, 执行后积分]
        """
        print('-' * 50)
        self.logger.info("正在获取任务列表...")
        
        tasks = self.get_task_list()
        if not tasks:
            self.logger.error("获取任务列表失败")
            return (0, 0)
        
        points_before = self.total_points
        self.logger.points_info(points_before, "执行前积分")
        
        completed = 0
        seen_tasks = set()  # 去重
        
        for task in tasks:
            title = task.get('title', '未知任务')
            status = task.get('status')
            
            # 去重
            task_key = f"{title}_{task.get('taskCode', '')}"
            if task_key in seen_tasks:
                continue
            seen_tasks.add(task_key)
            
            # 已完成
            if status == 3:
                self.logger.success(f"{title} - 已完成")
                continue
            
            # 跳过列表
            if title in self.config.SKIP_TASKS:
                self.logger.task_skip(title)
                continue
            
            # 提取属性
            self._set_task_attrs(task)
            
            if not self.taskCode:
                if 'buttonRedirect' in task:
                    extracted = self._extract_task_id_from_url(task['buttonRedirect'])
                    if extracted:
                        self.taskCode = extracted
                    else:
                        self.logger.warning(f"{title} - 无法提取taskCode，跳过")
                        continue
                else:
                    self.logger.warning(f"{title} - 无法提取taskCode，跳过")
                    continue
            
            self.logger.task_found(title, status)
            
            # 特殊任务：生活特权
            if '领任意生活特权福利' in title:
                if self.handle_welfare_task(title):
                    time.sleep(2)
                    if self.execute_task():
                        self.logger.task_complete(title)
                        time.sleep(2)
                        if self.receive_task_reward():
                            self.logger.reward_get(title)
                            self._update_points()
                            completed += 1
                    else:
                        self.logger.warning(f"任务执行失败: {title}")
                else:
                    self.logger.warning(f"{title} - 无法完成,跳过")
                time.sleep(3)
                continue
            
            # 状态1：需要先执行
            if status == 1:
                if '连签7天' in title and 'process' in task:
                    current, total = map(int, task['process'].split('/'))
                    if current < total:
                        self.logger.info(f"【{title}】进度: {task['process']}，还需{total - current}天")
                        continue
                
                if self.execute_task():
                    self.logger.task_complete(title)
                    time.sleep(2)
                    status = 2
                else:
                    self.logger.warning(f"任务执行失败: {title}")
                    continue
            
            # 状态2：可领取奖励
            if status == 2:
                if self.receive_task_reward():
                    self.logger.reward_get(title)
                    self._update_points()
                    completed += 1
                    continue
                
                # 再试一次：先执行再领取
                if self.execute_task():
                    self.logger.task_complete(title)
                    time.sleep(2)
                    if self.receive_task_reward():
                        self.logger.reward_get(title)
                        self._update_points()
                        completed += 1
                else:
                    self.logger.warning(f"任务执行失败: {title}")
                continue
            
            time.sleep(2)
        
        # 获取最终积分
        self._update_points()
        points_after = self.total_points
        self.logger.points_info(points_after, "执行后积分")
        
        self.logger.info(f"共完成 {completed} 个任务")
        return (points_before, points_after)


# ==================== 账号管理器 ====================
class AccountManager:
    """账号管理器"""
    
    def __init__(self, account_url: str, account_index: int, config: Config, logger: Logger):
        self.account_url = account_url
        self.account_index = account_index
        self.config = config
        self.logger = logger
        self.http_client = SFHttpClient(config)
        self.user_id = ''
        self.phone = ''
    
    def run(self) -> Dict:
        """运行单账号任务
        
        Returns:
            结果字典
        """
        self.logger.reset_account()
        
        print(f"\n{'='*60}")
        print(f"👤 账号 {self.account_index + 1}")
        print(f"{'='*60}")
        
        # 登录
        success, self.user_id, self.phone = self.http_client.login(self.account_url)
        
        if not success:
            self.logger.error(f"账号{self.account_index + 1} 登录失败，请检查 sfsyUrl 是否正确")
            return {
                'index': self.account_index,
                'success': False,
                'phone': self.phone or '未知',
                'points_before': 0,
                'points_after': 0,
                'points_earned': 0,
                'expired': True,
                'keepalive': self.config.SF_KEEPALIVE,
            }
        
        self.logger.user_info(self.phone)
        
        # 初始化任务执行器
        executor = TaskExecutor(self.http_client, self.logger, self.config, self.user_id)
        
        # 保活模式
        if self.config.SF_KEEPALIVE:
            self.logger.info('💓 保活模式：只进行轻量请求保活...')
            alive, alive_msg, current_points = executor.keep_alive()
            
            if alive:
                return {
                    'index': self.account_index,
                    'success': True,
                    'phone': self.phone,
                    'points_before': current_points,
                    'points_after': current_points,
                    'points_earned': 0,
                    'keepalive': True,
                    'expired': False,
                }
            else:
                self.logger.error(f'保活失败: {alive_msg}')
                return {
                    'index': self.account_index,
                    'success': False,
                    'phone': self.phone,
                    'points_before': 0,
                    'points_after': 0,
                    'points_earned': 0,
                    'expired': True,
                    'keepalive': True,
                }
        
        # 签到
        sign_success, sign_error = executor.sign_in()
        time.sleep(1)
        
        # 执行任务
        points_before, points_after = executor.run_all_tasks()
        points_earned = points_after - points_before
        
        # 检测 session 是否失效
        session_expired = False
        if not sign_success and '用户信息失效' in sign_error:
            session_expired = True
        elif points_before == 0 and points_after == 0 and not sign_success:
            session_expired = True
        
        if session_expired:
            self.logger.error(f'账号{self.account_index + 1} sfsyUrl 已过期，请重新获取')
        
        return {
            'index': self.account_index,
            'success': not session_expired,
            'phone': self.phone,
            'points_before': points_before,
            'points_after': points_after,
            'points_earned': points_earned,
            'expired': session_expired,
            'keepalive': False,
        }


# ==================== WxPusher 推送 ====================
def send_wxpusher(config: Config, title: str, content: str):
    """发送 WxPusher 推送"""
    if not config.WXPUSHER_APP_TOKEN:
        return False
    
    url = 'https://wxpusher.zjiecode.com/api/send/message'
    data = {
        'appToken': config.WXPUSHER_APP_TOKEN,
        'content': f'{title}\n\n{content}',
        'contentType': 1,
    }
    
    if config.WXPUSHER_UIDS:
        data['uids'] = [u.strip() for u in config.WXPUSHER_UIDS.split(',') if u.strip()]
    if config.WXPUSHER_TOPIC_IDS:
        data['topicIds'] = [int(t.strip()) for t in config.WXPUSHER_TOPIC_IDS.split(',') if t.strip()]
    
    try:
        resp = requests.post(url, json=data, timeout=10)
        result = resp.json()
        return result.get('success', False)
    except:
        return False


# ==================== 主函数 ====================
def main():
    """主函数"""
    config = Config()
    
    print(f"\n{'='*60}")
    print(f"🚀 {config.APP_NAME} 日常积分任务 v{config.VERSION}")
    print(f"{'='*60}")
    print(f"📅 运行时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📱 平台: APP端 (SFAPP)")
    if config.SF_KEEPALIVE:
        print(f"💓 模式: 保活模式")
    print(f"⚡ 并发数: {CONCURRENT_NUM}")
    print(f"{'='*60}")
    
    # 获取账号列表
    env_value = os.getenv(config.ENV_NAME, '')
    if not env_value:
        print(f"\n❌ 未找到环境变量 {config.ENV_NAME}")
        print(f"   请在环境变量中设置 sfsyUrl")
        print(f"   格式: sessionId=xxx;_login_user_id_=xxx;_login_mobile_=xxx")
        print(f"   多账号用 & 分隔")
        return
    
    accounts = [a.strip() for a in env_value.split('&') if a.strip()]
    print(f"\n👥 共找到 {len(accounts)} 个账号")
    
    if not accounts:
        print("❌ 没有有效的账号")
        return
    
    # 执行任务
    all_results = []
    logger = Logger()
    
    if CONCURRENT_NUM == 1 or len(accounts) == 1:
        # 串行执行
        for i, account in enumerate(accounts):
            manager = AccountManager(account, i, config, logger)
            result = manager.run()
            all_results.append(result)
    else:
        # 并发执行
        with ThreadPoolExecutor(max_workers=CONCURRENT_NUM) as executor:
            futures = {}
            for i, account in enumerate(accounts):
                acc_logger = Logger()
                manager = AccountManager(account, i, config, acc_logger)
                future = executor.submit(manager.run)
                futures[future] = (i, acc_logger)
            
            for future in as_completed(futures):
                result = future.result()
                all_results.append(result)
        
        # 按序号排序
        all_results.sort(key=lambda x: x['index'])
    
    # 显示汇总
    all_results.sort(key=lambda x: x['index'])
    
    success_count = sum(1 for r in all_results if r['success'])
    fail_count = len(all_results) - success_count
    total_earned = sum(r['points_earned'] for r in all_results if r['success'])
    expired_count = sum(1 for r in all_results if r.get('expired'))
    
    print(f"\n{'='*80}")
    if config.SF_KEEPALIVE:
        print(f"💓 保活模式汇总")
    else:
        print(f"📊 积分统计汇总")
    print(f"{'='*80}")
    
    if config.SF_KEEPALIVE:
        print(f"{'序号':<6} {'手机号':<15} {'当前积分':<15} {'状态':<10}")
    else:
        print(f"{'序号':<6} {'手机号':<15} {'今日获得积分':<15} {'总积分':<15} {'状态':<10}")
    print(f"{'-'*80}")
    
    for result in all_results:
        idx = result['index'] + 1
        phone = result['phone']
        if phone and len(phone) >= 11:
            phone = phone[:3] + '****' + phone[7:]
        earned = result['points_earned']
        total = result['points_after']
        status = '💓保活成功' if (result['success'] and config.SF_KEEPALIVE) else ('✅成功' if result['success'] else '❌已过期')
        
        if config.SF_KEEPALIVE:
            print(f"{idx:<6} {phone:<15} {total:<15} {status:<10}")
        else:
            print(f"{idx:<6} {phone:<15} {earned:<15} {total:<15} {status:<10}")
    
    print(f"{'-'*80}")
    if config.SF_KEEPALIVE:
        print(f"{'汇总':<6} {'账号总数: ' + str(len(all_results)):<15} {'成功: ' + str(success_count):<15} {'失败: ' + str(fail_count):<10}")
    else:
        print(f"{'汇总':<6} {'账号总数: ' + str(len(all_results)):<15} {'今日总获得: ' + str(total_earned):<15} {'':<15} {'成功: ' + str(success_count):<10}")
    print(f"{'='*80}")
    
    # WxPusher 推送
    if config.WXPUSHER_APP_TOKEN:
        should_push = False
        push_title = ''
        push_content = ''
        
        if expired_count > 0:
            should_push = True
            push_title = '⚠️ 顺丰速运 sfsyUrl 过期提醒'
            expired_accounts = [r for r in all_results if r.get('expired')]
            lines = [f'有 {len(expired_accounts)} 个账号的 sfsyUrl 已过期，请重新获取！\n']
            for r in expired_accounts:
                phone = r['phone']
                if phone and len(phone) >= 11:
                    phone = phone[:3] + '****' + phone[7:]
                lines.append(f"账号 {r['index'] + 1}: {phone}")
            lines.append('\n请使用 iPhone Stream 重新抓包获取最新的 sessionId')
            push_content = '\n'.join(lines)
        elif not config.WXPUSHER_ONLY_EXPIRED:
            should_push = True
            push_title = '📊 顺丰速运每日签到汇总'
            lines = [f'运行时间: {time.strftime("%Y-%m-%d %H:%M:%S")}']
            lines.append(f'账号总数: {len(all_results)}')
            lines.append(f'成功: {success_count}  失败: {fail_count}')
            lines.append(f'今日总获得: {total_earned} 积分\n')
            for r in all_results:
                phone = r['phone']
                if phone and len(phone) >= 11:
                    phone = phone[:3] + '****' + phone[7:]
                status = '✅' if r['success'] else '❌'
                lines.append(f"{status} 账号{r['index'] + 1} {phone}: +{r['points_earned']}分 (共{r['points_after']}分)")
            push_content = '\n'.join(lines)
        
        if should_push:
            send_wxpusher(config, push_title, push_content)
            print(f"\n📨 WxPusher 推送已发送")


if __name__ == '__main__':
    main()
