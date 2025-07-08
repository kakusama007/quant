# logger/log.py
import logging
from logging.handlers import TimedRotatingFileHandler
import os

log_dir = 'logs'
os.makedirs(log_dir, exist_ok=True)

log_path = os.path.join(log_dir, 'strategy.log')

# 日志自动分割，按天生成新文件，保留最近7天
handler = TimedRotatingFileHandler(log_path, when='midnight', interval=1, backupCount=7, encoding='utf-8')
handler.suffix = "%Y-%m-%d"
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(handler)

# 控制台输出
console = logging.StreamHandler()
console.setFormatter(formatter)
logger.addHandler(console)

def log_info(message):
    logger.info(message)

def log_warn(message):
    logger.warning(message)

def log_error(message):
    logger.error(message)
