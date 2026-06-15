from __future__ import annotations

import argparse
import csv
import json
import math
import re
import subprocess
import time
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DATA = ROOT / "insights" / "hotspots-data.js"
OUT_DIR = ROOT / "data" / "social-discovery"
XHS = "xhs"
DATA_PREFIX = "window.XIAOHU_HOTSPOTS_DATA = "

KEYWORD_HINTS = [
    ("外卖大战", ["外卖", "美团", "京东", "阿里", "即时零售"]),
    ("即时零售", ["外卖", "美团", "京东", "阿里", "即时零售"]),
    ("电商平台约谈", ["淘宝", "京东", "拼多多", "抖音", "小红书", "约谈"]),
    ("长鑫科技", ["长鑫科技", "国产存储", "IPO", "芯片"]),
    ("腾讯AI慢", ["腾讯", "AI", "姚顺雨", "汤道生"]),
    ("姚顺雨", ["腾讯", "AI", "姚顺雨", "汤道生"]),
    ("茅台董事长", ["茅台", "股东会", "价格", "渠道"]),
    ("茅台股东会", ["茅台", "股东会", "价格", "渠道"]),
    ("军工企业名单", ["比亚迪", "阿里", "百度", "军工企业名单", "美国"]),
    ("比亚迪", ["比亚迪", "军工企业名单", "美国"]),
    ("泡泡玛特", ["泡泡玛特", "LABUBU", "城市乐园"]),
    ("瑞幸", ["瑞幸", "外卖", "价格战"]),
    ("正新鸡排", ["正新鸡排", "上市", "蜜雪冰城"]),
    ("蔚来李斌", ["蔚来", "李斌", "销量"]),
    ("宁德时代", ["宁德时代", "宁王", "IPO"]),
    ("英伟达", ["英伟达", "SK海力士", "存储"]),
]

NOISE_TERMS = [
    "恐龙",
    "侏罗纪",
    "霸王龙",
    "苍龙",
    "减肥",
    "美食教程",
    "探店",
    "红包",
    "口令",
    "优惠券",
    "省钱",
    "凑单",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="用 xiaohongshu-cli 只读采集热点相关笔记/视频评论并输出标准 CSV。")
    parser.add_argument("--input", type=Path, default=FRONTEND_DATA, help="热点前端数据 JS。")
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--keywords", help="逗号分隔的手动关键词；提供后不从热点自动生成。")
    parser.add_argument("--max-hotspots", type=int, default=8)
    parser.add_argument("--search-limit", type=int, default=12)
    parser.add_argument("--notes-per-keyword", type=int, default=2)
    parser.add_argument("--comments-per-note", type=int, default=8)
    parser.add_argument("--sort", choices=["latest", "popular", "general"], default="latest", help="小红书搜索排序。默认用最新，避免热门排序混入旧内容。")
    parser.add_argument("--min-note-likes", type=float, default=100)
    parser.add_argument("--min-comment-likes", type=float, default=5)
    parser.add_argument("--days", type=int, default=15)
    parser.add_argument("--note-type", choices=["all", "video", "image"], default="all")
    parser.add_argument("--all-comments", action="store_true", help="抓取全部评论；默认只抓首页评论。")
    parser.add_argument("--sleep", type=float, default=1.0, help="xhs 请求间隔秒数。")
    args = parser.parse_args()

    ensure_xhs_auth()
    hotspots = load_hotspots(args.input)
    keyword_specs = build_keyword_specs(hotspots, args)

    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for spec in keyword_specs:
        try:
            rows.extend(collect_keyword(spec, args))
        except Exception as exc:  # xhs can hit platform verification; keep partial output.
            errors.append(f"{spec['keyword']}: {type(exc).__name__}: {exc}")
        time.sleep(args.sleep)

    selected = select_rows(rows, args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    raw_path = args.output_dir / f"{timestamp}-xhs-raw-comments.csv"
    opinions_path = args.output_dir / f"{timestamp}-xhs-social-opinions.csv"
    kol_path = args.output_dir / f"{timestamp}-xhs-kol-mentions.csv"
    report_path = args.output_dir / f"{timestamp}-xhs-social-report.json"

    write_csv(raw_path, raw_fields(), rows)
    write_csv(opinions_path, opinion_fields(), [to_opinion(row) for row in selected])
    write_csv(kol_path, kol_fields(), build_kol_rows(selected))
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input": str(args.input),
        "keywords": keyword_specs,
        "raw_rows": len(rows),
        "selected_rows": len(selected),
        "errors": errors,
        "outputs": {
            "raw_comments": str(raw_path),
            "social_opinions": str(opinions_path),
            "kol_mentions": str(kol_path),
            "report": str(report_path),
        },
        "next_step": (
            f"python scripts/apply_social_opinions_to_frontend.py --social-opinions {opinions_path}"
        ),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"RAW_COMMENTS: {raw_path}")
    print(f"SOCIAL_OPINIONS: {opinions_path}")
    print(f"KOL_MENTIONS: {kol_path}")
    print(f"REPORT: {report_path}")
    print(f"SELECTED_COMMENTS: {len(selected)}")
    if errors:
        print("WARNINGS:")
        for error in errors:
            print(f"- {error}")
    return 0


