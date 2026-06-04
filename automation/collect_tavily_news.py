from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse


TAVILY_SEARCH_URL = "https://api.tavily.com/search"

MEDIA_DOMAINS = [
    "36kr.com",
    "latepost.com",
    "huxiu.com",
    "jiemian.com",
    "caixin.com",
    "thepaper.cn",
    "nbd.com.cn",
    "yicai.com",
]

SOURCE_NAMES = {
    "36kr.com": "36氪",
    "latepost.com": "晚点 LatePost",
    "huxiu.com": "虎嗅",
    "jiemian.com": "界面新闻",
    "caixin.com": "财新网",
    "thepaper.cn": "澎湃新闻",
    "nbd.com.cn": "每日经济新闻",
    "yicai.com": "第一财经",
}

SOURCE_WEIGHTS = {
    "36kr.com": 1.05,
    "latepost.com": 1.2,
    "huxiu.com": 1.0,
    "jiemian.com": 1.0,
    "caixin.com": 1.15,
    "thepaper.cn": 1.0,
    "nbd.com.cn": 0.98,
    "yicai.com": 1.05,
}

QUERIES = [
    "互联网大公司 商业热点 争议 战略 财报 外卖 电商 平台",
    "新能源汽车大公司 商业热点 争议 涨价 智驾 高管",
    "AI 芯片 大公司 商业热点 争议 产品发布 投融资",
    "消费 新零售 大公司 商业热点 争议 品牌 餐饮 零售",
    "机器人 大公司 商业热点 争议 人形机器人 融资 产品",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="使用 Tavily 搜索最近商业媒体热点。")
    parser.add_argument("--days", type=int, default=15, help="检索最近多少天，默认 15。")
    parser.add_argument("--max-results", type=int, default=12, help="每个行业查询最多结果数。")
    parser.add_argument("--output", type=Path, required=True, help="输出 raw-items JSON 路径。")
    args = parser.parse_args()

    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("缺少 TAVILY_API_KEY，无法运行 Tavily 媒体检索。")

    end_date = date.today()
    start_date = end_date - timedelta(days=max(1, args.days))
    items: list[dict[str, object]] = []
    errors: list[str] = []

    for query in QUERIES:
        try:
            results = search(
                api_key=api_key,
                query=query,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                max_results=args.max_results,
            )
            items.extend(normalize_results(results))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{query}: {type(exc).__name__}: {exc}")

    output = deduplicate(items)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"TAVILY_RAW_ITEMS: {args.output}")
    print(f"TAVILY_ITEM_COUNT: {len(output)}")
    for error in errors:
        print(f"WARNING: {error}")
    if not output:
        raise SystemExit("Tavily 未返回可用商业媒体条目。")
    return 0


def search(api_key: str, query: str, start_date: str, end_date: str, max_results: int) -> list[dict[str, object]]:
    payload = {
        "api_key": api_key,
        "query": query,
        "topic": "news",
        "search_depth": "advanced",
        "max_results": max_results,
        "include_domains": MEDIA_DOMAINS,
        "start_date": start_date,
        "end_date": end_date,
        "include_answer": False,
        "include_raw_content": False,
    }
    request = urllib.request.Request(
        TAVILY_SEARCH_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "xiaohu-business-hotspots/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Tavily HTTP {exc.code}: {detail[:300]}") from exc
    return [item for item in result.get("results", []) if isinstance(item, dict)]


def normalize_results(results: list[dict[str, object]]) -> list[dict[str, object]]:
    normalized = []
    for item in results:
        url = str(item.get("url", "")).strip()
        title = str(item.get("title", "")).strip()
        if not url or not title:
            continue
        domain = registrable_domain(url)
        normalized.append(
            {
                "source_name": SOURCE_NAMES.get(domain, domain),
                "title": title,
                "url": url,
                "published": normalize_date(str(item.get("published_date", ""))),
                "summary": str(item.get("content", "")).strip()[:500],
                "source_weight": SOURCE_WEIGHTS.get(domain, 1.0),
            }
        )
    return normalized


def deduplicate(items: list[dict[str, object]]) -> list[dict[str, object]]:
    output = []
    seen: set[str] = set()
    for item in items:
        key = str(item.get("url") or item.get("title")).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def registrable_domain(url: str) -> str:
    hostname = (urlparse(url).hostname or "").lower()
    for domain in MEDIA_DOMAINS:
        if hostname == domain or hostname.endswith(f".{domain}"):
            return domain
    return hostname


def normalize_date(value: str) -> str:
    return value[:10] if len(value) >= 10 else ""


if __name__ == "__main__":
    raise SystemExit(main())
