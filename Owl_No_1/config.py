import os
from dotenv import load_dotenv
# 加载.env配置 pip3 install python-dotenv
load_dotenv()


# API 密钥配置
apikey = os.getenv("API_KEY")
secretkey = os.getenv("SECRET_KEY")
passphrase = os.getenv("PASSPHRASE")
# 是否模拟盘
simulated = os.getenv("SIMULATED", "True").lower() == "true"

# 备用域名
backup_domain = os.getenv("BACKUP_DOMAIN", "www.chouyi.tv")

# 策略相关配置
symbol = os.getenv("SYMBOL", "BTC/USDT:USDT")
trade_type = os.getenv("TRADE_TYPE", "swap")
contract_size = float(os.getenv("CONTRACT_SIZE", "0.01"))# 合约大小
timeframe = os.getenv("TIMEFRAME", "1m")
want_fetch_candles = int(os.getenv("WANT_FETCH_CANDLES", '3'))


# 策略参数
BALANCE_CHECK_SECURITY_FACTOR = float(os.getenv("BALANCE_CHECK_SECURITY_FACTOR", "1.1"))# 余额检查安全系数
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "10")) # 每?秒执行一次
PRE_DROP_THRESHOLD = float(os.getenv("PRE_DROP_THRESHOLD", "-0.1")) # 前一分钟跌幅1%
PRE_PRE_DROP_THRESHOLD = float(os.getenv("PRE_PRE_DROP_THRESHOLD", "-0.15"))# 前前跌幅1%
TRIGGER_DIRECTION = os.getenv("TRIGGER_DIRECTION", "short")# 开仓方向 long  short 当前已经固定空仓，这个配置无效
TRIGGER_MARGIN_MODE = os.getenv("TRIGGER_MARGIN_MODE", "isolated")# 保证金模式 逐仓模式 (isolated)	全仓模式 (cross)
TRIGGER_AMOUNT = int(os.getenv("TRIGGER_AMOUNT", "1"))# 开仓数量（单位：合约张数）
TRIGGER_LEVERAGE = int(os.getenv("TRIGGER_LEVERAGE", "10"))# 杠杆
TRIGGER_TRAILING_PERCENT = float(os.getenv("TRIGGER_TRAILING_PERCENT", "0.05"))# 回撤百分比（%） 1%  1000+-

# 通知配置
NOTICE_TITLE = os.getenv("NOTICE_TITLE", "猫头鹰1号")

# 创建订单类型映射字典
ORDER_TYPE_MAPPING = {
    'market': '市价单，仅适用于币币/杠杆/交割/永续',
    'limit': '限价单',
    'post_only': '只做maker单',
    'fok': '全部成交或立即取消',
    'ioc': '立即成交并取消剩余',
    'optimal_limit_ioc': '市价委托立即成交并取消剩余（仅适用交割、永续）',
    'mmp': '做市商保护(仅适用于组合保证金账户模式下的期权订单)',
    'mmp_and_post_only': '做市商保护且只做maker单(仅适用于组合保证金账户模式下的期权订单)'
}

notifier_config = {
  'wechat': {
      'enable': os.getenv("ENABLE_WECHAT", "True").lower() == "true",
      'sendkeys': [
        os.getenv("WECHAT_SENDKEY1"),
        os.getenv("WECHAT_SENDKEY2")
      ]
  },
  'email': {
      'enable': os.getenv("ENABLE_EMAIL", "True").lower() == "true",
      'smtp_server': os.getenv("SMTP_SERVER"),
      'smtp_user': os.getenv("SMTP_USER"),
      'smtp_pass': os.getenv("SMTP_PASS"),
      'smtp_port': int(os.getenv("SMTP_PORT")),
      'to_emails': [
          os.getenv("TO_EMAIL1")
          , os.getenv("TO_EMAIL2")
      ]
  },
}
#
# 类型：轻量应用服务器（Linux）
# 系统：Ubuntu 22.04
# 推荐厂商（国内访问OKX网站无问题）：
# 阿里云轻量应用服务器
# 腾讯云轻量服务器
# 推荐配置：
# CPU：2核
# 内存：2G
# 硬盘：40G SSD
# 带宽：1～5Mbps