def ensure_xhs_auth() -> None:
    result = run_xhs(["status", "--yaml"], check=False)
    if result.returncode != 0:
        raise SystemExit("xhs 未登录。请先运行：xhs login 或 xhs login --qrcode")


def load_hotspots(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    data = json.loads(text.removeprefix(DATA_PREFIX).rstrip(" ;\n"))
    return data.get("hotspots") or []


def build_keyword_specs(hotspots: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, str]]:
    if args.keywords:
        return [{"keyword": item.strip(), "hotspot_title": item.strip()} for item in args.keywords.split(",") if item.strip()]
    specs: list[dict[str, str]] = []
    seen: set[str] = set()
    for hotspot in hotspots[: args.max_hotspots]:
        blob = " ".join(str(hotspot.get(key, "")) for key in ["title", "summary", "core_summary", "business_angle"])
        keyword = infer_keyword(blob)
        if not keyword or keyword in seen:
            continue
        seen.add(keyword)
        specs.append({"keyword": keyword, "hotspot_title": str(hotspot.get("title", keyword))})
    return specs


def infer_keyword(text: str) -> str:
    for keyword, terms in KEYWORD_HINTS:
        if any(term in text for term in terms):
            return keyword
    cleaned = re.sub(r"【[^】]+】", "", text)
    cleaned = re.split(r"[，,。:：|｜\s]", cleaned.strip())[0]
    return cleaned[:16]


def collect_keyword(spec: dict[str, str], args: argparse.Namespace) -> list[dict[str, Any]]:
    query = query_for_keyword(spec["keyword"])
    search_items = search_xhs(query, args)
    candidates = filter_candidates(search_items, spec["keyword"], args)
    rows: list[dict[str, Any]] = []
    for item in candidates[: args.notes_per_keyword]:
        note = read_note(item["url"])
        article = merge_article(item, note)
        comments = read_comments(item["url"], all_comments=args.all_comments)
        for comment in flatten_comments(comments):
            row = build_row(spec, article, comment)
            if row["comment_like_count"] >= args.min_comment_likes:
                rows.append(row)
        time.sleep(args.sleep)
    return rows


def query_for_keyword(keyword: str) -> str:
    return keyword


def search_xhs(query: str, args: argparse.Namespace) -> list[dict[str, Any]]:
    cmd = ["search", query, "--sort", args.sort, "--json"]
    if args.note_type != "all":
        cmd.extend(["--type", args.note_type])
    result = run_xhs(cmd)
    data = json.loads(result.stdout)
    items = (data.get("data") or {}).get("items") or []
    output = []
    for item in items[: args.search_limit]:
        card = item.get("note_card") or {}
        info = card.get("interact_info") or {}
        user = card.get("user") or {}
        title = clean(card.get("display_title") or card.get("title") or "")
        note_id = item.get("id") or item.get("note_id") or card.get("note_id")
        xsec_token = item.get("xsec_token") or user.get("xsec_token") or ""
        if not note_id or not xsec_token:
            continue
        output.append(
            {
                "id": note_id,
                "url": f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={urllib.parse.quote(xsec_token)}",
                "title": title,
                "author": clean(user.get("nickname") or user.get("nick_name") or ""),
                "likes": parse_number(info.get("liked_count")),
                "comments": parse_number(info.get("comment_count")),
                "shares": parse_number(info.get("shared_count") or info.get("share_count")),
                "published_at": published_from_corner(card),
                "type": card.get("type") or item.get("model_type") or "",
            }
        )
    return output


def filter_candidates(items: list[dict[str, Any]], keyword: str, args: argparse.Namespace) -> list[dict[str, Any]]:
    terms = terms_for_keyword(keyword)
    cutoff = datetime.now() - timedelta(days=args.days)
    filtered = []
    for item in items:
        title = item["title"]
        if not title:
            continue
        if item["likes"] < args.min_note_likes:
            continue
        published_at = parse_date(item.get("published_at", ""))
        if published_at and published_at < cutoff:
            continue
        if any(noise in title for noise in NOISE_TERMS):
            continue
        if terms and not is_relevant_title(title, keyword, terms):
            continue
        filtered.append(item)
    return sorted(filtered, key=lambda item: (item["likes"], item["comments"]), reverse=True)


