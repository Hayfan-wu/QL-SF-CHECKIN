# QL-SF-CHECKIN

顺丰速运小程序每日签到 & 日常任务脚本

## 功能特性

- ✅ 三重签到兜底（APP签到 / 新签到 / 小程序签到）
- 📋 自动完成日常任务（多渠道去重）
- 💰 积分查询与统计
- 🎁 生活特权自动领取
- 🔐 MD5 签名认证，请求更稳定
- 🌐 代理 IP 支持（可选）
- ⚡ 多账号并发执行（最大20并发）
- 👥 多账号支持（& 分隔）
- ⏭️  任务跳过列表（可配置）
- 📱 支持青龙面板 / Python 运行

## 环境变量

### 必需变量

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `sfsyUrl` | 顺丰速运小程序登录态，多账号用 `&` 分隔 | `sessionId=xxx;_login_mobile_=13800138000;_login_user_id_=xxx` |

### 可选变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `SFBF` | 并发数量（1-20），1为串行 | `1` |
| `SF_PROXY_API_URL` | 代理 API 地址（返回 ip:port 格式） | 空（不使用代理） |
| `WXPUSHER_APP_TOKEN` | WxPusher 应用Token（启用推送） | 空（不推送） |
| `WXPUSHER_UIDS` | WxPusher 用户UID，多个用逗号分隔 | 空 |
| `WXPUSHER_TOPIC_IDS` | WxPusher 主题ID，多个用逗号分隔 | 空 |

## 获取 sfsyUrl

### iPhone 抓包（Stream 方式）

1. App Store 搜索下载 **Stream**（开发者 Suying，免费）
2. 打开 Stream → HTTPS 抓包 → 安装证书 → 允许下载描述文件
3. 设置 → 已下载描述文件 → 安装证书
4. 设置 → 通用 → 关于本机 → 证书信任设置 → 开启 Stream 证书
5. Stream 首页 → 开始抓包
6. 打开微信 → 顺丰速运+小程序 → 进入「我的」或「积分」页面
7. 回到 Stream → 停止抓包 → 抓包历史
8. 搜索 `mcs-mimp-web`，找到 Cookie 里有 `_login_user_id_` 和 `_login_mobile_` 的请求
9. 从 Cookie 中提取 `sessionId`、`_login_mobile_`、`_login_user_id_`，拼成以下格式：

```
sessionId=xxx;_login_mobile_=13800138000;_login_user_id_=xxx
```

### 安卓抓包

类似原理，使用 **HttpCanary**（黄鸟）或 **Stream** 等抓包工具，抓取 `mcs-mimp-web.sf-express.com` 域名的请求，提取 Cookie 中的登录态。

## 青龙面板部署

### 方式一：单文件拉取

```bash
ql raw https://raw.githubusercontent.com/Hayfan-wu/QL-SF-CHECKIN/main/sfsy.py
```

### 方式二：仓库拉取

```bash
ql repo https://github.com/Hayfan-wu/QL-SF-CHECKIN.git "sfsy" "" ""
```

### 配置环境变量

在青龙面板 → 环境变量 → 新增变量：

- 名称：`sfsyUrl`
- 值：抓包获取的登录态（CK格式）
- 多账号：用 `&` 分隔

### 定时任务

建议每天运行 1-2 次：

```
51 8,21 * * *
```

## 本地运行

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置环境变量

```bash
# Windows (PowerShell)
$env:sfsyUrl = "你的登录态"

# Linux / macOS
export sfsyUrl="你的登录态"
```

### 运行脚本

```bash
python sfsy.py
```

## 脚本功能说明

### 签到功能

脚本会依次尝试三种签到方式，确保签到成功：

1. **APP 签到** - `getUnFetchPointAndDiscount` 接口
2. **新签到** - `integralSignV2Service` 接口（V2版）
3. **小程序签到** - `automaticSignFetchPackage` 接口

### 任务系统

- 遍历 8 个 channelType 获取任务列表
- 自动去重相同 taskCode 的任务
- 自动从 `buttonRedirect` URL 中提取 taskId
- 支持任务状态判断（1=待执行，2=待领取，3=已完成）
- 智能重试：先直接领奖励，失败则先执行再领取

### 生活特权

- 自动获取生活特权列表
- 自动领取可用的特权福利
- 领取后自动提交任务并领取积分

### 代理支持

配置 `SF_PROXY_API_URL` 环境变量启用代理：

```
http://your-proxy-api.com/getProxy
```

代理 API 返回格式：`ip:port` 或 `http://ip:port`

### 并发执行

设置 `SFBF` 环境变量控制并发数：

```bash
export SFBF=5  # 5个账号并发执行
```

## 多账号支持

在 `sfsyUrl` 变量中用 `&` 分隔多个登录态：

```
sessionId=xxx;_login_mobile_=13800138000;_login_user_id_=xxx&sessionId=yyy;_login_mobile_=13900139000;_login_user_id_=yyy
```

脚本会随机打乱执行顺序，降低风控风险。

## 跳过任务

脚本默认跳过以下任务（在 `Config.SKIP_TASKS` 中配置）：

- 用行业模板寄件下单
- 用积分兑任意礼品
- 参与积分活动
- 每月累计寄件
- 完成每月任务
- 去使用AI寄件

如需修改，可编辑脚本中的 `SKIP_TASKS` 列表。

## 技术架构

```
Config          # 全局配置
Logger          # 日志管理器（线程安全）
ProxyManager    # 代理管理器
SFHttpClient    # HTTP客户端（含签名、重试、代理切换）
TaskExecutor    # 任务执行器
AccountManager  # 账号管理器
main()          # 主程序入口
```

## WxPusher 推送（可选）

支持通过 WxPusher 推送签到结果和 sfsyUrl 过期提醒到微信。

### 配置方式

在青龙面板 → 环境变量中添加：

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `WXPUSHER_APP_TOKEN` | WxPusher 应用 Token（必填） | `AT_xxx...` |
| `WXPUSHER_UIDS` | 用户 UID，多个用逗号分隔 | `UID_xxx,UID_yyy` |
| `WXPUSHER_TOPIC_IDS` | 主题 ID，多个用逗号分隔 | `123,456` |

> `WXPUSHER_UIDS` 和 `WXPUSHER_TOPIC_IDS` 至少配置一个。

### 推送内容

- **全部成功**：推送签到汇总，包含每个账号获得的积分
- **有账号失效**：推送失败提醒，提示哪个账号的 sfsyUrl 需要更新

### 获取 WxPusher Token

1. 微信搜索「WxPusher」公众号并关注
2. 访问 [wxpusher.zjiecode.com](https://wxpusher.zjiecode.com/) 注册账号
3. 创建应用，获取 `APP_TOKEN`
4. 在公众号后台获取你的 `UID`

## 注意事项

1. 本脚本仅供学习交流使用，请勿用于商业用途
2. 使用本脚本所产生的一切后果由使用者自行承担
3. 请合理使用，避免频繁请求导致账号异常
4. 如遇接口变更，请及时更新脚本
5. 建议使用代理 IP 降低账号封禁风险
6. sessionId 有效期约几天到一周，过期需重新抓包

## 免责声明

本项目仅供学习研究使用，使用者需自行承担使用风险。请遵守相关法律法规及平台用户协议。

## License

MIT
