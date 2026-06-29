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
| `sfsyUrl` | 顺丰速运小程序抓包URL，多账号用 `&` 分隔 | `https://mcs-mimp-web.sf-express.com/...` |

### 可选变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `SFBF` | 并发数量（1-20），1为串行 | `1` |
| `SF_PROXY_API_URL` | 代理 API 地址（返回 ip:port 格式） | 空（不使用代理） |

## 获取 sfsyUrl

### 方法一：综合工具（推荐 ⭐⭐⭐）

**三合一工具**：扫码登录 + 代理抓包 + 手动同步，自动降级，一个脚本全搞定。

```bash
python sf_qrlogin.py
```

| 功能 | 说明 |
|------|------|
| 扫码登录 | 10+接口自动尝试，微信扫码即得 |
| 代理抓包 | 扫码不行自动切换，mitmproxy 自动配置 |
| 手动同步 | 已有URL直接粘贴同步 |
| 青龙配置 | 一键配置青龙面板，自动同步 |
| 账号管理 | 查看本地和青龙上的所有账号 |

**推荐流程**：先试扫码登录 → 不行自动切代理抓包 → 手动兜底

### 方法二：电脑微信代理抓包（单独版）

电脑端打开微信小程序，脚本自动抓包 + 一键同步到青龙面板。

```bash
python sf_login.py
```

操作步骤：
1. 运行 `sf_login.py`，选择「1 - 一键抓取」
2. 脚本自动安装依赖 + 设置系统代理
3. 打开电脑微信 → 顺丰速运+小程序 → 积分页面
4. 自动捕获 sfsyUrl，一键同步到青龙

首次使用需要安装 mitmproxy 证书（脚本有提示）。

### 方法三：手机端抓包工具

手机 WiFi 代理抓包，适合没有电脑微信的场景。

```bash
pip install mitmproxy
python capture_sfsy.py
```

详细使用说明请参考 [CAPTURE_GUIDE.md](CAPTURE_GUIDE.md)

### 方法四：手动抓包

1. 打开微信，进入「顺丰速运+」小程序
2. 进入「我的」→「积分」→ 任务列表界面
3. 使用抓包工具（如 HttpCanary、Stream、Charles 等）抓取请求
4. 找到以下任一 URL，复制完整 URL：
   - `https://mcs-mimp-web.sf-express.com/mcs-mimp/share/weChat/shareGiftReceiveRedirect`
   - `https://mcs-mimp-web.sf-express.com/mcs-mimp/share/app/shareRedirect`
   - 任何包含 Cookie 的 mcs-mimp-web.sf-express.com 域名请求

### Cookie 格式（可选）

也可以直接使用 Cookie 字符串，格式如下：
```
sessionId=xxx;_login_mobile_=13800138000;_login_user_id_=xxx
```

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
- 值：抓包获取的完整 URL
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
$env:sfsyUrl = "你的抓包URL"

# Linux / macOS
export sfsyUrl="你的抓包URL"
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

在 `sfsyUrl` 变量中用 `&` 分隔多个 URL：

```
https://mcs-mimp-web.sf-express.com/...账号1...&https://mcs-mimp-web.sf-express.com/...账号2...
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

## 注意事项

1. 本脚本仅供学习交流使用，请勿用于商业用途
2. 使用本脚本所产生的一切后果由使用者自行承担
3. 请合理使用，避免频繁请求导致账号异常
4. 如遇接口变更，请及时更新脚本
5. 建议使用代理 IP 降低账号封禁风险

## 免责声明

本项目仅供学习研究使用，使用者需自行承担使用风险。请遵守相关法律法规及平台用户协议。

## License

MIT
