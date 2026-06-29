# QL-SF-CHECKIN

顺丰速运小程序每日签到 & 日常任务脚本

## 功能特性

- ✅ 每日自动签到
- 📋 自动完成日常任务
- 💰 积分查询与统计
- 🐝 采蜜游戏（可选）
- 🎰 积分抽奖（可选）
- 👥 多账号支持
- 📱 支持青龙面板 / Node.js 运行

## 环境变量

### 必需变量

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `sfsyUrl` | 顺丰速运小程序抓包URL，多账号换行分割 | `https://mcs-mimp-web.sf-express.com/...` |

### 可选变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `sfsyBee` | 是否开启采蜜游戏（`true`/`false`） | `false` |

## 抓包教程

### 方法一：小程序抓包

1. 打开微信，进入「顺丰速运+」小程序
2. 进入「我的」→「积分」→ 任务列表界面
3. 使用抓包工具（如 HttpCanary、Stream、Charles 等）抓取请求
4. 找到以下任一 URL，复制完整 URL：
   - `https://mcs-mimp-web.sf-express.com/mcs-mimp/share/weChat/shareGiftReceiveRedirect`
   - `https://mcs-mimp-web.sf-express.com/mcs-mimp/share/app/shareRedirect`
   - 任何包含 `memberId` 参数的 URL

### 方法二：APP 抓包

1. 打开顺丰速运 APP
2. 进入「我的」→「积分」→ 任务列表界面
3. 抓包获取包含 `memberId` 的 URL

## 青龙面板部署

### 方式一：单文件拉取

```bash
ql raw https://raw.githubusercontent.com/Hayfan-wu/QL-SF-CHECKIN/main/sfsy.js
```

### 方式二：仓库拉取

```bash
ql repo https://github.com/Hayfan-wu/QL-SF-CHECKIN.git "sfsy" "" ""
```

### 配置环境变量

在青龙面板 → 环境变量 → 新增变量：

- 名称：`sfsyUrl`
- 值：抓包获取的完整 URL
- 多账号：每行一个 URL

### 定时任务

建议每天运行 1-2 次：

```
51 8,21 * * *
```

## 本地运行

### 安装依赖

```bash
npm install
```

### 配置环境变量

```bash
# Windows (PowerShell)
$env:sfsyUrl = "你的抓包URL"

# Linux / macOS
export sfsyUrl="你的抓包URL"
```

### 运行脚本

```bash
npm start
```

## 脚本功能说明

### 积分任务

1. **每日签到** - 每天签到获取积分
2. **浏览任务** - 模拟浏览各页面完成任务
3. **日常任务** - 自动完成所有可完成的日常任务
4. **积分查询** - 显示当前积分余额

### 采蜜游戏（可选）

- 领取可收集的蜂蜜
- 采集花朵获得蜂蜜
- 蜂蜜可兑换快递券和实物

### 积分抽奖（可选）

- 使用积分参与抽奖
- 有机会获得各种奖品

## 多账号支持

在 `sfsyUrl` 变量中每行填写一个 URL 即可支持多账号：

```
https://mcs-mimp-web.sf-express.com/...账号1...
https://mcs-mimp-web.sf-express.com/...账号2...
```

## 注意事项

1. 本脚本仅供学习交流使用，请勿用于商业用途
2. 使用本脚本所产生的一切后果由使用者自行承担
3. 请合理使用，避免频繁请求导致账号异常
4. 如遇接口变更，请及时更新脚本

## 免责声明

本项目仅供学习研究使用，使用者需自行承担使用风险。请遵守相关法律法规及平台用户协议。

## License

MIT
