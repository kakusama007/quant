import os
import requests
import time
import smtplib
from collections import defaultdict, deque
from typing import Dict, List
from email.mime.text import MIMEText
from email.header import Header

from dotenv import load_dotenv

from logger.log import *

# 加载.env配置 pip3 install python-dotenv
load_dotenv()


class Notifier:

    def __init__(self):
        # 邮件配置
        self.email_host = os.getenv("SMTP_SERVER", "")
        self.email_port = int(os.getenv("SMTP_PORT", 465))
        self.email_user = os.getenv("SMTP_USER", "")
        self.email_pass = os.getenv("SMTP_PASS", "")
        self.email_to = os.getenv("TO_EMAIL2", "")

        # 企业微信 Webhook
        self.wechat_webhook = os.getenv("WECHAT_WEBHOOK", "")

    def send_email(self, subject: str, content: str):
        if not all([self.email_host, self.email_user, self.email_pass, self.email_to]):
            log_error("❌ 邮件参数未配置完整")
            return

        msg = MIMEText(content, "plain", "utf-8")
        msg["From"] = self.email_user
        msg["To"] = self.email_to
        msg["Subject"] = Header(subject, "utf-8")

        try:
            smtp = smtplib.SMTP_SSL(self.email_host, self.email_port)
            smtp.login(self.email_user, self.email_pass)
            smtp.sendmail(self.email_user, [self.email_to], msg.as_string())
            smtp.quit()
            log_info("✅ 邮件已发送")
        except Exception as e:
            log_error(f"❌ 邮件发送失败: {e}")

    def send_wechat(self, title,content: str):
        if not self.wechat_webhook:
            log_error("❌ 企业微信 Webhook 未配置")
            return

        # data = {
        #     # "msgtype": "markdown",
        #     "msgtype": "text",
        #     "markdown": {
        #         "content": content
        #     },
        #     "mentioned_list": ["@all"]
        # }
        data = {
            "msgtype": "text",
            "text": {
                "content": f"{title}\n{content}\n",
                # "mentioned_list": ["@all"]
            }
        }

        try:
            r = requests.post(self.wechat_webhook, json=data, timeout=5)
            if r.json().get("errcode") == 0:
                log_info("✅ 企业微信通知成功")
            else:
                log_error(f"❌ 企业微信失败: {r.text}")
        except Exception as e:
            log_error(f"❌ 企业微信异常: {e}")


