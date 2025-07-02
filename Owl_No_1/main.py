import os
import time
from datetime import datetime

import ccxt

from config import *
from strategy.TrailingEntryStrategy import TrailingEntryStrategy
from logger.log import log_info, log_warn, log_error
import requests
import smtplib
from email.mime.text import MIMEText
from email.header import Header

# 初始化交易所
exchange = None
sent_content = None


def fetch_ohlcv(symbol, timeframe='1m', limit=2):
    return exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)


def get_drop_percentage(ohlcv):
    open_price = ohlcv[1][1]  # 当前开盘价
    close_price = ohlcv[1][4]  # 当前收盘价
    pre_open = ohlcv[0][1]  # 前一分钟开盘价
    pre_close = ohlcv[0][4]  # 前一分钟收盘价
    print(f'前一分钟：{datetime.fromtimestamp(ohlcv[0][0] / 1000).strftime("%Y-%m-%d %H:%M:%S")}', pre_open, pre_close,
          f'{(pre_close - pre_open) / pre_open:.6f}')
    print(f'当前分钟：{datetime.fromtimestamp(ohlcv[1][0] / 1000).strftime("%Y-%m-%d %H:%M:%S")}', open_price,
          close_price, f'{(close_price - open_price) / open_price:.6f}')
    cur_drop_pct = (close_price - open_price) / open_price
    pre_drop_pct = (pre_close - pre_open) / pre_open
    return pre_drop_pct, cur_drop_pct


def has_position(pos_side):
    positions = exchange.fetch_positions([symbol])
    for p in positions:
        if p['side'] == pos_side and float(p['contracts']) > 0:
            return True
    return False


def notify_wechat(message):
    if notifier_config['wechat']['enable']:
        for key in notifier_config['wechat']['sendkeys']:
            try:
                url = f'https://sctapi.ftqq.com/{key}.send'
                requests.post(url, data={'title': '量化策略通知', 'desp': message})
            except Exception as e:
                log_warn(f"微信通知失败: {e}")


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
        log_warn(f"邮件通知失败: {e}")


def mask_sensitive(data):
    if isinstance(data, str) and len(data) > 6:
        return data[:3] + '***' + data[-3:]
    return data


def format_placed_order(order):
    info = order.get('info', {})

    return {
        'symbol': order.get('symbol', 'N/A'),
        'type': ORDER_TYPE_MAPPING.get(order.get('type')) or '未知订单类型',

        'side': '📤 卖出(sell)' if order.get('side') == 'sell' else '📥 买入(buy)',

        # 订单 ID 优先使用 algoId 或 ordId，避免 None
        'id': mask_sensitive(
            order.get('id') or info.get('ordId') or info.get('algoId', 'N/A')
        ),

        'tag': info.get('tag', '无'),
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }


def format_template(data):
    return f"""
            🚀 交易通知: {data['side']}
            📈 交易对:{data['symbol']}
            🏷️ 标签: {data['tag']}
            🆔 订单ID: {data['id']}
            ⏰ 时间: {data['time']}
            """


def loop_strategy():
    sent_content = None
    while True:
        try:
            ohlcv = fetch_ohlcv(symbol)
            pre_drop, cur_drop = get_drop_percentage(ohlcv)
            log_info(
                f"🚦 前一分钟{'跌' if pre_drop < 0 else '涨'}幅: {pre_drop:.4f},阈值:{PRE_DROP_THRESHOLD / 100},差值：{pre_drop - PRE_DROP_THRESHOLD}")
            log_info(
                f"🚦 当前分钟{'跌' if cur_drop < 0 else '涨'}幅: {cur_drop:.4f},阈值：{CUR_DROP_THRESHOLD / 100},差值: {cur_drop - CUR_DROP_THRESHOLD}")
            # 只做空仓
            TRIGGER_DIRECTION = 'short'
            if pre_drop <= PRE_DROP_THRESHOLD / 100 and cur_drop <= CUR_DROP_THRESHOLD / 100:
                log_info("🔍 检测到连续跌幅超过阈值，准备检查是否已持仓...")
                if has_position(TRIGGER_DIRECTION):
                    log_warn(f"⚠️ 已持有{'多' if TRIGGER_DIRECTION != 'short' else '空'}仓，跳过下单")
                else:
                    log_info("🟢 满足建仓条件，执行策略...")
                    # macOS 播放声音
                    # os.system('say "满足建仓条件，执行策略"')
                    strategy = TrailingEntryStrategy(
                        exchange=exchange,
                        symbol=symbol,
                        amount=TRIGGER_AMOUNT,
                        leverage=TRIGGER_LEVERAGE,
                        margin_mode=TRIGGER_MARGIN_MODE,
                        direction=TRIGGER_DIRECTION,
                        trigger_price=ohlcv[1][4],
                        trailing_percent=TRIGGER_TRAILING_PERCENT
                    )
                    trigger_entry_order, trailing_stop_order = strategy.run()
                    content = format_template(format_placed_order(trigger_entry_order))
                    if sent_content != content:
                        sent_content = content
                        notify_wechat(f"📈 满足建仓条件，策略{NOTICE_TITLE}正在执行")
                        # notify_email(f"策略{NOTICE_TITLE}启动通知", "满足建仓条件，正在执行策略")
                        notify_email(f"策略{NOTICE_TITLE}启动通知", content)
            else:
                log_info("🟡 条件未满足，等待下一轮...")
        # exit()
        except Exception as e:
            log_error(f"❌ 策略轮询异常: {str(e)}")
            content = str(e)
            if sent_content != content:
                sent_content = content
                # notify_wechat(f"策略运行异常: {str(e)}")
                notify_email("🚨策略运行异常🚨", str(e))

        time.sleep(CHECK_INTERVAL)


if __name__ == '__main__':
    okx = ccxt.okx({
        'apiKey': apikey,
        'secret': secretkey,
        'password': passphrase,
        # 'hostname': 'www.chouyi.tv',
        'enableRateLimit': True,
        # 'test':True,
        # 'proxies': proxies,
        'options': {
            'sandboxMode': simulated,
            'adjustForTimeDifference': True,
            'defaultType': trade_type,  # 模拟盘模式 spot 现货  swap 永续合约
        },
    })
    okx.hostname = backup_domain
    # okx.set_sandbox_mode(simulated)
    exchange = okx
    log_info("🚀 初始化交易所完成，策略轮询开始...")

    loop_strategy()
