#!/bin/bash
# 🚀 一键部署 Sentinel-2 行情异动监控服务
# ✅ 支持 Alibaba Cloud Linux 3.2104 LTS x64

set -e

# 项目变量
PROJECT_NAME="sentinel_2"

# 路径变量
PROJECT_DIR="$(pwd)"
PYTHON_VERSION="3.12.1"
PYTHON_BIN="python3.12"
PYTHON_SRC_DIR="/usr/local/src/Python-$PYTHON_VERSION"
PYTHON_TGZ="Python-$PYTHON_VERSION.tgz"
VENV_DIR="$PROJECT_DIR/venv"
LOG_DIR="$PROJECT_DIR/logs"
ENV_FILE="$PROJECT_DIR/.env"
REQUIREMENTS_FILE="$PROJECT_DIR/requirements.txt"

SUPERVISOR_CONF="/etc/supervisord.d/${PROJECT_NAME}.ini"
MAIN_SCRIPT="$PROJECT_DIR/main.py"
USER=$(whoami)

echo "📁 当前部署目录: $PROJECT_DIR"

# 1. 安装系统依赖
echo "📦 安装系统依赖..."
sudo yum install -y gcc make zlib-devel bzip2 bzip2-devel readline-devel sqlite sqlite-devel openssl-devel libffi-devel curl

# 2. 安装 Python 3.12.1（如果未安装）
if ! command -v $PYTHON_BIN &> /dev/null; then
    echo "📥 Python $PYTHON_VERSION 未检测到，开始安装..."
    cd /usr/local/src
    if [ ! -f "$PYTHON_TGZ" ]; then
        sudo curl -O https://www.python.org/ftp/python/$PYTHON_VERSION/$PYTHON_TGZ
    fi
    if [ ! -d "$PYTHON_SRC_DIR" ]; then
        sudo tar -xzf $PYTHON_TGZ
    fi
    cd "$PYTHON_SRC_DIR"
    sudo ./configure --enable-optimizations
    sudo make -j$(nproc)
    sudo make altinstall
    cd "$PROJECT_DIR"
else
    echo "✅ Python $PYTHON_VERSION 已安装"
fi

# 3. 创建虚拟环境
if [ ! -d "$VENV_DIR" ]; then
    echo "🧪 创建虚拟环境 venv..."
    $PYTHON_BIN -m venv "$VENV_DIR"
fi

# 4. 安装依赖
source "$VENV_DIR/bin/activate"
echo "📦 安装 Python 包依赖..."
pip install --upgrade pip
if [ ! -f "$REQUIREMENTS_FILE" ]; then
    cat > "$REQUIREMENTS_FILE" <<EOF
ccxt
requests
python-dotenv
EOF
fi
pip install -r "$REQUIREMENTS_FILE"

# 5. 创建日志目录
mkdir -p "$LOG_DIR"

# 6. 生成 .env 文件（如不存在）
if [ ! -f "$ENV_FILE" ]; then
    echo "📝 创建 .env 文件..."
    cat > "$ENV_FILE" <<EOF
# Sentinel-2 配置
BACKUP_DOMAIN=www.chouyi.tv
TIMEFRAME=1m
CHECK_INTERVAL=30
BTC_THRESHOLD=0.002
ETH_THRESHOLD=0.0045
WANT_FETCH_CANDLES=3
NOTICE_TITLE="Sentinel-2 行情异动监控"
SENDKEY=your_serverchan_key_here
EOF
else
    echo "⚠️ .env 文件已存在，未覆盖"
fi

# 7. 安装 Supervisor（如果没装）
if ! command -v supervisord &> /dev/null; then
    echo "🛠️ 安装 Supervisor..."
    sudo yum install -y supervisor
    [ ! -d "/etc/supervisord.d" ] && sudo mkdir -p /etc/supervisord.d
    sudo systemctl enable supervisord
    sudo systemctl start supervisord
else
    echo "✅ Supervisor 已安装"
fi

# 8. 写入 Supervisor 配置文件
echo "🧩 写入 Supervisor 配置: $SUPERVISOR_CONF"
sudo bash -c "cat > $SUPERVISOR_CONF" <<EOF
[program:$PROJECT_NAME]
command=$VENV_DIR/bin/python $MAIN_SCRIPT
directory=$PROJECT_DIR
autostart=true
autorestart=true
stdout_logfile=$LOG_DIR/out.log
stderr_logfile=$LOG_DIR/err.log
user=$USER
environment=PYTHONUNBUFFERED=1
EOF

# 9. 启动 Supervisor 任务
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl restart $PROJECT_NAME || true

# 10. 完成提示
echo -e "\n✅ $PROJECT_NAME 部署完成"
echo "🛠️ 查看运行日志: tail -f $LOG_DIR/out.log"
echo "📘 Python 日志文件: $LOG_DIR/sentinel.log"
