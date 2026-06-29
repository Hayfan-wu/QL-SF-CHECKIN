#!/bin/bash
# ============================================================
# 顺丰 sfsyUrl 远程更新服务 - 一键部署脚本
# 适用于 Linux (Debian/Ubuntu/CentOS/OpenWrt 等)
# ============================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}"
echo "============================================"
echo "  顺丰 sfsyUrl 远程更新服务 - 部署脚本"
echo "============================================"
echo -e "${NC}"

# 默认安装目录
INSTALL_DIR="/root/sf"

# 检查 Python3
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ 未找到 python3，请先安装 Python 3${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Python3 已安装: $(python3 --version)${NC}"

# 检查 pip
if ! python3 -m pip --version &> /dev/null; then
    echo -e "${YELLOW}⚠️  pip 未安装，正在安装...${NC}"
    if command -v apt-get &> /dev/null; then
        apt-get update && apt-get install -y python3-pip
    elif command -v yum &> /dev/null; then
        yum install -y python3-pip
    else
        echo -e "${RED}❌ 无法自动安装 pip，请手动安装${NC}"
        exit 1
    fi
fi
echo -e "${GREEN}✅ pip 已安装${NC}"

# 安装依赖
echo "📦 安装 Python 依赖..."
python3 -m pip install requests -q
echo -e "${GREEN}✅ 依赖安装完成${NC}"

# 创建安装目录
mkdir -p "$INSTALL_DIR"
echo "📁 安装目录: $INSTALL_DIR"

# 复制脚本文件
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -f "$SCRIPT_DIR/sf_wxpusher_update.py" ]; then
    cp "$SCRIPT_DIR/sf_wxpusher_update.py" "$INSTALL_DIR/"
    echo -e "${GREEN}✅ 脚本已复制${NC}"
else
    echo -e "${YELLOW}⚠️  未找到 sf_wxpusher_update.py，请手动复制到 $INSTALL_DIR/${NC}"
fi

# 检查环境变量文件
if [ ! -f "$INSTALL_DIR/.env" ]; then
    if [ -f "$SCRIPT_DIR/.env.example" ]; then
        cp "$SCRIPT_DIR/.env.example" "$INSTALL_DIR/.env"
        echo ""
        echo -e "${YELLOW}⚠️  请编辑配置文件: $INSTALL_DIR/.env${NC}"
        echo "   填写青龙地址、密钥和 WxPusher Token"
        echo ""
        read -p "按回车键继续..." -n1 -s
    fi
fi

# 检查 systemd
if command -v systemctl &> /dev/null; then
    echo ""
    echo "🔧 配置 systemd 服务..."
    
    # 复制 service 文件
    if [ -f "$SCRIPT_DIR/sf-wxpusher.service" ]; then
        cp "$SCRIPT_DIR/sf-wxpusher.service" /etc/systemd/system/
        echo -e "${GREEN}✅ systemd 服务文件已复制${NC}"
    else
        # 生成 service 文件
        cat > /etc/systemd/system/sf-wxpusher.service << EOF
[Unit]
Description=SF Express WxPusher Update Service
After=network.target
Wants=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$(which python3) $INSTALL_DIR/sf_wxpusher_update.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=sf-wxpusher

[Install]
WantedBy=multi-user.target
EOF
        echo -e "${GREEN}✅ systemd 服务文件已生成${NC}"
    fi
    
    # 重载 systemd
    systemctl daemon-reload
    
    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}🎉 部署完成！${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""
    echo "常用命令:"
    echo "  启动服务:  systemctl start sf-wxpusher"
    echo "  停止服务:  systemctl stop sf-wxpusher"
    echo "  重启服务:  systemctl restart sf-wxpusher"
    echo "  查看状态:  systemctl status sf-wxpusher"
    echo "  查看日志:  journalctl -u sf-wxpusher -f"
    echo "  开机自启:  systemctl enable sf-wxpusher"
    echo "  取消自启:  systemctl disable sf-wxpusher"
    echo ""
    echo -e "${YELLOW}⚠️  使用前请确保已编辑 $INSTALL_DIR/.env 配置文件${NC}"
    echo ""
    read -p "是否现在启动服务？(y/N) " -n1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        systemctl start sf-wxpusher
        sleep 2
        systemctl status sf-wxpusher --no-pager
    fi
else
    # 没有 systemd（如 OpenWrt）
    echo ""
    echo -e "${YELLOW}⚠️  检测到没有 systemd（可能是 OpenWrt 等系统）${NC}"
    echo ""
    echo "手动启动方式:"
    echo "  前台运行:  cd $INSTALL_DIR && python3 sf_wxpusher_update.py"
    echo "  后台运行:  cd $INSTALL_DIR && nohup python3 sf_wxpusher_update.py > sf.log 2>&1 &"
    echo "  查看日志:  tail -f $INSTALL_DIR/sf.log"
    echo ""
    echo "OpenWrt 开机自启:"
    echo "  在 /etc/rc.local 中添加:"
    echo "  cd $INSTALL_DIR && nohup python3 sf_wxpusher_update.py > sf.log 2>&1 &"
    echo ""
fi