class SnapshotMonitor:
    def __init__(
        self,
        intervals: List[int] = [1, 5],
        rise_thresholds: Dict[int, float] = None,
        fall_thresholds: Dict[int, float] = None,
        print_limit: int = 20
    ):
        self.intervals = sorted(intervals)
        self.max_interval = max(self.intervals)
        self.cache: Dict[str, deque] = defaultdict(lambda: deque(maxlen=self.max_interval + 1))
        self.api_url = "https://www.chouyi.tv/api/v5/market/tickers?instType=SPOT"
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0'})

        self.rise_thresholds = rise_thresholds or {1: 3.0, 5: 5.0}
        self.fall_thresholds = fall_thresholds or {1: -3.0, 5: -5.0}
        self.print_limit = print_limit

        self.notice_title = os.getenv("NOTICE_TITLE", "")
        self.last_tickers = set()
        self.notifier = Notifier()

        resp = self.session.get(self.api_url, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        data = [t for t in data if t["instId"].endswith("-USDT")]
        initial_tickers = {t["instId"] for t in data}
        self.last_tickers = initial_tickers

        log_info(f"🆕 初始化完成交易对: {len(initial_tickers)} 个: {list(initial_tickers)[:5]} ...")

    def fetch_snapshot(self) -> List[dict]:
        try:
            resp = self.session.get(self.api_url, timeout=10)
            resp.raise_for_status()
            data = resp.json().get("data", [])
            data = [t for t in data if t["instId"].endswith("-USDT")]

            current_tickers = {t["instId"] for t in data}
            new_pairs = current_tickers - self.last_tickers
            if new_pairs:
                log_info(f"🆕 新上线交易对: {len(new_pairs)} 个: {list(new_pairs)[:5]} ...")
                self.notifier.send_wechat(f"🆕 新上线交易对: {len(new_pairs)} 个",  f"{list(new_pairs)}")
            self.last_tickers = current_tickers

            return data
        except Exception as e:
            log_error(f"[请求失败] {e}")
            time.sleep(5)
            return []

    def store_snapshot(self, tickers: List[dict], now_ts: float):
        for t in tickers:
            symbol = t["instId"]
            self.cache[symbol].append({
                "ts": now_ts,
                "last": float(t["last"]),
                "open24h": float(t["open24h"])
            })

    def calculate_pct(self, old_price: float, new_price: float) -> float:
        if old_price == 0:
            return 0
        return round((new_price - old_price) / old_price * 100, 2)

    def evaluate(self, now_ts: float):
        results = {i: {"up": [], "down": []} for i in self.intervals}

        for symbol, snapshots in self.cache.items():
            if len(snapshots) < 2:
                continue
            latest = snapshots[-1]
            for i in self.intervals:
                ref_ts = now_ts - i * 60
                ref = next((s for s in reversed(snapshots) if s["ts"] <= ref_ts), None)
                if not ref:
                    continue

                pct = self.calculate_pct(ref["last"], latest["last"])
                daily_pct = self.calculate_pct(latest["open24h"], latest["last"])

                record = {
                    "symbol": symbol,
                    "interval": i,
                    "pct": pct,
                    "ref_time": time.strftime('%H:%M:%S', time.localtime(ref["ts"])),
                    "ref_price": ref["last"],
                    "now_time": time.strftime('%H:%M:%S', time.localtime(latest["ts"])),
                    "now_price": latest["last"],
                    "open24h": latest["open24h"],
                    "daily_pct": daily_pct
                }

                if pct >= self.rise_thresholds.get(i, 999):
                    results[i]["up"].append(record)
                elif pct <= self.fall_thresholds.get(i, -999):
                    results[i]["down"].append(record)

        return results

    def notify_results(self, results: Dict[int, Dict[str, List[dict]]]):
        now = time.strftime('%Y-%m-%d %H:%M:%S')
        title = f"📊 {self.notice_title}(共{len(self.last_tickers)}种) {now}"
        # lines = [f"#### {title}\n"]
        lines = []

        for i in self.intervals:
            ups = sorted(results[i]["up"], key=lambda x: -x["pct"])[:self.print_limit]
            downs = sorted(results[i]["down"], key=lambda x: x["pct"])[:self.print_limit]

            if ups:
                lines.append(f"\n> 📈 涨幅 ≥ {self.rise_thresholds[i]}%（{i}分钟）共{len(ups)}种:")
                for r in ups:
                    lines.append(
                        # f"- 【{r['symbol']}】 {i}m: +{r['pct']}%  \n"
                        f"【{r['symbol']}】 {i}m: +{r['pct']}%"
                        # f" {r['ref_time']} → {r['now_time']}\n"
                        # f" {r['ref_price']:.4f} → {r['now_price']:.4f}\n"
                        # f"  24h: {r['daily_pct']:+.2f}% (开盘: {r['open24h']:.4f})\n"
                    )
                    # lines.append(
                    #     f"- {r['symbol']}(现:{r['now_price']:.4f}): {i}m: +{r['pct']}% (起: {r['ref_price']:.4f}) \n"
                    #     f"   "
                    #     f"现: {r['now_time']} @ {r['now_price']:.4f}  \n"
                    #     f"  24h: {r['daily_pct']:+.2f}% (开盘: {r['open24h']:.4f})"
                    # )

            if downs:
                lines.append(f"\n> 📉 跌幅 ≤ {self.fall_thresholds[i]}%（{i}分钟）共{len(downs)}种:")
                for r in downs:
                    lines.append(
                        # f"- 【{r['symbol']}】 {i}m: {r['pct']}%  \n"
                        f"【{r['symbol']}】 {i}m: {r['pct']}%"
                        # f" {r['ref_time']} → {r['now_time']} {i}m\n"
                        # f" {r['ref_price']:.4f} → {r['now_price']:.4f}\n"
                        # f"  24h: {r['daily_pct']:+.2f}% (开盘: {r['open24h']:.4f})\n"
                    )

        content = "\n".join(lines)
        if len(content.strip()) and len(lines) > 0:
            # log_info((title, content))
            # self.notifier.send_email(title, content)
            self.notifier.send_wechat(title, content)

    def run(self, interval_sec=60):
        log_info("🚀 启动快照行情监控...")
        while True:
            ts = time.time()
            tickers = self.fetch_snapshot()
            self.store_snapshot(tickers, ts)
            results = self.evaluate(ts)
            self.notify_results(results)
            time.sleep(interval_sec)


if __name__ == "__main__":
    monitor = SnapshotMonitor(
        intervals=[1, 2],
        # intervals=[1],
        rise_thresholds={1: 1, 2: 1.5},
        fall_thresholds={1: -1, 2: -1.5},
        # rise_thresholds={1: 0.01,2:1.5},
        # fall_thresholds={1: -0.01,2:1.5},
        print_limit=20
    )
    monitor.run()
