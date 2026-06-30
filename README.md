# QL-SF-CHECKIN

顺丰速运日常积分任务脚本（APP端精简版）

## 功能特性

- ✅ APP 端签到
- 📋 自动完成日常任务
- 💰 积分查询与统计
- 🎁 生活特权自动领取
- 🔐 MD5 签名认证
- 💓 自动保活模式（延长 session 有效期）
- 📨 WxPusher 微信推送（过期提醒）
- ⚡ 多账号并发（最大20并发）
- 👥 多账号支持（& 分隔）
- 🌐 代理 IP 支持（可选）
- ⏭️  任务跳过列表

## 环境变量

### 必填

| 变量名 | 说明 |
|--------|------|
| `sfsyUrl` | 顺丰速运登录态，CK 格式 |

**sfsyUrl 格式（最简 CK 格式，3个值即可）：**
```
sessionId=xxx;_login_user_id_=xxx;_login_mobile_=xxx
```

多账号用 `&` 分隔：
```
sessionId=aaa;_login_user_id_=bbb;_login_mobile_=111&sessionId=ccc;_login_user_id_=ddd;_login_mobile_=222
```

### 可选变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `SFBF` | 并发数量（1-20），1为串行 | `1` |
| `SF_PROXY_API_URL` | 代理 API 地址 | 空（不使用代理） |
| `SF_KEEPALIVE` | 保活模式（true/false） | `false` |
| `WXPUSHER_APP_TOKEN` | WxPusher 应用 Token | 空（不推送） |
| `WXPUSHER_UIDS` | WxPusher 接收 UID，多账号逗号分隔 | 空 |
| `WXPUSHER_TOPIC_IDS` | WxPusher 主题 ID，多个逗号分隔 | 空 |
| `WXPUSHER_ONLY_EXPIRED` | 只在过期时推送（true/false） | `true` |

## sfsyUrl 获取方法（iPhone）

使用 Stream（小蓝鸟）APP 抓包：

1. App Store 搜索「Stream」下载安装
2. 打开 Stream → 点击「HTTPS 抓包」→「安装证书」
3. 安装描述文件后，去 **设置 → 通用 → 关于本机 → 证书信任设置** 开启信任
4. 点击「开始抓包」
5. 打开**顺丰速运 APP** → 进入「我的」→「积分」
6. 回到 Stream → 停止抓包 → 打开抓包历史
7. 搜索 `mcs-mimp-web`，找一个 POST 请求
8. 点开请求，在 **请求 → Cookie** 中复制这三个值：
   - `sessionId`
   - `_login_user_id_`
   - `_login_mobile_`
9. 拼成格式：`sessionId=xxx;_login_user_id_=xxx;_login_mobile_=xxx`

## 保活模式

session 过期的主要原因是"长期不活跃"。保活模式每天只做一次轻量的积分查询请求，模拟用户活跃，从而延长 session 有效期。

**推荐配置**：
```
主任务（每天1次完整签到）：
  cron: 51 8 * * *
  正常模式

保活任务（每天2次维持session）：
  cron: 0 12,20 * * *
  SF_KEEPALIVE=true
```

> 💡 每天 3 次活跃，session 基本可以维持 7-14 天甚至更久。

## WxPusher 推送

过期了自动发微信提醒，再也不会漏掉签到。

1. 访问 [WxPusher 官网](https://wxpusher.zjiecode.com/admin/) 注册
2. 创建应用，获取 `APP_TOKEN`
3. 关注应用后获取 `UID`
4. 在青龙环境变量中配置：
   - `WXPUSHER_APP_TOKEN` = 你的 APP_TOKEN
   - `WXPUSHER_UIDS` = 你的 UID

## 青龙面板部署

1. 新建脚本 `sfsy.py`，粘贴代码
2. 添加环境变量 `sfsyUrl`
3. 添加定时任务：`task sfsy.py`
4. （可选）配置保活任务，设置 `SF_KEEPALIVE=true`

## 本地运行

```bash
pip install requests
export sfsyUrl="sessionId=xxx;_login_user_id_=xxx;_login_mobile_=xxx"
python sfsy.py
```

## 免责声明

本项目仅供学习交流使用，请勿用于商业用途。使用本脚本造成的任何后果由使用者自行承担。
