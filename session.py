"""
HTTP 会话管理 - UA轮换、重试、延迟
复用 /Users/Zhuanz/起点文章/qidian_scraper.py 的模式
"""

import random
import time
import logging

import requests

from config import (
    USER_AGENTS,
    REQUEST_DELAY,
    DETAIL_DELAY,
    BACKOFF_DELAY,
    PENALTY_PAUSE,
    MAX_RETRIES,
    REQUEST_TIMEOUT,
    QIDIAN_BASE,
    CONSECUTIVE_403_THRESHOLD,
)

logger = logging.getLogger(__name__)


class QidianSession:
    """起点中文网 HTTP 会话，带反爬保护"""

    def __init__(self, proxy=None, cookie=None):
        self.session = requests.Session()
        self.proxy = proxy
        self._consecutive_403 = 0

        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}

        self.session.headers.update({
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Referer": QIDIAN_BASE,
        })

        if cookie:
            self.session.headers["Cookie"] = cookie

    def rotate_ua(self):
        """轮换 User-Agent"""
        self.session.headers["User-Agent"] = random.choice(USER_AGENTS)

    def safe_get(self, url, delay_range=None, timeout=None, extra_headers=None):
        """
        带重试和延迟的安全 GET 请求。
        403 时自动退避和轮换 UA。
        """
        delay = delay_range or REQUEST_DELAY
        timeout = timeout or REQUEST_TIMEOUT

        for attempt in range(MAX_RETRIES):
            # 正常延迟
            time.sleep(random.uniform(*delay))

            # 每次请求前轮换 UA
            self.rotate_ua()

            try:
                logger.debug(f"GET {url} (attempt {attempt + 1})")
                resp = self.session.get(url, headers=extra_headers, timeout=timeout)

                # 403 处理
                if resp.status_code == 403:
                    self._consecutive_403 += 1
                    logger.warning(f"403 Forbidden ({self._consecutive_403} consecutive)")

                    if self._consecutive_403 >= CONSECUTIVE_403_THRESHOLD:
                        logger.warning(f"连续 {CONSECUTIVE_403_THRESHOLD} 次 403，暂停 {PENALTY_PAUSE}s")
                        time.sleep(PENALTY_PAUSE)
                        self._consecutive_403 = 0
                    else:
                        backoff = random.uniform(*BACKOFF_DELAY)
                        logger.info(f"退避 {backoff:.1f}s")
                        time.sleep(backoff)

                    self.rotate_ua()
                    continue

                resp.raise_for_status()

                # 成功，重置403计数
                self._consecutive_403 = 0
                return resp

            except requests.RequestException as e:
                logger.warning(f"请求失败 [{attempt + 1}/{MAX_RETRIES}]: {e}")
                if attempt == MAX_RETRIES - 1:
                    logger.error(f"最终失败，跳过: {url}")
                    return None
                time.sleep(random.uniform(3, 8))

        return None

    def safe_get_json(self, url, delay_range=None, timeout=None):
        """安全获取 JSON API 响应"""
        delay = delay_range or REQUEST_DELAY
        timeout = timeout or REQUEST_TIMEOUT

        for attempt in range(MAX_RETRIES):
            time.sleep(random.uniform(*delay))
            self.rotate_ua()

            try:
                # JSON 请求需要不同 Accept 头
                headers = {"Accept": "application/json, text/javascript, */*; q=0.01"}
                logger.debug(f"GET JSON {url} (attempt {attempt + 1})")
                resp = self.session.get(url, headers=headers, timeout=timeout)

                if resp.status_code == 403:
                    self._consecutive_403 += 1
                    backoff = random.uniform(*BACKOFF_DELAY)
                    time.sleep(backoff)
                    self.rotate_ua()
                    continue

                resp.raise_for_status()
                self._consecutive_403 = 0
                return resp.json()

            except (requests.RequestException, ValueError) as e:
                logger.warning(f"JSON请求失败 [{attempt + 1}/{MAX_RETRIES}]: {e}")
                if attempt == MAX_RETRIES - 1:
                    logger.error(f"最终失败: {url}")
                    return None
                time.sleep(random.uniform(3, 8))

        return None

    def harvest_csrf(self, mobile_url=None):
        """访问移动端页面获取 CSRF Token"""
        url = mobile_url or "https://m.qidian.com/"
        resp = self.safe_get(url, delay_range=(1, 3))
        if not resp:
            return ""

        # 从 cookies 中提取
        for name in ("_csrfToken", "csrfToken"):
            token = self.session.cookies.get(name)
            if token:
                return token

        # 从 HTML meta 标签中提取
        import re
        m = re.search(r'csrf[_-]?token["\s:=]+["\']([^"\']+)', resp.text, re.I)
        if m:
            return m.group(1)

        return ""
