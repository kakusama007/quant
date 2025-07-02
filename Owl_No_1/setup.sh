#!/bin/bash
# 🚀 一键部署 Owl_No_1 量化策略服务
# ✅ 支持 Alibaba Cloud Linux 3.2104 LTS x64

set -e

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

# 重点修改1：Supervisor 配置路径（Alibaba Cloud Linux 3常用）
SUPERVISOR_CONF="/etc/supervisord.d/owl_no_1.ini"

MAIN_SCRIPT="$PROJECT_DIR/main.py"
USER=$(whoami)

echo "📁 当前部署目录: $PROJECT_DIR"

# 1. 安装系统依赖（跳过 epel-release，防冲突）
echo "📦 安装系统依赖（跳过 epel-release）..."
sudo yum install -y gcc make zlib-devel bzip2 bzip2-devel readline-devel sqlite sqlite-devel openssl-devel libffi-devel curl

# 2. 安装 Python 3.12.1（如果未安装）
if ! command -v $PYTHON_BIN &> /dev/null; then
    echo "📥 Python $PYTHON_VERSION 未检测到，开始编译安装..."
    cd /usr/local/src
    # 重点修改2：加判断避免重复下载源码包
    if [ ! -f "$PYTHON_TGZ" ]; then
        echo "🌐 正在下载 Python 源码..."
        sudo curl -O https://www.python.org/ftp/python/$PYTHON_VERSION/$PYTHON_TGZ
    else
        echo "✅ 已有 Python 源码包，跳过下载"
    fi

    if [ ! -d "$PYTHON_SRC_DIR" ]; then
        sudo tar -xzf $PYTHON_TGZ
    else
        echo "✅ 已有 Python 源码目录，跳过解压"
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

# 4. 安装 Python 依赖
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

# 6. 生成 .env 配置（如果不存在）
if [ ! -f "$ENV_FILE" ]; then
  echo "📝 创建 .env 文件..."
  cat > "$ENV_FILE" <<EOF
API_KEY="your_api_key"
SECRET_KEY="your_secret_key"
PASSPHRASE="your_passphrase"
BACKUP_DOMAIN="www.chouyi.tv"
SYMBOL="BTC/USDT:USDT"
EOF
else
  echo "⚠️ .env 文件已存在，未覆盖"
fi

# 7. 安装 Supervisor（如果没装）
if ! command -v supervisord &> /dev/null; then
    echo "🛠️ 安装 Supervisor..."
    sudo yum install -y supervisor
    # 重点修改3：确保 Supervisor 配置目录存在
    if [ ! -d "/etc/supervisord.d" ]; then
        echo "📂 创建 Supervisor 配置目录 /etc/supervisord.d"
        sudo mkdir -p /etc/supervisord.d
    fi
    sudo systemctl enable supervisord
    sudo systemctl start supervisord
else
    echo "✅ Supervisor 已安装"
fi

# 8. 写入 Supervisor 配置文件
echo "🧩 写入 Supervisor 配置: $SUPERVISOR_CONF"
sudo bash -c "cat > $SUPERVISOR_CONF" <<EOF
[program:owl_no_1]
command=$VENV_DIR/bin/python $MAIN_SCRIPT
directory=$PROJECT_DIR
autostart=true
autorestart=true
stdout_logfile=$LOG_DIR/out.log
stderr_logfile=$LOG_DIR/err.log
user=$USER
environment=PYTHONUNBUFFERED=1
EOF

# 9. 让 Supervisor 重新加载配置并启动程序
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl restart owl_no_1 || true

# 10. 完成提示
echo -e "\n✅ 量化脚本部署完成"
echo "🛠️ 可使用如下命令查看日志："
echo "   tail -f $LOG_DIR/out.log"
echo "📂 项目路径: $PROJECT_DIR"
echo "📦 虚拟环境: $VENV_DIR"
echo "📄 Supervisor 配置: $SUPERVISOR_CONF"