def is_relevant_title(title: str, keyword: str, terms: list[str]) -> bool:
    if keyword in title:
        return True
    matched = sum(1 for term in terms if term in title)
    if len(terms) <= 1:
        return matched >= 1
    return matched >= 2


def terms_for_keyword(keyword: str) -> list[str]:
    for key, terms in KEYWORD_HINTS:
        if keyword == key:
            return terms
    return [keyword]


def read_note(url: str) -> dict[str, Any]:
    result = run_xhs(["read", url, "--json"])
    data = json.loads(result.stdout)
    items = (data.get("data") or {}).get("items") or []
    return items[0] if items else {}


def merge_article(item: dict[str, Any], note: dict[str, Any]) -> dict[str, Any]:
    card = note.get("note_card") or {}
    info = card.get("interact_info") or {}
    user = card.get("user") or {}
    title = clean(card.get("display_title") or card.get("title") or item.get("title") or "")
    desc = clean(card.get("desc") or "")
    return {
        "id": item["id"],
        "url": item["url"],
        "title": title or desc[:40] or item["title"],
        "desc": desc,
        "author": clean(user.get("nickname") or user.get("nick_name") or item.get("author") or ""),
        "likes": parse_number(info.get("liked_count") or item.get("likes")),
        "comments": parse_number(info.get("comment_count") or item.get("comments")),
        "shares": parse_number(info.get("share_count") or item.get("shares")),
        "published_at": format_timestamp(card.get("time")) or item.get("published_at", ""),
    }


def read_comments(url: str, all_comments: bool) -> list[dict[str, Any]]:
    cmd = ["comments", url, "--json"]
    if all_comments:
        cmd.insert(2, "--all")
    result = run_xhs(cmd)
    data = json.loads(result.stdout)
    return (data.get("data") or {}).get("comments") or []


