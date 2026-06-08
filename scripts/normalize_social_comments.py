from __future__ import annotations

import argparse
import csv
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "social-discovery"


FIELD_ALIASES = {
    "keyword": ["keyword", "关键词", "topic", "hotspot_keyword"],
    "hotspot_title": ["hotspot_title", "热点标题", "hotspot", "topic_title"],
    "platform": ["platform", "平台", "source_platform"],
    "article_title": ["article_title", "内容标题", "文章标题", "video_title", "note_title", "title"],
    "article_url": ["article_url", "内容链接", "文章链接", "video_url", "note_url", "url"],
    "article_author": ["article_author", "账号", "作者", "author", "publisher"],
    "article_followers": ["article_followers", "粉丝数", "followers", "fans"],
    "article_view_count": ["article_view_count", "播放量", "阅读量", "views", "view_count"],
    "article_like_count": ["article_like_count", "内容点赞数", "article_likes", "video_likes"],
    "article_comment_count": ["article_comment_count", "评论数", "article_comments", "comment_count"],
    "article_share_count": ["article_share_count", "转发数", "分享数", "shares", "reposts"],
    "article_heat_score": ["article_heat_score", "文章热度", "内容热度", "heat", "hot_score"],
    "published_at": ["published_at", "发布时间", "date", "created_at"],
    "comment_id": ["comment_id", "评论ID", "id"],
    "comment_text": ["comment_text", "评论内容", "opinion", "热评", "comment", "text"],
    "comment_author": ["comment_author", "评论用户", "user", "comment_user"],
    "comment_like_count": ["comment_like_count", "评论点赞数", "likes", "点赞数", "like_count"],
    "comment_reply_count": ["comment_reply_count", "回复数", "reply_count"],
    "comment_url": ["comment_url", "评论链接", "comment_link"],
    "stance": ["stance", "立场"],
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="把授权 API、第三方数据服务或后台导出的真实评论标准化为热点页面可用 CSV。"
    )
    parser.add_argument("--input", type=Path, required=True, help="评论明细 CSV/JSON。")
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--min-article-heat", type=float, default=1000, help="最低文章热度分。")
    parser.add_argument("--min-comment-likes", type=float, default=20, help="最低评论点赞数。")
    parser.add_argument("--top-articles-per-keyword", type=int, default=5)
    parser.add_argument("--top-comments-per-article", type=int, default=5)
    parser.add_argument("--top-comments-per-keyword", type=int, default=8)
    args = parser.parse_args()

    rows = read_rows(args.input)
    normalized = [normalize_row(row) for row in rows]
    verified = [row for row in normalized if has_required_evidence(row)]
    ranked = rank_rows(verified)
    selected = select_rows(
        ranked,
        min_article_heat=args.min_article_heat,
        min_comment_likes=args.min_comment_likes,
        top_articles_per_keyword=args.top_articles_per_keyword,
        top_comments_per_article=args.top_comments_per_article,
        top_comments_per_keyword=args.top_comments_per_keyword,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    opinions_path = args.output_dir / f"{timestamp}-verified-social-opinions.csv"
    kol_path = args.output_dir / f"{timestamp}-verified-kol-mentions.csv"
    report_path = args.output_dir / f"{timestamp}-verified-social-report.json"

    write_social_opinions(opinions_path, selected)
    write_kol_mentions(kol_path, selected)
    report = build_report(args, rows, verified, selected, opinions_path, kol_path, report_path)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"SOCIAL_OPINIONS: {opinions_path}")
    print(f"KOL_MENTIONS: {kol_path}")
    print(f"REPORT: {report_path}")
    print(f"SELECTED_COMMENTS: {len(selected)}")
    return 0


def read_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("items") or data.get("comments") or []
        if not isinstance(data, list):
            raise ValueError("JSON 输入必须是 list，或包含 items/comments list")
        return [row for row in data if isinstance(row, dict)]
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = {field: pick(row, aliases) for field, aliases in FIELD_ALIASES.items()}
    normalized["keyword"] = normalized["keyword"] or keyword_from_title(normalized["hotspot_title"])
    normalized["article_heat_score"] = heat_score(normalized)
    normalized["comment_like_count"] = parse_number(normalized["comment_like_count"])
    normalized["comment_reply_count"] = parse_number(normalized["comment_reply_count"])
    normalized["article_view_count"] = parse_number(normalized["article_view_count"])
    normalized["article_like_count"] = parse_number(normalized["article_like_count"])
    normalized["article_comment_count"] = parse_number(normalized["article_comment_count"])
    normalized["article_share_count"] = parse_number(normalized["article_share_count"])
    normalized["article_followers_count"] = parse_number(normalized["article_followers"])
    normalized["stance"] = normalized["stance"] or infer_stance(normalized["comment_text"])
    normalized["evidence_url"] = normalized["comment_url"] or normalized["article_url"]
    normalized["combined_score"] = combined_score(normalized)
    return normalized


def pick(row: dict[str, Any], aliases: list[str]) -> str:
    for alias in aliases:
        value = row.get(alias)
        if value not in (None, ""):
            return clean(value)
    return ""


def has_required_evidence(row: dict[str, Any]) -> bool:
    if not row["keyword"] or not row["platform"] or not row["article_url"] or not row["comment_text"]:
        return False
    if row["comment_like_count"] <= 0:
        return False
    return row["article_heat_score"] > 0 or any(
        row[field] > 0
        for field in ["article_view_count", "article_like_count", "article_comment_count", "article_share_count"]
    )


def rank_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: row["combined_score"], reverse=True)


