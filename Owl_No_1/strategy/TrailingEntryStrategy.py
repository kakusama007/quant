import time
from logger.log import log_info, log_error, log_warn


class TrailingEntryStrategy:
    """
        策略名称：TrailingEntryStrategy（移动止损跟踪建仓策略）

        策略逻辑：
            1. 设置杠杆和模式；
            2. 挂一个触发式的开仓单（达到触发价格后以市价开多/空）；
            3. 轮询检查是否持仓；
            4. 持仓建立后，挂一个移动止损单（trailing stop）用于自动平仓。
        """
    def __init__(self, exchange, symbol, amount, leverage, margin_mode, direction, trigger_price, trailing_percent):
        """
               初始化策略参数

               :param exchange: CCXT 交易所对象
               :param symbol: 交易对，例如 'BTC/USDT:USDT'
               :param amount: 开仓数量（单位：合约张数）
               :param leverage: 杠杆倍数
               :param margin_mode: 保证金模式：'isolated'（逐仓） 或 'cross'（全仓）
               :param direction: 方向，'long'（做多） 或 'short'（做空）
               :param trigger_price: 触发开仓的价格
               :param trailing_percent: 回撤比例（百分比），用于移动止损
               """

        self.exchange = exchange
        self.symbol = symbol                        # 'BTC/USDT:USDT'
        self.symbol_okx = symbol if symbol == 'BTC-USDT-SWAP' else symbol.replace('/', '-').replace(':USDT', '') + '-SWAP'
        # print(self.symbol_okx)
        # # exit()
        self.amount = amount
        self.leverage = leverage
        self.margin_mode = margin_mode              # 'isolated' or 'cross'
        self.direction = direction                  # 'long' or 'short'
        self.trigger_price = trigger_price
        self.trailing_percent = trailing_percent
        # 仓位方向（long 或 short）
        self.pos_side = 'long' if direction == 'long' else 'short'
        # 开仓方向（买/卖）
        self.open_side = 'buy' if direction == 'long' else 'sell'
        # 平仓方向（与开仓相反）
        self.close_side = 'sell' if direction == 'long' else 'buy'

    def set_leverage(self):
        log_info(f"⚙️ 设置杠杆为 {self.leverage}x")
        self.exchange.set_margin_mode(self.margin_mode,self.symbol,
                                 {'leverage': self.leverage, 'posSide': self.pos_side})

    def cancel_trailing_orders(self):
        log_info("🧹 清理未触发的移动止损挂单...")
        try:
            orders = self.exchange.private_get_trade_orders_algo_pending({
                'instType': 'SWAP',
                'instId': self.symbol_okx,
                'ordType': 'move_order_stop'
            })
            for order in orders['data']:
                if order['posSide'] == self.pos_side:
                    log_info(f"❌ 取消挂单:{order['algoId']}")
                    self.exchange.private_post_trade_cancel_algos({
                        'algoId': order['algoId'],
                        'instId': self.symbol_okx
                    })
        except Exception as e:
            log_error(f"⚠️ 清理挂单失败:{str(e)}")

    def place_trigger_entry_order(self):
        """
        挂一个触发开仓单（达到 trigger_price 后，以市价买入或卖出）
        """
        # self.cancel_trailing_orders()
        log_info(f"🔔 挂触发型开{'空' if 'short'==self.pos_side else '多'}仓订单...")
        order = self.exchange.create_order(
            symbol=self.symbol,
            # 当市场价格达到 triggerPrice 时，才会触发实际下单（用 ordType 决定是限价还是市价）
            type='trigger', # 使用触发单类型 “计划委托”/“触发单
            # type='market', # 市价
            side=self.open_side,
            amount=self.amount,
            price=None,# 触发后市价成交
            params={
                'tdMode': self.margin_mode,
                'ordType': 'market', # 触发后以市价下单
                'posSide': self.pos_side,
                # buy	做多/平空	当前价格（默认是标记价）≥ triggerPrice
                # sell	做空/平多	当前价格（默认是标记价）≤ triggerPrice
                'triggerPrice': self.trigger_price,# 到这个价格时才触发下单
                'triggerType': 'mark', # 使用标记价格作为触发依据，更稳定
                'reduceOnly': False # 开仓单必须为 False
            }
        )
        log_info(f"✅ 触发开{'空' if 'short'==self.pos_side else '多'}仓单挂好了，订单 ID:{order['id']}")
        # return order
        # order_detail = self.exchange.fetch_order(order['id'], self.symbol)
        # return order_detail
        return order

    def wait_for_position(self):
        log_info("⏳ 等待仓位建立...")
        while True:
            positions = self.exchange.fetch_positions([self.symbol])
            for p in positions:
                # if p['side'] == self.pos_side and float(p['contracts']) >= self.amount:
                if float(p['contracts']) >= self.amount:
                    log_info(f"✅ 检测到 {'空' if 'short' == self.pos_side else '多'} 仓建立，准备挂追踪止损...")
                    return
            log_info("⏳ 仓位尚未建立，继续等待...")
            time.sleep(3)

    def place_trailing_stop(self):
        """
        创建移动止损订单：
        - trailingPercent: 回撤百分比
        - trailingTriggerPrice: 触发该订单的价格（达到后才激活 trailing 逻辑）
        """

        log_info("🎯 创建追踪止损...")
        order = self.exchange.create_trailing_percent_order(
            symbol=self.symbol,
            type='market',  # 一旦触发就市价止损
            side=self.close_side,# 平仓方向
            amount=self.amount,
            trailingPercent=self.trailing_percent,
            trailingTriggerPrice=self.trigger_price, # 如果不设置，默认立即激活移动止损。
            params={
                'tdMode': self.margin_mode,
                'posSide': self.pos_side,
                'reduceOnly': True,  # 仅用于平仓
                # 'triggerType': 'mark'  # 使用标记价格触发
            }
        )
        log_info(f"✅ 追踪止损挂单成功，订单 ID:{order['id']}，触发价格{self.trigger_price}")
        # order_detail = self.exchange.fetch_order(order['id'], self.symbol)
        return order
        # return order_detail

    def run(self):
        """
        策略主入口，按顺序执行：
        1. 设置杠杆；
        2. 挂触发开仓单；
        3. 等仓位建立；
        4. 挂移动止损平仓单。
        """

        # 1. 判断是否已有持仓
        log_info(f"🔍 检查是否已有{'空' if 'short'==self.pos_side else '多'}仓...")
        try:
            positions = self.exchange.fetch_positions([self.symbol])
            for p in positions:
                if p['side'] == self.pos_side and float(p['contracts']) > 0:

                    log_warn(f"🚫 已经持有{'空' if 'short'==self.pos_side else '多'}仓，策略终止。")
                    return None, None
        except Exception as e:
            log_error(f"❌ 查询持仓失败: {e}")
            return None, None

        self.set_leverage()
        trigger_entry_order = self.place_trigger_entry_order()
        self.wait_for_position()
        trailing_stop_order = self.place_trailing_stop()
        return trigger_entry_order, trailing_stop_order



# 创建策略实例
# strategy = TrailingEntryStrategy(
#     exchange=get_exchange(),
#     symbol='BTC/USDT:USDT',
#     amount=0.1,
#     leverage=10,
#     margin_mode='isolated',
#     direction='short',              # 'long' or 'short'
#     trigger_price=107800,
#     trailing_percent=0.1
# )

# 执行策略
# strategy.run()