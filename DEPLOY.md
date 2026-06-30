# 顺丰签到机器人 - 详细部署指南

本文档详细介绍如何在小主机（Linux）上部署顺丰签到机器人。

---

## 目录

1. [准备工作](#1-准备工作)
2. [上传文件](#2-上传文件)
3. [配置环境变量](#3-配置环境变量)
4. [安装依赖](#4-安装依赖)
5. [部署服务](#5-部署服务)
6. [验证运行](#6-验证运行)
7. [使用指南](#7-使用指南)
8. [常见问题](#8-常见问题)

---

## 1. 准备工作

### 1.1 系统要求

- 操作系统：Linux（Debian/Ubuntu/CentOS/OpenWrt 等）
- Python 3.6+
- 已安装青龙面板

### 1.2 需要准备的信息

| 信息 | 说明 | 在哪里获取 |
|------|------|-----------|
| 青龙面板地址 | `http://127.0.0.1:5700` | 本机部署用 127.0.0.1 |
| 青龙 Client ID | 青龙 Open API 密钥 | 见下方说明 |
| 青龙 Client Secret | 青龙 Open API 密钥 | 见下方说明 |
| WxPusher AppToken | 微信推送用 | 见下方说明 |
| WxPusher 用户 UID | 你的用户 ID | 见下方说明 |

### 1.3 获取青龙 Open API 密钥

1. 打开青龙面板 → 系统设置 → 应用设置
2. 点击「新建应用」
3. 填写名称：`sf-bot`
4. 权限：勾选「环境变量」的「查看」和「编辑」
5. 点击确定，保存生成的 `Client ID` 和 `Client Secret`

### 1.4 注册 WxPusher

1. 访问 https://wxpusher.zjiecode.com/admin/
2. 微信扫码登录
3. 点击「应用信息」→「新建应用」
4. 填写应用名称：顺丰签到机器人
5. 创建后复制 `APP_TOKEN`
6. 点击「用户管理」→ 扫描二维码关注
7. 关注后复制你的 `UID`

---

## 2. 上传文件

### 2.1 需要上传的文件

从 GitHub 下载或直接从仓库复制以下文件：

```
sf_bot.py          # 机器人主程序
sf-bot.service     # systemd 服务配置
.env.example       # 配置模板
```

仓库地址：https://github.com/Hayfan-wu/QL-SF-CHECKIN

### 2.2 上传方式

#### 方式一：Git 克隆（推荐）

```bash
# 进入安装目录
cd /root

# 克隆仓库
git clone https://github.com/Hayfan-wu/QL-SF-CHECKIN.git sf

cd sf
```

#### 方式二：SFTP 上传

使用 WinSCP / FileZilla 等工具，将文件上传到 `/root/sf/` 目录。

#### 方式三：wget 下载

```bash
mkdir -p /root/sf && cd /root/sf

# 下载主程序
wget -O sf_bot.py https://raw.githubusercontent.com/Hayfan-wu/QL-SF-CHECKIN/main/sf_bot.py

# 下载配置模板
wget -O .env.example https://raw.githubusercontent.com/Hayfan-wu/QL-SF-CHECKIN/main/.env.example

# 下载 service 文件
wget -O sf-bot.service https://raw.githubusercontent.com/Hayfan-wu/QL-SF-CHECKIN/main/sf-bot.service
```

---

## 3. 配置环境变量

### 3.1 复制配置文件

```bash
cd /root/sf
cp .env.example .env
```

### 3.2 编辑配置文件

```bash
vi .env
```

### 3.3 最小配置（必须项）

至少需要配置以下内容：

```ini
# ========== 青龙面板配置（必填） ==========
QL_URL=http://127.0.0.1:5700
QL_CLIENT_ID=你的ClientID
QL_CLIENT_SECRET=你的ClientSecret

# ========== WxPusher 配置（微信推送 + 交互） ==========
WXPUSHER_APP_TOKEN=AT_你的AppToken
WXPUSHER_UIDS=UID_你的用户UID
```

### 3.4 完整配置说明

```ini
# 青龙面板地址（本机填 127.0.0.1）
QL_URL=http://127.0.0.1:5700

# 青龙 Open API 密钥
QL_CLIENT_ID=xxxxxxxxxxxxxxxxxxxx
QL_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 环境变量名（默认 sfsyUrl，不用改）
ENV_NAME=sfsyUrl

# WxPusher 应用 Token
WXPUSHER_APP_TOKEN=AT_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 允许操作的用户 UID（白名单，多个用逗号分隔）
# 建议配置，防止其他人操作
WXPUSHER_UIDS=UID_xxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 主题 ID（可选，推送到主题的所有用户）
WXPUSHER_TOPIC_IDS=

# 管理员 UID（默认为 WXPUSHER_UIDS）
ADMIN_UIDS=

# 企业微信 Webhook（可选，不需要就留空）
WECOM_WEBHOOK=

# 钉钉 Webhook（可选）
DINGTALK_WEBHOOK=
DINGTALK_SECRET=

# 飞书 Webhook（可选）
FEISHU_WEBHOOK=
FEISHU_SECRET=

# 消息轮询间隔（秒），默认 30 秒
POLL_INTERVAL=30

# 每日签到时间（24小时制）
CHECKIN_HOUR=8
CHECKIN_MINUTE=0
```

### 3.5 保存退出

按 `Esc`，输入 `:wq`，按回车保存退出。

---

## 4. 安装依赖

### 4.1 检查 Python

```bash
python3 --version
```

如果提示找不到 python3，先安装：

```bash
# Debian/Ubuntu
apt update && apt install -y python3 python3-pip

# CentOS
yum install -y python3 python3-pip

# OpenWrt
opkg update && opkg install python3 python3-pip
```

### 4.2 安装 Python 依赖

```bash
pip3 install requests
```

或者：

```bash
python3 -m pip install requests
```

---

## 5. 部署服务

### 5.1 先手动测试一下（可选，建议）

在配置 systemd 之前，先手动运行看看能不能正常启动：

```bash
cd /root/sf
python3 sf_bot.py
```

如果看到类似以下输出，说明配置正确：

```
============================================================
🤖 顺丰签到机器人 v2.0.0
============================================================
🔍 测试青龙连接...
✅ 青龙连接正常，当前 0 个账号
📨 推送渠道: WxPusher
💬 WxPusher 交互已启用

⏰ 签到时间: 每天 08:00
⏱️  轮询间隔: 30 秒
🚀 服务启动...
============================================================
```

按 `Ctrl + C` 停止。

### 5.2 安装 systemd 服务

```bash
# 复制 service 文件
cp /root/sf/sf-bot.service /etc/systemd/system/

# 重载 systemd
systemctl daemon-reload
```

### 5.3 启动服务

```bash
# 启动
systemctl start sf-bot

# 设置开机自启
systemctl enable sf-bot
```

### 5.4 查看状态

```bash
systemctl status sf-bot
```

正常应该显示 `active (running)`。

---

## 6. 验证运行

### 6.1 查看实时日志

```bash
journalctl -u sf-bot -f
```

按 `Ctrl + C` 退出查看。

### 6.2 查看最近日志

```bash
# 最近 50 行
journalctl -u sf-bot -n 50

# 最近 1 小时
journalctl -u sf-bot --since "1 hour ago"

# 今天的日志
journalctl -u sf-bot --since today
```

### 6.3 微信测试

打开 WxPusher 微信公众号，发送：

```
帮助
```

如果收到机器人回复的帮助信息，说明部署成功！

再发送：

```
状态
```

应该能看到系统状态信息。

---

## 7. 使用指南

### 7.1 添加账号

**方式一：直接发送 sfsyUrl/CK**

在 WxPusher 里直接粘贴你抓包得到的 CK：

```
sessionId=xxxxxxxxxxxx;_login_mobile_=13800138000;_login_user_id_=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

机器人会自动识别并添加。

**方式二：使用命令**

```
添加 sessionId=xxxxxxxxxxxx;_login_mobile_=13800138000;_login_user_id_=xxx
```

### 7.2 常用命令

| 命令 | 说明 |
|------|------|
| `帮助` | 查看所有命令 |
| `列表` | 查看所有账号 |
| `添加` + URL | 添加账号 |
| `删除` + 手机号 | 删除账号 |
| `替换` + URL | 全量替换 |
| `测试` | 测试所有账号有效性 |
| `签到` | 立即执行签到 |
| `积分` | 查询当前积分 |
| `状态` | 查看系统状态 |
| `版本` | 查看版本 |

### 7.3 每日签到

- 机器人会在每天配置的时间（默认 08:00）自动签到
- 签到结果会推送到所有已配置的渠道
- 如果你想手动触发，发送 `签到` 命令即可

---

## 8. 常见问题

### Q1: 启动失败，提示青龙连接失败

**原因**：青龙地址或密钥配置错误

**排查步骤**：
1. 确认青龙面板地址是否正确
   ```bash
   curl http://127.0.0.1:5700
   ```
2. 确认 Client ID 和 Secret 是否正确
3. 确认应用权限是否勾选了「环境变量」

### Q2: 微信发消息没反应

**原因**：WxPusher 配置错误或轮询间隔问题

**排查步骤**：
1. 确认 AppToken 是否正确
2. 确认 UID 是否正确配置在白名单里
3. 查看日志有没有收到消息
   ```bash
   journalctl -u sf-bot -f
   ```
4. 等待 30 秒（默认轮询间隔），不是实时的

### Q3: 签到失败，提示登录失效

**原因**：sfsyUrl 过期了

**解决方法**：
1. 重新抓包获取最新的 CK
2. 发送 `替换` + 新的 CK 给机器人
3. 或者删除失效账号后重新添加

### Q4: 如何修改签到时间

编辑 `.env` 文件：

```bash
vi /root/sf/.env
```

修改：

```ini
CHECKIN_HOUR=9    # 改成你想要的小时
CHECKIN_MINUTE=30 # 改成你想要的分钟
```

保存后重启服务：

```bash
systemctl restart sf-bot
```

### Q5: 如何添加多个推送渠道

在 `.env` 里配置多个渠道的 webhook 即可：

```ini
# WxPusher
WXPUSHER_APP_TOKEN=AT_xxx
WXPUSHER_UIDS=UID_xxx

# 企业微信（可选）
WECOM_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx

# 钉钉（可选）
DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=xxx
DINGTALK_SECRET=SECxxx

# 飞书（可选）
FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
```

重启服务生效：

```bash
systemctl restart sf-bot
```

### Q6: 如何停止/重启服务

```bash
# 停止
systemctl stop sf-bot

# 重启
systemctl restart sf-bot

# 取消开机自启
systemctl disable sf-bot
```

### Q7: OpenWrt 没有 systemd 怎么办

用 nohup 后台运行：

```bash
cd /root/sf
nohup python3 sf_bot.py > sf-bot.log 2>&1 &
```

设置开机自启，编辑 `/etc/rc.local`：

```bash
vi /etc/rc.local
```

在 `exit 0` 前添加：

```bash
cd /root/sf && nohup python3 sf_bot.py > sf-bot.log 2>&1 &
```

查看日志：

```bash
tail -f /root/sf/sf-bot.log
```

### Q8: 如何更新机器人版本

```bash
cd /root/sf

# 备份配置
cp .env .env.bak

# 拉取最新代码
git pull

# 或者手动下载最新的 sf_bot.py
wget -O sf_bot.py https://raw.githubusercontent.com/Hayfan-wu/QL-SF-CHECKIN/main/sf_bot.py

# 重启服务
systemctl restart sf-bot
```

---

## 9. 文件结构

部署完成后，目录结构如下：

```
/root/sf/
├── sf_bot.py          # 主程序
├── sf-bot.service     # systemd 配置
├── .env               # 配置文件（你自己的）
├── .env.example       # 配置模板
└── sf-bot.log         # 日志（OpenWrt 用 nohup 时才有）
```

---

## 10. 卸载

如果不想用了：

```bash
# 停止服务
systemctl stop sf-bot
systemctl disable sf-bot

# 删除服务文件
rm /etc/systemd/system/sf-bot.service
systemctl daemon-reload

# 删除程序文件
rm -rf /root/sf
```

---

有其他问题请查看日志：`journalctl -u sf-bot -f`