def select_rows(
    rows: list[dict[str, Any]],
    min_article_heat: float,
    min_comment_likes: float,
    top_articles_per_keyword: int,
    top_comments_per_article: int,
    top_comments_per_keyword: int,
) -> list[dict[str, Any]]:
    article_rank: dict[str, list[str]] = {}
    for row in sorted(rows, key=lambda item: item["article_heat_score"], reverse=True):
        article_rank.setdefault(row["keyword"], [])
        if row["article_url"] not in article_rank[row["keyword"]]:
            article_rank[row["keyword"]].append(row["article_url"])

    selected: list[dict[str, Any]] = []
    per_article: dict[str, int] = {}
    per_keyword: dict[str, int] = {}
    for row in rows:
        if row["article_heat_score"] < min_article_heat or row["comment_like_count"] < min_comment_likes:
            continue
        if row["article_url"] not in article_rank.get(row["keyword"], [])[:top_articles_per_keyword]:
            continue
        article_key = f"{row['keyword']}::{row['article_url']}"
        if per_article.get(article_key, 0) >= top_comments_per_article:
            continue
        if per_keyword.get(row["keyword"], 0) >= top_comments_per_keyword:
            continue
        selected.append(row)
        per_article[article_key] = per_article.get(article_key, 0) + 1
        per_keyword[row["keyword"]] = per_keyword.get(row["keyword"], 0) + 1
    return selected


def heat_score(row: dict[str, Any]) -> float:
    explicit = parse_number(row["article_heat_score"])
    if explicit > 0:
        return explicit
    views = parse_number(row["article_view_count"])
    likes = parse_number(row["article_like_count"])
    comments = parse_number(row["article_comment_count"])
    shares = parse_number(row["article_share_count"])
    followers = parse_number(row["article_followers"])
    return round(views * 0.02 + likes + comments * 3 + shares * 2 + min(followers * 0.001, 500), 2)


def combined_score(row: dict[str, Any]) -> float:
    return round(math.log10(row["article_heat_score"] + 10) * 20 + row["comment_like_count"] * 1.5 + row["comment_reply_count"], 2)


def write_social_opinions(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "keyword",
        "platform",
        "opinion",
        "likes",
        "stance",
        "url",
        "article_title",
        "article_url",
        "article_heat_score",
        "comment_author",
        "comment_id",
        "comment_reply_count",
        "combined_score",
    ]
    output = []
    for row in rows:
        output.append(
            {
                "keyword": row["keyword"],
                "platform": row["platform"],
                "opinion": row["comment_text"],
                "likes": format_number(row["comment_like_count"]),
                "stance": row["stance"],
                "url": row["evidence_url"],
                "article_title": row["article_title"],
                "article_url": row["article_url"],
                "article_heat_score": format_number(row["article_heat_score"]),
                "comment_author": row["comment_author"],
                "comment_id": row["comment_id"],
                "comment_reply_count": format_number(row["comment_reply_count"]),
                "combined_score": row["combined_score"],
            }
        )
    write_csv(path, fields, output)


def write_kol_mentions(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["keyword", "platform", "author", "followers", "title", "url", "date"]
    seen: set[str] = set()
    output = []
    for row in sorted(rows, key=lambda item: item["article_heat_score"], reverse=True):
        key = f"{row['keyword']}::{row['article_url']}"
        if key in seen:
            continue
        seen.add(key)
        output.append(
            {
                "keyword": row["keyword"],
                "platform": row["platform"],
                "author": row["article_author"] or "待核实账号",
                "followers": row["article_followers"],
                "title": row["article_title"],
                "url": row["article_url"],
                "date": row["published_at"],
            }
        )
    write_csv(path, fields, output)


def build_report(
    args: argparse.Namespace,
    input_rows: list[dict[str, Any]],
    verified: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    opinions_path: Path,
    kol_path: Path,
    report_path: Path,
) -> dict[str, Any]:
    keywords = sorted({row["keyword"] for row in selected})
    platforms = sorted({row["platform"] for row in selected})
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input": str(args.input),
        "input_count": len(input_rows),
        "verified_count": len(verified),
        "selected_count": len(selected),
        "keywords": keywords,
        "platforms": platforms,
        "thresholds": {
            "min_article_heat": args.min_article_heat,
            "min_comment_likes": args.min_comment_likes,
            "top_articles_per_keyword": args.top_articles_per_keyword,
            "top_comments_per_article": args.top_comments_per_article,
            "top_comments_per_keyword": args.top_comments_per_keyword,
        },
        "outputs": {
            "social_opinions": str(opinions_path),
            "kol_mentions": str(kol_path),
            "report": str(report_path),
        },
        "evidence_rule": "每条入选评论必须有 keyword、platform、article_url、comment_text、comment_like_count，并具备文章热度或文章互动指标。",
    }


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def parse_number(value: Any) -> float:
    text = clean(value).replace(",", "")
    if not text:
        return 0.0
    multiplier = 1.0
    if "亿" in text:
        multiplier = 100000000
    elif "万" in text:
        multiplier = 10000
    match = re.search(r"\d+(?:\.\d+)?", text)
    return round(float(match.group(0)) * multiplier, 2) if match else 0.0


def format_number(value: Any) -> str:
    number = float(value or 0)
    if number.is_integer():
        return str(int(number))
    return str(round(number, 2))


def infer_stance(text: str) -> str:
    if re.search(r"(质疑|担心|反对|割韭菜|垄断|内卷|不看好|失望|离谱|坑)", text):
        return "质疑"
    if re.search(r"(支持|看好|利好|认可|值得|改善|创新|期待|方便)", text):
        return "支持"
    return "中性"


def keyword_from_title(title: str) -> str:
    title = clean(title)
    title = re.sub(r"[【】\[\]（）()｜|:：,，。].*$", "", title)
    return title[:24]


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


if __name__ == "__main__":
    raise SystemExit(main())
