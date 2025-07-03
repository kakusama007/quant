# main.py
import smtplib
import time
import threading
import queue
import smtplib
from email.mime.text import MIMEText
from email.header import Header

import ccxt
import logging

import requests
from dotenv import load_dotenv
import os
from datetime import datetime

load_dotenv()

# 配置
BACKUP_DOMAIN = os.getenv("BACKUP_DOMAIN", 'www.chouyi.tv')
TIMEFRAME = os.getenv("TIMEFRAME", '1m')
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", '30'))
BTC_THRESHOLD = float(os.getenv("BTC_THRESHOLD", '0.002'))
ETH_THRESHOLD = float(os.getenv("ETH_THRESHOLD", '0.0045'))
WANT_FETCH_CANDLES = int(os.getenv("WANT_FETCH_CANDLES", '3'))
NOTICE_TITLE = os.getenv("NOTICE_TITLE", 'Sentinel-1 行情异动监控')

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT"]
THRESHOLDS = {
    "BTC": BTC_THRESHOLD,
    "ETH": ETH_THRESHOLD
}

# 日志配置
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(log_dir, "sentinel.log"), encoding='utf-8'),
        logging.StreamHandler()
    ]
)

notification_queue = queue.Queue()

exchange = ccxt.okx({
    "enableRateLimit": True,
    'hostname': BACKUP_DOMAIN,
    "options": {
        "defaultType": "swap"
    }
})

notifier_config = {
  'wechat': {
      'enable': True,
      'sendkeys': [
        os.getenv("WECHAT_SENDKEY1"),
        os.getenv("WECHAT_SENDKEY2")
      ]
  },
  'email': {
      'enable': True,
      'smtp_server': os.getenv("SMTP_SERVER"),
      'smtp_user': os.getenv("SMTP_USER"),
      'smtp_pass': os.getenv("SMTP_PASS"),
      'smtp_port': int(os.getenv("SMTP_PORT")),
      'to_emails': [
          os.getenv("TO_EMAIL2")
          , os.getenv("TO_EMAIL1")
      ]
  },
}
def fetch_kline(symbol):
    try:
        data = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=WANT_FETCH_CANDLES)
        if len(data) < 2:
            logging.warning(f"{symbol} K线不足2根")
            return None
        return data[-2]
    except Exception as e:
        logging.error(f"获取K线失败: {symbol} {e}")
        return None

def monitor():
    last_sent_msgs = {} # 存储已发送的警报，避免重复通知
    while True:
        current_alerts = {} # 当前周期检测到的警报
        for symbol in SYMBOLS:
            kline = fetch_kline(symbol)
            if kline:
                name = symbol.split("/")[0]
                quote_currency = symbol.split("/")[1].split(":")[0]
                open_, close_ = kline[1], kline[4]
                pct = (close_ - open_)*100 / open_
                threshold = THRESHOLDS.get(name)
                logging.info(
                    f"🚦 {datetime.fromtimestamp(kline[0] / 1000).strftime("%Y-%m-%d %H:%M:%S")}':"
                    f"{symbol}{'跌' if pct < 0 else '涨'}幅: {pct:.6f},阈值：{threshold}"
                )

                if threshold and abs(pct) >= abs(threshold):
                    alert_id = f"{symbol}_{open_}_{close_}"
                    # 检查是否是新行情（未在last_sent_msgs中）
                    if alert_id not in last_sent_msgs:
                        current_alerts[alert_id] = f'''
{'🪂📉' if pct < 0 else '🔥📈'}{symbol}波动行情{'📉🪂' if pct < 0 else '📈🔥'}
💰 开盘：{open_} {quote_currency} ↔️ 收盘：{close_} {quote_currency}
📊 行情:{'🚀暴涨：' if pct > 0 else '💣暴跌：'}{pct:.6%}（1分钟）{'🚀' if pct > 0 else '💣'}
⏰ 时间:{datetime.fromtimestamp(kline[0] / 1000).strftime("%Y-%m-%d %H:%M:%S")}
'''

        new_msg = '\n'.join(current_alerts.values())
        if new_msg:
            last_sent_msgs = {**last_sent_msgs, **current_alerts}
            last_sent_msgs = dict(list(last_sent_msgs.items())[-5:])
            notification_queue.put(new_msg)
            logging.info(f"【{NOTICE_TITLE}】\n{new_msg}")
        time.sleep(CHECK_INTERVAL)

def notify_worker():
    while True:
        msg = notification_queue.get()
        send_notification(msg)

def notify_email(subject, content):
    if not notifier_config['email']['enable']:
        return
    try:
        smtp_conf = notifier_config['email']
        msg = MIMEText(content, 'plain', 'utf-8')
        msg['From'] = smtp_conf['smtp_user']
        msg['To'] = ','.join(smtp_conf['to_emails'])
        msg['Subject'] = Header(subject, 'utf-8')

        smtp = smtplib.SMTP_SSL(smtp_conf['smtp_server'], smtp_conf['smtp_port'])
        smtp.login(smtp_conf['smtp_user'], smtp_conf['smtp_pass'])
        smtp.sendmail(smtp_conf['smtp_user'], smtp_conf['to_emails'], msg.as_string())
        smtp.quit()
    except Exception as e:
        logging.error(f"邮件通知失败: {e}")

def notify_wechat(title,message):
    if notifier_config['wechat']['enable']:
        for key in notifier_config['wechat']['sendkeys']:
            try:
                url = f'https://sctapi.ftqq.com/{key}.send'
                requests.post(url, data={'title': title, 'desp': message})
            except Exception as e:
                logging.error(f"通知失败: {e}")


def send_notification(msg):
    try:
        title = f'📢🚨🚨{NOTICE_TITLE}通知🚨🚨🔊'
        logging.info(f"[{datetime.now()}] {title}: {msg}")
        notify_wechat(title,msg)
        notify_email(title, msg)
    except Exception as e:
        logging.error(f"通知失败: {e}")

if __name__ == "__main__":
    threading.Thread(target=notify_worker, daemon=True).start()
    monitor()