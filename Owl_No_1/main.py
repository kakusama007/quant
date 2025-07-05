import json
import time
from datetime import datetime

import ccxt

from config import *
from exceptions.exceptions import WeChatNotifyError, EmailNotifyError
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
    # :param int [limit]: the maximum amount of candles to fetch
    return exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)


def get_drop_percentage(ohlcv: object) -> object:
    pre_pre_open_price = ohlcv[0][1]  # 上上一分钟开盘价
    pre_pre_close_price = ohlcv[0][4]  # 上上一分钟收盘价

    pre_open = ohlcv[1][1]  # 前一分钟开盘价
    pre_close = ohlcv[1][4]  # 前一分钟收盘价
    pre_pre_drop_pct = (pre_pre_close_price - pre_pre_open_price) * 100 / pre_pre_open_price
    pre_drop_pct = (pre_close - pre_open) * 100 / pre_open
    log_info(
        f"🚦 前两分钟 {datetime.fromtimestamp(ohlcv[0][0] / 1000).strftime("%Y-%m-%d %H:%M:%S")}:{'跌' if pre_pre_drop_pct < 0 else '涨'}幅: {pre_pre_drop_pct:.6f},阈值:{PRE_PRE_DROP_THRESHOLD}")
    log_info(
        f"🚦 前一分钟 {datetime.fromtimestamp(ohlcv[1][0] / 1000).strftime("%Y-%m-%d %H:%M:%S")}':{'跌' if pre_drop_pct < 0 else '涨'}幅: {pre_drop_pct:.6f},阈值：{PRE_DROP_THRESHOLD}")

    return pre_pre_drop_pct, pre_drop_pct


def has_position(pos_side):
    log_info("🔍 持仓情况检查...")
    positions = exchange.fetch_positions([symbol])
    for p in positions:
        if p['side'] == pos_side and float(p['contracts']) > 0:
            return True
    return False


def notify_wechat(title,message):
    if notifier_config['wechat']['enable']:
        for key in notifier_config['wechat']['sendkeys']:
            try:
                url = f'https://sctapi.ftqq.com/{key}.send'
                requests.post(url, data={'title': title, 'desp': message})
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
    except EmailNotifyError as e:
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


def check_swap_margin(exchange, symbol, amount, leverage=20, margin_mode='isolated'
                      , pos_side='short', safety_factor=1.1, contract_size=0.01):
    """
    检查 OKX 永续合约下单前是否有足够保证金资金。

    参数：
        exchange     - ccxt.okx() 实例
        symbol       - 交易对，如 'BTC/USDT:USDT'
        amount       - 想要买入或卖出的 BTC 数量
        leverage     - 杠杆倍数（默认20倍）
        pos_side     - 仓位方向默认空仓 short
        margin_mode  - 'isolated' or 'cross'

    报错：
        如果保证金不足会 raise ValueError
        所需保证金=下单数量×价格/杠杆倍数
    """
    # 获取合约信息（如果需要合约面值）
    if contract_size is None:
        markets = exchange.load_markets()
        if symbol in markets:
            contract_size = markets[symbol].get('contractSize', 1.0)
        else:
            log_warn(f"无法获取合约信息: {symbol}")
            raise ValueError(f"无法找到市场信息: {symbol}")

    # 获取当前最新价格
    ticker = exchange.fetch_ticker(symbol)
    # 买入使用卖一价 Ask（卖一价）# Bid（买一价）做多用 ask，做空用 bid
    # Ask（卖价/卖一价）：卖方愿意接受的最低价格，即市场上卖单的最低价。
    # Bid（买价/买一价）：买方愿意支付的最高价格，即市场上买单的最高价。
    price = ticker['bid'] if pos_side == 'short' else ticker['ask']
    # markPrice = ticker['markPrice']  # 标记价格 交易所用来计算爆仓和平仓的参考价格，目的是防止因交易所行情异常而导致不合理爆仓。
    # 计算预估保证金 = 合约面值 * 张数 * 价格 / 杠杆
    required_margin = contract_size * amount * price / leverage
    required_margin *= safety_factor  # 加安全系数

    quote = symbol.split('/')[1].split(':')[0]  # 提取出 USDT

    if margin_mode == 'cross':
        balance = exchange.fetch_balance({'type': trade_type})
    else:  # isolated 或默认
        balance = exchange.fetch_balance()
    free = balance[quote]['free']

    if free < required_margin:
        raise ValueError(f"❌ 保证金不足：大约需要 {required_margin:.2f} {quote}，但只有 {free:.2f} {quote}")
    else:
        log_info(f"✅ 保证金充足：下单大约需要 {required_margin:.2f} {quote}，可用 {quote} 为 {free:.2f}")