def flatten_comments(comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flat: list[dict[str, Any]] = []
    for comment in comments:
        flat.append(comment)
        for sub in comment.get("sub_comments") or []:
            flat.append(sub)
    return sorted(flat, key=lambda item: parse_number(item.get("like_count")), reverse=True)


def build_row(spec: dict[str, str], article: dict[str, Any], comment: dict[str, Any]) -> dict[str, Any]:
    user = comment.get("user_info") or {}
    reply_count = parse_number(comment.get("sub_comment_count"))
    article_heat = heat_score(article)
    comment_likes = parse_number(comment.get("like_count"))
    return {
        "keyword": spec["keyword"],
        "hotspot_title": spec["hotspot_title"],
        "platform": "小红书",
        "article_title": article["title"],
        "article_url": article["url"],
        "article_author": article["author"],
        "article_followers": "",
        "article_view_count": "",
        "article_like_count": format_number(article["likes"]),
        "article_comment_count": format_number(article["comments"]),
        "article_share_count": format_number(article["shares"]),
        "article_heat_score": format_number(article_heat),
        "published_at": article["published_at"],
        "comment_id": comment.get("id", ""),
        "comment_text": clean(comment.get("content") or ""),
        "comment_author": clean(user.get("nickname") or ""),
        "comment_like_count": comment_likes,
        "comment_reply_count": reply_count,
        "comment_url": f"{article['url']}#comment-{comment.get('id', '')}",
        "stance": infer_stance(clean(comment.get("content") or "")),
        "combined_score": round(math.log10(article_heat + 10) * 20 + comment_likes * 1.5 + reply_count, 2),
    }


def select_rows(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    rows = [row for row in rows if row["comment_text"] and parse_number(row["comment_like_count"]) >= args.min_comment_likes]
    rows.sort(key=lambda row: row["combined_score"], reverse=True)
    selected: list[dict[str, Any]] = []
    per_keyword: dict[str, int] = {}
    per_article: dict[str, int] = {}
    for row in rows:
        keyword = row["keyword"]
        article_key = f"{keyword}::{row['article_url']}"
        if per_keyword.get(keyword, 0) >= args.comments_per_note * args.notes_per_keyword:
            continue
        if per_article.get(article_key, 0) >= args.comments_per_note:
            continue
        selected.append(row)
        per_keyword[keyword] = per_keyword.get(keyword, 0) + 1
        per_article[article_key] = per_article.get(article_key, 0) + 1
    return selected


def heat_score(article: dict[str, Any]) -> float:
    return round(article["likes"] + article["comments"] * 3 + article["shares"] * 2, 2)


def to_opinion(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "keyword": row["keyword"],
        "platform": row["platform"],
        "opinion": row["comment_text"],
        "likes": format_number(row["comment_like_count"]),
        "stance": row["stance"],
        "url": row["comment_url"],
        "article_title": row["article_title"],
        "article_url": row["article_url"],
        "published_at": row["published_at"],
        "article_heat_score": format_number(row["article_heat_score"]),
        "comment_author": row["comment_author"],
        "comment_id": row["comment_id"],
        "comment_reply_count": format_number(row["comment_reply_count"]),
        "combined_score": row["combined_score"],
    }


def build_kol_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    seen = set()
    for row in sorted(rows, key=lambda item: parse_number(item["article_heat_score"]), reverse=True):
        key = f"{row['keyword']}::{row['article_url']}"
        if key in seen:
            continue
        seen.add(key)
        output.append(
            {
                "keyword": row["keyword"],
                "platform": row["platform"],
                "author": row["article_author"],
                "followers": row["article_followers"],
                "title": row["article_title"],
                "url": row["article_url"],
                "date": row["published_at"],
            }
        )
    return output


def run_xhs(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([XHS, *args], capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result


def published_from_corner(card: dict[str, Any]) -> str:
    for item in card.get("corner_tag_info") or []:
        if item.get("type") == "publish_time":
            text = clean(item.get("text") or "")
            now = datetime.now()
            if text == "刚刚":
                return now.strftime("%Y-%m-%d")
            minute_match = re.match(r"^(\d+)分钟前$", text)
            if minute_match:
                return (now - timedelta(minutes=int(minute_match.group(1)))).strftime("%Y-%m-%d")
            hour_match = re.match(r"^(\d+)小时前$", text)
            if hour_match:
                return (now - timedelta(hours=int(hour_match.group(1)))).strftime("%Y-%m-%d")
            if text.startswith("昨天"):
                return (now - timedelta(days=1)).strftime("%Y-%m-%d")
            if text.startswith("前天"):
                return (now - timedelta(days=2)).strftime("%Y-%m-%d")
            if re.match(r"^\d{2}-\d{2}$", text):
                return f"{now.year}-{text}"
            return text
    return ""


def parse_date(value: str) -> datetime | None:
    value = clean(value)
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def format_timestamp(value: Any) -> str:
    if not value:
        return ""
    try:
        return datetime.fromtimestamp(float(value) / 1000).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return ""


def infer_stance(text: str) -> str:
    if any(word in text for word in ["支持", "合理", "正常", "理解", "看好"]):
        return "支持"
    if any(word in text for word in ["质疑", "割韭菜", "离谱", "坑", "反对", "不看好"]):
        return "质疑"
    if any(word in text for word in ["担心", "风险", "问题", "压力"]):
        return "担忧"
    return "讨论"


def parse_number(value: Any) -> float:
    text = clean(value)
    if not text:
        return 0.0
    multiplier = 1
    if text.endswith("万"):
        multiplier = 10000
        text = text[:-1]
    elif text.endswith("亿"):
        multiplier = 100000000
        text = text[:-1]
    text = re.sub(r"[^0-9.]", "", text)
    if not text:
        return 0.0
    try:
        return float(text) * multiplier
    except ValueError:
        return 0.0


def format_number(value: Any) -> str:
    number = parse_number(value)
    if number.is_integer():
        return str(int(number))
    return str(round(number, 2))


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def raw_fields() -> list[str]:
    return [
        "keyword",
        "hotspot_title",
        "platform",
        "article_title",
        "article_url",
        "article_author",
        "article_followers",
        "article_view_count",
        "article_like_count",
        "article_comment_count",
        "article_share_count",
        "article_heat_score",
        "published_at",
        "comment_id",
        "comment_text",
        "comment_author",
        "comment_like_count",
        "comment_reply_count",
        "comment_url",
        "stance",
        "combined_score",
    ]


def opinion_fields() -> list[str]:
    return [
        "keyword",
        "platform",
        "opinion",
        "likes",
        "stance",
        "url",
        "article_title",
        "article_url",
        "published_at",
        "article_heat_score",
        "comment_author",
        "comment_id",
        "comment_reply_count",
        "combined_score",
    ]


def kol_fields() -> list[str]:
    return ["keyword", "platform", "author", "followers", "title", "url", "date"]


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


if __name__ == "__main__":
    raise SystemExit(main())
