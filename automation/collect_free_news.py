from __future__ import annotations

import argparse
import html
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree


USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126.0"
BING_NEWS_URL = "https://www.bing.com/news/search"
GOOGLE_NEWS_URL = "https://news.google.com/rss/search"

MEDIA_DOMAINS = {
    "36kr.com": ("36氪", 1.05),
    "latepost.com": ("晚点 LatePost", 1.2),
    "huxiu.com": ("虎嗅", 1.0),
    "jiemian.com": ("界面新闻", 1.0),
    "caixin.com": ("财新网", 1.15),
    "thepaper.cn": ("澎湃新闻", 1.0),
    "nbd.com.cn": ("每日经济新闻", 0.98),
    "yicai.com": ("第一财经", 1.05),
    "sina.com.cn": ("新浪财经", 0.95),
    "cls.cn": ("财联社", 1.02),
    "stcn.com": ("证券时报", 0.98),
    "eeo.com.cn": ("经济观察报", 1.02),
    "chinanews.com.cn": ("中国新闻网", 0.95),
    "bjnews.com.cn": ("新京报", 0.98),
    "bbtnews.com.cn": ("北京商报", 0.98),
    "cb.com.cn": ("中国经营报", 1.0),
    "lanjinger.com": ("蓝鲸新闻", 0.95),
    "time-weekly.com": ("时代财经", 0.98),
    "ithome.com": ("IT之家", 0.92),
    "leiphone.com": ("雷峰网", 0.98),
    "donews.com": ("DoNews", 0.9),
    "autohome.com.cn": ("汽车之家", 0.92),
    "pcauto.com.cn": ("太平洋汽车", 0.9),
    "cnstock.com": ("上海证券报", 0.98),
}

QUERIES = [
    "互联网 大公司 商业热点 争议 战略 财报",
    "平台经济 电商 本地生活 即时零售 竞争 监管",
    "科技公司 独角兽 IPO 上市 估值 融资",
    "AI 公司 大模型 独角兽 上市 融资 估值",
    "AI 芯片 半导体 算力 数据中心 商业化",
    "新能源汽车 车企 价格战 智驾 出海 财报",
    "动力电池 充电 自动驾驶 供应链 监管",
    "消费品牌 新零售 餐饮 茶饮 潮玩 争议 涨价",
    "直播电商 线下零售 品牌 出海 业绩 监管",
    "机器人 人形机器人 具身智能 融资 上市 订单",
]

EXCLUDE_TITLE_TERMS = [
    "港股异动",
    "美股异动",
    "股价",
    "涨停",
    "跌停",
    "概念股",
    "主力资金",
    "期指",
    "今夜看点",
    "下周看点",
    "附名单",
    "ETF",
    "一夜市值",
    "保险资金",
    "险资",
    "合理估值",
    "市值暴涨",
    "分红金额",
    "每股分红",
    "资本加持",
    "快10倍",
    "万亿市值",
]


COMMENTARY_TITLE_RE = re.compile(r"^\s*(【评论】|评论[｜丨:：]|观点[｜丨:：]|快评[｜丨:：]|社论[｜丨:：])")
DIGEST_TITLE_RE = re.compile(
    r"^\s*((\d{1,2}\s*[点:：]\s*\d{0,2}\s*氪)|8点1氪|36氪早报|[\w\u4e00-\u9fa5]{0,12}早报|[\w\u4e00-\u9fa5]{0,12}晨报|今日要闻|今日看点|一文看懂|一图看懂)"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="使用免费新闻 RSS 聚合补充商业热点。")
    parser.add_argument("--base", type=Path, help="可选：先载入已有 raw-items JSON，再合并免费搜索结果。")
    parser.add_argument("--days", type=int, default=15, help="保留最近多少天，默认 15。")
    parser.add_argument("--output", type=Path, required=True, help="合并后的 raw-items JSON 输出路径。")
    args = parser.parse_args()

    items = load_items(args.base) if args.base else []
    errors: list[str] = []
    for query in QUERIES:
        try:
            items.extend(search_bing_news(query, args.days))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Bing backup skipped for {query}: {type(exc).__name__}: {exc}")
        try:
            items.extend(search_google_news(query, args.days))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Google {query}: {type(exc).__name__}: {exc}")

    output = deduplicate(items)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"FREE_NEWS_RAW_ITEMS: {args.output}")
    print(f"FREE_NEWS_ITEM_COUNT: {len(output)}")
    for error in errors:
        print(f"INFO: {error}")
    if not output:
        raise SystemExit("免费新闻聚合未返回可用条目。")
    return 0