def send_wechat(title,content):
    if not WECHAT_WEBHOOK:
        log_error(f"⚠️微信通知失败,WECHAT_WEBHOOK发送失败!")
    else:
        headers = {'Content-Type': 'application/json'}
        markdown_content = f"""# {title}\n{content}"""
        # payload = {
        #     "msgtype": "markdown",
        #     "markdown": {
        #         # "content": f"**{title}：**\n\n{text}"
        #         "content": markdown_content
        #         # , "mentioned_list":"@all"
        #     }
        payload = {
            "msgtype": "text",
            "text": {
                "content": f"{title}\n{content}",
                "mentioned_list": ["@all"]
            }
        }
        try:
            r = requests.post(WECHAT_WEBHOOK, data=json.dumps(payload), headers=headers)
            r.raise_for_status()
        except WeChatNotifyError as e:
            log_error(f"微信通知失败: {e}")

def loop_strategy():
    sent_content = None
    while True:
        try:
            #  1.先配置 不然获取不了数据  'sandboxMode': simulated,
            ohlcv = fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=want_fetch_candles)

            #  2.解决模拟环境异常 okx {"msg":"APIKey does not match current environment.","code":"50101"}
            # exchange.set_sandbox_mode(simulated)
            if len(ohlcv) < 1:
                log_error('⚠️ 数据抓取失败跳过执行')
            else:
                pre_pre_drop_pct, pre_drop_pct = get_drop_percentage(ohlcv)

                if pre_pre_drop_pct <= PRE_PRE_DROP_THRESHOLD and pre_drop_pct <= PRE_DROP_THRESHOLD:

                    log_info("🔍 检测到连续跌幅超过阈值，准备检查是否已持仓...")

                    if has_position(TRIGGER_DIRECTION):
                        log_warn(f"⚠️ 已持有{'多' if TRIGGER_DIRECTION != 'short' else '空'}仓，跳过下单")
                    else:

                        log_info("🔍 准备资金检查...")
                        # 资金检查
                        check_swap_margin(exchange, symbol, TRIGGER_AMOUNT
                                          , leverage=TRIGGER_LEVERAGE
                                          , margin_mode=TRIGGER_MARGIN_MODE
                                          , pos_side=TRIGGER_DIRECTION
                                          , safety_factor=BALANCE_CHECK_SECURITY_FACTOR,
                                          contract_size=contract_size
                                          )

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
                            trigger_price=ohlcv[2][4],
                            trailing_percent=TRIGGER_TRAILING_PERCENT
                        )
                        trigger_entry_order, trailing_stop_order = strategy.run()
                        content = format_template(format_placed_order(trigger_entry_order))
                        if sent_content != content:
                            sent_content = content
                            title = f"【{NOTICE_TITLE}】启动通知"
                            send_wechat(title,content)
                            # notify_wechat(title, content)
                            notify_email(title, content)
                else:
                    log_info("🟡 条件未满足，等待下一轮...")
                # exit()

        except ValueError as e:
            log_info(f"【{NOTICE_TITLE}】资金不足警告 {e}")
            content = str(e)
            if sent_content != content:
                sent_content = content
                send_wechat(f"⚠️💰【{NOTICE_TITLE}】资金不足警告💰⚠️",content)
                # notify_wechat(f"策略运行异常: {str(e)}")
                notify_email(f"⚠️💰【{NOTICE_TITLE}】资金不足警告💰⚠️", str(e))
        except WeChatNotifyError as e:
            log_info(f"微信通知失败 {e}")

        except Exception as e:
            log_error(f"❌ 【{NOTICE_TITLE}】轮询异常: {str(e)}")
            content = str(e)
            if sent_content != content:
                sent_content = content
                send_wechat(f"🚨【{NOTICE_TITLE}】运行异常🚨",content)
                # notify_wechat(f"策略运行异常: {str(e)}")
                notify_email(f"🚨【{NOTICE_TITLE}】运行异常🚨", content)

        time.sleep(CHECK_INTERVAL)


if __name__ == '__main__':
    # symbol = 'BTC/USDT:USDT'  # swap 永续合约标准格式
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
    exchange = okx
    log_info("🚀 初始化交易所完成，策略轮询开始...")

    # ohcv = exchange.fetch_ohlcv(symbol, timeframe='1m', limit=2)
    #
    # print(ohcv,len(ohcv)<1)
    # #这个set_sandbox_mode和 'sandboxMode': simulated, 会影响fetch_ohlcv和fetch_balance查询数据
    okx.set_sandbox_mode(simulated)

    # balance = exchange.fetch_balance()
    # print('balance', balance)
    # print(f"balance 可用余额:{balance['free']} ")
    # print(f"balance 已被占用的金额（用于挂单、保证金等）:{balance['used']} ")
    # print(f"balance 	总资产 :{balance['total']} ")

    # btc_amount = balance['BTC']['free']
    # # market = exchange.market('BTC/USDT')
    # market = exchange.market(symbol)  # 即 'BTC/USDT:USDT'
    #
    # min_amount = market['limits']['amount']['min']
    # if btc_amount < min_amount:
    #     raise ValueError(f"余额不足，最小交易量为 {min_amount} BTC")

    # print(f"market {market} ")
    # print(f"symbol {symbol} ")
    # print(f"btc_amount {btc_amount} ")
    # print(f"market 最小交易量为：{min_amount} BTC")

    loop_strategy()
