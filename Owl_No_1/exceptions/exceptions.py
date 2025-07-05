# exceptions.py

class AppError(Exception):
    """
    所有自定义异常的根基类（可统一 try/except 捕获）
    """
    def __init__(self, message=None, *, detail=None):
        self.message = message or self.__class__.__name__
        self.detail = detail
        super().__init__(self.message)

    def __str__(self):
        if self.detail:
            return f"{self.message} -> {self.detail}"
        return self.message


# ====================
# 通知相关异常
# ====================

class NotificationError(AppError):
    """所有通知系统相关错误的基类"""
    pass

# 企业微信专属
class WeChatNotifyError(NotificationError):
    """企业微信通知失败（总类）"""
    pass

class WeChatAccessTokenError(WeChatNotifyError):
    """获取 access_token 失败"""
    pass

class WeChatSendMessageError(WeChatNotifyError):
    """发送消息失败"""
    pass

class EmailNotifyError(NotificationError):
    """邮件通知失败"""
    pass

class ServerChanNotifyError(NotificationError):
    """Server酱通知失败"""
    pass

class TelegramNotifyError(NotificationError):
    """Telegram通知失败"""
    pass


# ====================
# API/数据抓取异常
# ====================

class APIRequestError(AppError):
    """外部 API 请求失败"""
    pass

class DataFetchError(AppError):
    """K线或行情数据获取失败"""
    pass


# ====================
# 配置/环境异常
# ====================

class ConfigError(AppError):
    """配置文件或环境变量问题"""
    pass

class AuthError(AppError):
    """身份验证失败，例如 APIKey 错误"""
    pass


# ====================
# 业务逻辑类异常（自定义）
# ====================

class StrategyError(AppError):
    """策略运行出错"""
    pass

class OrderExecutionError(AppError):
    """下单失败"""
    pass

class InsufficientBalanceError(AppError):
    """余额不足"""
    pass