def search_bing_news(query: str, days: int) -> list[dict[str, object]]:
    domain_filter = " OR ".join(f"site:{domain}" for domain in MEDIA_DOMAINS)
    params = urllib.parse.urlencode(
        {
            "q": f"{query} ({domain_filter})",
            "format": "rss",
            "setlang": "zh-cn",
        }
    )
    request = urllib.request.Request(
        f"{BING_NEWS_URL}?{params}",
        headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"},
    )
    root = fetch_xml(request)

    cutoff = datetime.now().astimezone() - timedelta(days=max(1, days))
    output = []
    for node in root.findall(".//item"):
        title = clean(node.findtext("title") or "")
        url = clean_bing_url(clean(node.findtext("link") or ""))
        summary = clean(node.findtext("description") or "")
        published = parse_date(node.findtext("pubDate") or "")
        if published and published < cutoff:
            continue
        domain = matched_domain(url)
        if not title or not url or not domain:
            continue
        if is_excluded_title(title):
            continue
        source_name, source_weight = MEDIA_DOMAINS[domain]
        output.append(
            {
                "source_name": source_name,
                "title": title,
                "url": url,
                "published": published.strftime("%Y-%m-%d") if published else "",
                "summary": summary[:500],
                "source_weight": source_weight,
            }
        )
    return output


def search_google_news(query: str, days: int) -> list[dict[str, object]]:
    params = urllib.parse.urlencode(
        {
            "q": f"{query} when:{max(1, days)}d",
            "hl": "zh-CN",
            "gl": "CN",
            "ceid": "CN:zh-Hans",
        }
    )
    request = urllib.request.Request(
        f"{GOOGLE_NEWS_URL}?{params}",
        headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"},
    )
    root = fetch_xml(request)

    cutoff = datetime.now().astimezone() - timedelta(days=max(1, days))
    output = []
    for node in root.findall(".//item"):
        source_node = node.find("source")
        source_url = source_node.get("url", "") if source_node is not None else ""
        domain = matched_domain(source_url)
        if not domain:
            continue
        title = clean(node.findtext("title") or "")
        source_name, source_weight = MEDIA_DOMAINS[domain]
        title = re.sub(rf"\s*-\s*{re.escape(source_node.text or source_name)}\s*$", "", title).strip()
        url = clean(node.findtext("link") or "")
        summary = clean(node.findtext("description") or "")
        published = parse_date(node.findtext("pubDate") or "")
        if published and published < cutoff:
            continue
        if not title or not url:
            continue
        if is_excluded_title(title):
            continue
        output.append(
            {
                "source_name": source_name,
                "title": title,
                "url": url,
                "published": published.strftime("%Y-%m-%d") if published else "",
                "summary": summary[:500],
                "source_weight": source_weight,
            }
        )
    return output


def load_items(path: Path) -> list[dict[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [item for item in data if isinstance(item, dict)]


def fetch_xml(request: urllib.request.Request, retries: int = 2) -> ElementTree.Element:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
            return ElementTree.fromstring(sanitize_rss_xml(body))
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt >= retries:
                break
            time.sleep(1.5 * (attempt + 1))
    raise last_error or RuntimeError("RSS XML fetch failed")


def sanitize_rss_xml(body: bytes) -> bytes:
    # Bing occasionally returns a very long xmlns:News URL; remove it before
    # handing the feed to Python's strict XML parser.
    return remove_xmlns_news(body).replace(b"&nbsp;", b" ")


def remove_xmlns_news(body: bytes) -> bytes:
    marker = b"xmlns:News="
    start = body.find(marker)
    if start < 0:
        return body
    attr_start = start
    while attr_start > 0 and body[attr_start - 1] in b" \t\r\n":
        attr_start -= 1
    value_start = start + len(marker)
    if value_start >= len(body):
        return body[:attr_start]
    quote = body[value_start : value_start + 1]
    if quote in {b'"', b"'"}:
        value_end = body.find(quote, value_start + 1)
        if value_end >= 0:
            return body[:attr_start] + body[value_end + 1 :]
    tag_end = body.find(b">", value_start)
    if tag_end >= 0:
        return body[:attr_start] + body[tag_end:]
    return body[:attr_start]


def clean_bing_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    for key in ("url", "u", "target"):
        value = query.get(key)
        if value and value[0].startswith("http"):
            return value[0]
    return url


def matched_domain(url: str) -> str:
    hostname = (urlparse(url).hostname or "").lower()
    for domain in MEDIA_DOMAINS:
        if hostname == domain or hostname.endswith(f".{domain}"):
            return domain
    return ""


def parse_date(value: str) -> datetime | None:
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def deduplicate(items: list[dict[str, object]]) -> list[dict[str, object]]:
    output = []
    seen: set[str] = set()
    for item in items:
        key = str(item.get("url") or item.get("title") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def is_excluded_title(title: str) -> bool:
    return (
        "#" in title
        or bool(COMMENTARY_TITLE_RE.search(title))
        or bool(DIGEST_TITLE_RE.search(title))
        or any(term.lower() in title.lower() for term in EXCLUDE_TITLE_TERMS)
    )


def clean(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


if __name__ == "__main__":
    raise SystemExit(main())
