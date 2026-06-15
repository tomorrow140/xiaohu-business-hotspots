from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DATA = ROOT / "insights" / "hotspots-data.js"
DATA_PREFIX = "window.XIAOHU_HOTSPOTS_DATA = "


def main() -> int:
    parser = argparse.ArgumentParser(description="把 social-opinions CSV 回灌到当前热点前端数据。")
    parser.add_argument("--input", type=Path, default=FRONTEND_DATA)
    parser.add_argument("--output", type=Path, default=FRONTEND_DATA)
    parser.add_argument("--social-opinions", type=Path, required=True)
    parser.add_argument("--max-comments-per-hotspot", type=int, default=5)
    parser.add_argument("--replace-existing", action="store_true", help="没有匹配评论的热点也清空旧评论。默认只更新匹配到的热点。")
    args = parser.parse_args()

    data = load_frontend(args.input)
    opinions = load_opinions(args.social_opinions)
    updated = 0
    for hotspot in data.get("hotspots", []):
        blob = " ".join(
            str(hotspot.get(key, ""))
            for key in ["title", "summary", "core_summary", "business_angle", "topic_value"]
        )
        matched = match_opinions(blob, opinions)[: args.max_comments_per_hotspot]
        if not matched and not args.replace_existing:
            continue
        hotspot["social_opinions"] = matched
        hotspot["social_data_complete"] = len(matched) >= 5
        analysis = build_social_analysis(matched)
        hotspot["public_consensus"] = analysis["consensus"]
        hotspot["public_controversies"] = analysis["controversies"]
        if matched:
            updated += 1

    report = data.setdefault("report", {})
    report["social_opinions_file"] = str(args.social_opinions)
    report["social_opinions_applied_at"] = datetime.now().isoformat(timespec="seconds")
    report["social_opinions_hotspot_count"] = updated

    args.output.write_text(DATA_PREFIX + json.dumps(data, ensure_ascii=False, indent=2) + ";\n", encoding="utf-8")
    print(f"UPDATED_HOTSPOTS: {updated}")
    print(f"OUTPUT: {args.output}")
    return 0


def load_frontend(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    return json.loads(text.removeprefix(DATA_PREFIX).rstrip(" ;\n"))


def load_opinions(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    output = []
    for row in rows:
        keyword = clean(row.get("keyword"))
        opinion = clean(row.get("opinion") or row.get("comment_text"))
        platform = clean(row.get("platform"))
        if not keyword or not opinion or not platform:
            continue
        output.append(
            {
                "keyword": keyword,
                "platform": platform,
                "opinion": opinion,
                "likes": clean(row.get("likes") or row.get("comment_like_count")),
                "stance": clean(row.get("stance")),
                "url": clean(row.get("url") or row.get("comment_url") or row.get("article_url")),
                "article_title": clean(row.get("article_title")),
                "article_url": clean(row.get("article_url")),
                "article_heat_score": clean(row.get("article_heat_score")),
                "comment_author": clean(row.get("comment_author")),
                "comment_id": clean(row.get("comment_id")),
                "comment_reply_count": clean(row.get("comment_reply_count")),
                "combined_score": parse_number(row.get("combined_score")),
            }
        )
    output.sort(key=lambda item: item["combined_score"], reverse=True)
    return output


def match_opinions(text: str, opinions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lowered = text.lower()
    matched = []
    for opinion in opinions:
        if opinion["keyword"].lower() in lowered:
            matched.append(opinion)
    return matched


def build_social_analysis(opinions: list[dict[str, Any]]) -> dict[str, list[str]]:
    if len(opinions) < 5:
        return {
            "consensus": ["高赞评论样本不足，暂不归纳公众共识。"],
            "controversies": ["高赞评论样本不足，暂不归纳主要争议。"],
        }
    text = " ".join([item.get("stance", "") + " " + item.get("opinion", "") for item in opinions])
    consensus = [
        "高赞评论集中关注事件对普通用户体验、价格或选择权的影响。",
        "讨论会自然延伸到平台、品牌或大公司行为背后的商业账本。",
        "多数评论不是只看单一事件，而是在比较不同公司、行业格局和长期后果。",
    ]
    controversies = [
        "争议集中在企业动作是正常竞争，还是会造成成本转嫁、体验下降或新的内卷。",
        "不同群体对事件影响判断不一致：消费者、从业者、投资者和品牌方关注点不同。",
    ]
    if "支持" in text and "质疑" in text:
        controversies[0] = "舆论同时存在支持和质疑：支持者强调效率、创新或价格收益，质疑者担心成本转嫁、垄断或体验下降。"
    return {"consensus": consensus, "controversies": controversies}


def parse_number(value: Any) -> float:
    text = clean(value)
    if not text:
        return 0.0
    multiplier = 1
    if text.endswith("万"):
        multiplier = 10000
        text = text[:-1]
    text = re.sub(r"[^0-9.]", "", text)
    try:
        return float(text or 0) * multiplier
    except ValueError:
        return 0.0


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


if __name__ == "__main__":
    raise SystemExit(main())
