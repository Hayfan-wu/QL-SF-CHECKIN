/*
顺丰速运小程序 - 每日签到 & 日常任务脚本
版本: v3.0.0
功能: 自动签到、完成日常任务、领取积分、采蜜游戏
支持环境: 青龙面板 / Node.js
变量: sfsyUrl (多账号换行分割)
     sfsyBee (是否开启采蜜游戏, 默认关闭)
*/

const axios = require('axios');
const querystring = require('querystring');

// ============== 环境变量获取 ==============
function getEnv(name) {
  return process.env[name] || '';
}

// ============== 日志输出 ==============
const EnvName = '顺丰速运';
function log(msg) {
  console.log(`【${EnvName}】${msg}`);
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ============== 用户信息 ==============
class SFUser {
  constructor(url, index) {
    this.index = index;
    this.rawUrl = url.trim();
    this.memberId = '';
    this.token = '';
    this.platform = '';
    this.cookies = {};
    this.points = 0;
    this.signInDays = 0;
  }

  async init() {
    log(`\n========== 账号 ${this.index} 开始执行 ==========`);
    
    // 解析URL获取参数
    await this.parseUrl();
    
    if (!this.memberId) {
      log('❌ 无法获取 memberId，请检查 sfsyUrl 配置');
      return false;
    }
    
    log(`✅ 账号初始化成功，memberId: ${this.memberId}`);
    return true;
  }

  async parseUrl() {
    try {
      // 尝试从URL中解析参数
      const url = new URL(this.rawUrl);
      const params = new URLSearchParams(url.search);
      
      this.memberId = params.get('memberId') || params.get('menId') || '';
      this.token = params.get('token') || params.get('access_token') || '';
      this.platform = params.get('platform') || 'wechat';
      
      // 如果URL是分享链接，需要访问获取真实参数
      if (!this.memberId && this.rawUrl.includes('shareGiftReceiveRedirect')) {
        await this.getMemberInfoFromShareUrl();
      }
    } catch (e) {
      log(`⚠️ URL解析失败: ${e.message}`);
    }
  }

  async getMemberInfoFromShareUrl() {
    try {
      const res = await axios.get(this.rawUrl, {
        maxRedirects: 5,
        headers: {
          'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.0(0x18000000) NetType/WIFI Language/zh_CN',
        }
      });
      
      // 从响应中提取 memberId
      const match = res.data.match(/memberId[=:]["']?([^"'&<>\s]+)/i);
      if (match) {
        this.memberId = match[1];
      }
      
      // 提取 cookie
      if (res.headers['set-cookie']) {
        const cookies = res.headers['set-cookie'];
        cookies.forEach(cookie => {
          const [name, value] = cookie.split(';')[0].split('=');
          this.cookies[name] = value;
        });
      }
    } catch (e) {
      log(`⚠️ 获取分享链接信息失败: ${e.message}`);
    }
  }

  getCookieString() {
    return Object.entries(this.cookies)
      .map(([k, v]) => `${k}=${v}`)
      .join('; ');
  }

  // ============== 基础请求方法 ==============
  async request(options) {
    const defaultHeaders = {
      'Host': 'mcs-mimp-web.sf-express.com',
      'Content-Type': 'application/json',
      'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.0(0x18000000) NetType/WIFI Language/zh_CN',
      'Referer': 'https://mcs-mimp-web.sf-express.com/',
      'Origin': 'https://mcs-mimp-web.sf-express.com',
    };

    if (this.getCookieString()) {
      defaultHeaders['Cookie'] = this.getCookieString();
    }

    try {
      const res = await axios({
        ...options,
        headers: { ...defaultHeaders, ...options.headers },
        timeout: 30000,
      });
      return res.data;
    } catch (e) {
      log(`⚠️ 请求失败: ${e.message}`);
      return null;
    }
  }

  // ============== 1. 查询用户积分信息 ==============
  async getUserPoint() {
    log('📊 查询积分信息...');
    
    const data = await this.request({
      method: 'POST',
      url: 'https://mcs-mimp-web.sf-express.com/mcs-mimp/point/queryUserPoint',
      data: {
        memberId: this.memberId,
      }
    });

    if (data && data.success) {
      this.points = data.obj?.point || data.obj?.availablePoint || 0;
      log(`💰 当前积分: ${this.points}`);
      return data.obj;
    } else {
      log(`⚠️ 查询积分失败: ${data?.errorMsg || '未知错误'}`);
      return null;
    }
  }

  // ============== 2. 签到 ==============
  async doSignIn() {
    log('📝 执行签到...');
    
    const data = await this.request({
      method: 'POST',
      url: 'https://mcs-mimp-web.sf-express.com/mcs-mimp/point/signIn',
      data: {
        memberId: this.memberId,
      }
    });

    if (data && data.success) {
      const signPoint = data.obj?.signPoint || data.obj?.point || 0;
      const continuousDays = data.obj?.continuousDays || 0;
      log(`✅ 签到成功！获得 ${signPoint} 积分，已连续签到 ${continuousDays} 天`);
      this.signInDays = continuousDays;
      return true;
    } else if (data && data.errorCode === 'SIGN_IN_ALREADY') {
      log('ℹ️  今日已签到');
      return true;
    } else {
      log(`⚠️ 签到失败: ${data?.errorMsg || '未知错误'}`);
      return false;
    }
  }

  // ============== 3. 查询签到状态 ==============
  async getSignInStatus() {
    log('📋 查询签到状态...');
    
    const data = await this.request({
      method: 'POST',
      url: 'https://mcs-mimp-web.sf-express.com/mcs-mimp/point/signInStatus',
      data: {
        memberId: this.memberId,
      }
    });

    if (data && data.success) {
      const todaySigned = data.obj?.todaySigned || false;
      const continuousDays = data.obj?.continuousDays || 0;
      log(`📅 今日已签到: ${todaySigned ? '是' : '否'}，连续签到: ${continuousDays} 天`);
      this.signInDays = continuousDays;
      return data.obj;
    }
    return null;
  }

  // ============== 4. 查询任务列表 ==============
  async getTaskList() {
    log('📋 获取任务列表...');
    
    const data = await this.request({
      method: 'POST',
      url: 'https://mcs-mimp-web.sf-express.com/mcs-mimp/point/queryTaskList',
      data: {
        memberId: this.memberId,
        taskType: 'DAILY',
      }
    });

    if (data && data.success) {
      const tasks = data.obj || [];
      log(`📋 找到 ${tasks.length} 个日常任务`);
      return tasks;
    } else {
      log(`⚠️ 获取任务列表失败: ${data?.errorMsg || '未知错误'}`);
      return [];
    }
  }

  // ============== 5. 完成任务 ==============
  async completeTask(task) {
    const taskName = task.taskName || task.name || '未知任务';
    const taskCode = task.taskCode || task.code || '';
    const taskStatus = task.taskStatus || task.status || '';

    if (taskStatus === 'COMPLETED' || taskStatus === 'FINISHED') {
      log(`✅ 任务「${taskName}」已完成`);
      return true;
    }

    log(`🎯 正在完成任务: ${taskName}`);

    // 先触发任务
    const triggerData = await this.request({
      method: 'POST',
      url: 'https://mcs-mimp-web.sf-express.com/mcs-mimp/point/triggerTask',
      data: {
        memberId: this.memberId,
        taskCode: taskCode,
      }
    });

    await sleep(1000);

    // 再领取奖励
    const rewardData = await this.request({
      method: 'POST',
      url: 'https://mcs-mimp-web.sf-express.com/mcs-mimp/point/receiveTaskReward',
      data: {
        memberId: this.memberId,
        taskCode: taskCode,
      }
    });

    if (rewardData && rewardData.success) {
      const rewardPoint = rewardData.obj?.rewardPoint || 0;
      log(`🎉 任务「${taskName}」完成，获得 ${rewardPoint} 积分`);
      return true;
    } else if (triggerData && triggerData.success) {
      log(`ℹ️  任务「${taskName}」已触发，奖励可能延迟到账`);
      return true;
    } else {
      log(`⚠️ 任务「${taskName}」完成失败: ${rewardData?.errorMsg || triggerData?.errorMsg || '未知错误'}`);
      return false;
    }
  }

  // ============== 6. 浏览任务（模拟浏览） ==============
  async doBrowseTasks() {
    log('📖 执行浏览类任务...');
    
    const browseTasks = [
      { taskCode: 'BROWSE_HOME_PAGE', taskName: '浏览首页' },
      { taskCode: 'BROWSE_POINT_MALL', taskName: '浏览积分商城' },
      { taskCode: 'BROWSE_EXPRESS_QUERY', taskName: '浏览查件页' },
      { taskCode: 'BROWSE_MEMBER_CENTER', taskName: '浏览会员中心' },
    ];

    for (const task of browseTasks) {
      await this.completeTask(task);
      await sleep(2000);
    }
  }

  // ============== 7. 采蜜游戏 ==============
  async doBeeGame() {
    log('🐝 开始采蜜游戏...');
    
    // 查询蜂蜜数量
    const honeyData = await this.request({
      method: 'POST',
      url: 'https://mcs-mimp-web.sf-express.com/mcs-mimp/beeGame/getUserHoney',
      data: {
        memberId: this.memberId,
      }
    });

    if (honeyData && honeyData.success) {
      const honey = honeyData.obj?.honey || 0;
      log(`🍯 当前蜂蜜: ${honey}`);
    }

    // 领取蜂蜜
    const collectData = await this.request({
      method: 'POST',
      url: 'https://mcs-mimp-web.sf-express.com/mcs-mimp/beeGame/collectHoney',
      data: {
        memberId: this.memberId,
      }
    });

    if (collectData && collectData.success) {
      const collected = collectData.obj?.collectedHoney || 0;
      log(`🍯 领取蜂蜜成功: +${collected}`);
    } else if (collectData?.errorCode === 'NO_HONEY_TO_COLLECT') {
      log('ℹ️  暂无可领取的蜂蜜');
    } else {
      log(`⚠️ 领取蜂蜜失败: ${collectData?.errorMsg || '未知错误'}`);
    }

    // 采蜜（点击花朵）
    for (let i = 0; i < 5; i++) {
      const gatherData = await this.request({
        method: 'POST',
        url: 'https://mcs-mimp-web.sf-express.com/mcs-mimp/beeGame/gatherHoney',
        data: {
          memberId: this.memberId,
          flowerIndex: i,
        }
      });

      if (gatherData && gatherData.success) {
        log(`🌸 第 ${i + 1} 朵花采蜜成功`);
      }
      await sleep(1000);
    }
  }

  // ============== 8. 积分抽奖 ==============
  async doPointLottery() {
    log('🎰 尝试积分抽奖...');
    
    // 查询抽奖信息
    const lotteryData = await this.request({
      method: 'POST',
      url: 'https://mcs-mimp-web.sf-express.com/mcs-mimp/lottery/queryLotteryInfo',
      data: {
        memberId: this.memberId,
        activityCode: 'POINT_LOTTERY',
      }
    });

    if (!lotteryData || !lotteryData.success) {
      log('⚠️ 查询抽奖信息失败');
      return;
    }

    const remainTimes = lotteryData.obj?.remainTimes || 0;
    const costPoint = lotteryData.obj?.costPoint || 9;
    
    log(`🎰 剩余抽奖次数: ${remainTimes}，每次消耗: ${costPoint} 积分`);

    if (remainTimes > 0 && this.points >= costPoint) {
      // 执行一次抽奖
      const drawData = await this.request({
        method: 'POST',
        url: 'https://mcs-mimp-web.sf-express.com/mcs-mimp/lottery/draw',
        data: {
          memberId: this.memberId,
          activityCode: 'POINT_LOTTERY',
        }
      });

      if (drawData && drawData.success) {
        const prizeName = drawData.obj?.prizeName || '谢谢参与';
        log(`🎉 抽奖结果: ${prizeName}`);
      }
    }
  }

  // ============== 执行所有任务 ==============
  async runAllTasks() {
    const success = await this.init();
    if (!success) return;

    // 1. 查询积分
    await this.getUserPoint();
    await sleep(1000);

    // 2. 签到
    await this.doSignIn();
    await sleep(1000);

    // 3. 查询签到状态
    await this.getSignInStatus();
    await sleep(1000);

    // 4. 获取并完成日常任务
    const tasks = await this.getTaskList();
    if (tasks.length > 0) {
      for (const task of tasks) {
        if (task.taskStatus !== 'COMPLETED' && task.taskStatus !== 'FINISHED') {
          await this.completeTask(task);
          await sleep(2000);
        }
      }
    }

    // 5. 浏览类任务
    await this.doBrowseTasks();

    // 6. 采蜜游戏 (可选)
    const enableBee = getEnv('sfsyBee');
    if (enableBee === 'true') {
      await sleep(1000);
      await this.doBeeGame();
    }

    // 7. 积分抽奖
    await sleep(1000);
    await this.doPointLottery();

    // 8. 最终积分
    await sleep(1000);
    await this.getUserPoint();

    log(`\n✅ 账号 ${this.index} 任务执行完成`);
  }
}

// ============== 主函数 ==============
async function main() {
  log(`========== ${EnvName} 每日任务开始 ==========`);
  log(`脚本版本: v3.0.0`);

  const sfsyUrl = getEnv('sfsyUrl');
  
  if (!sfsyUrl) {
    log('❌ 未配置 sfsyUrl 环境变量');
    log('💡 请在环境变量中配置 sfsyUrl，多账号换行分割');
    return;
  }

  const urls = sfsyUrl.split('\n').filter(u => u.trim());
  log(`📋 共找到 ${urls.length} 个账号`);

  for (let i = 0; i < urls.length; i++) {
    const user = new SFUser(urls[i], i + 1);
    await user.runAllTasks();
    
    if (i < urls.length - 1) {
      await sleep(3000);
    }
  }

  log(`\n========== ${EnvName} 所有账号执行完成 ==========`);
}

// 运行
main().catch(e => {
  log(`❌ 脚本运行出错: ${e.message}`);
  console.error(e);
});

module.exports = { SFUser };
