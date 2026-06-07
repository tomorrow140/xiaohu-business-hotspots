#!/usr/bin/env python3
"""Enrich hotspot topic-value analysis with GitHub Models.

The script only rewrites topic analysis fields. It does not alter source facts,
scores, media links, or social-signal fields. If AI access is unavailable, it
leaves the existing data untouched so the collection workflow can still publish.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


API_URL = "https://models.github.ai/inference/chat/completions"
DEFAULT_MODEL = "openai/gpt-4.1-mini"
DATA_PREFIX = "window.XIAOHU_HOTSPOTS_DATA = "


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Use AI to create differentiated topic-value analysis.")
    parser.add_argument("--input", default="insights/hotspots-data.js", help="Frontend hotspot data file.")
    parser.add_argument("--model", default=os.getenv("AI_MODEL", DEFAULT_MODEL))
    parser.add_argument("--limit-per-industry", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when AI enrichment fails.")
    return parser.parse_args()


def read_payload(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8").strip()
    if not text.startswith(DATA_PREFIX):
        raise ValueError(f"{path} is not a supported hotspot data file")
    return json.loads(text.removeprefix(DATA_PREFIX).rstrip(" ;\n"))


def write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        DATA_PREFIX + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n",
        encoding="utf-8",
    )


def stable_id(title: str) -> str:
    return hashlib.sha1(title.encode("utf-8")).hexdigest()[:12]


def select_hotspots(hotspots: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    counts: defaultdict[str, int] = defaultdict(int)
    selected = []
    displayed_order = sorted(
        hotspots,
        key=lambda hotspot: float(hotspot.get("confidence") or 0),
        reverse=True,
    )
    for hotspot in displayed_order:
        industry = str(hotspot.get("industry") or "商业综合")
        if counts[industry] >= limit:
            continue
        counts[industry] += 1
        selected.append(hotspot)
    return selected


def compact_hotspot(hotspot: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": stable_id(str(hotspot.get("title") or "")),
        "title": hotspot.get("title"),
        "industry": hotspot.get("industry"),
        "type": hotspot.get("type"),
        "summary": hotspot.get("core_summary") or hotspot.get("summary"),
        "media_channels": hotspot.get("media_channels"),
        "media_channel_count": hotspot.get("media_channel_count"),
        "key_nodes": (hotspot.get("key_nodes") or [])[:4],
    }


def build_messages(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    system = """你是“小胡聊商业”的资深商业选题编辑。账号关注大众熟悉的大公司，用普通消费者能理解的语言解释商业竞争。

你的任务是基于给定新闻材料，为每条新闻生成独有的选题价值分析。

必须遵守：
1. 只能使用输入材料中的事实，不补造数字、内幕、舆论、结论或公司动机。
2. 每条分析必须指出该事件特有的利益冲突、反差或大众关联，不能使用“值得关注”“影响行业格局”“建议持续观察”等空话。
3. 小胡讲法要具体说明从谁的处境切入、解释什么商业机制，以及普通人为什么会关心。
4. 标题方向可以有吸引力，但不能把未证实推断写成事实。
5. 避坑提醒必须针对该新闻的事实边界，不能重复同一句话。
6. 不评价事件对错，不编造高赞评论。

仅输出 JSON，不要 Markdown。格式：
{"items":[{"id":"输入id","judgement":"1-2句选题判断","headline":"标题方向","conflict":"核心冲突","angle":"小胡讲法","risk":"避坑提醒"}]}"""
    user = "请逐条分析以下商业新闻，确保不同新闻的分析明显不同：\n" + json.dumps(
        items, ensure_ascii=False, separators=(",", ":")
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def call_model(token: str, model: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    body = json.dumps(
        {
            "model": model,
            "messages": build_messages(items),
            "response_format": {"type": "json_object"},
            "temperature": 0.35,
            "max_tokens": 5000,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=body,
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        response_payload = json.loads(response.read().decode("utf-8"))
    content = response_payload["choices"][0]["message"]["content"]
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    parsed = json.loads(content)
    return parsed.get("items", [])


def call_model_with_retries(token: str, model: str, items: list[dict[str, Any]], attempts: int = 3) -> list[dict[str, Any]]:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return call_model(token, model, items)
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code != 429 or attempt >= attempts - 1:
                break
            time.sleep(30 * (attempt + 1))
        except urllib.error.URLError as error:
            last_error = error
            if attempt >= attempts - 1:
                break
            time.sleep(10 * (attempt + 1))
    raise last_error or RuntimeError("AI model call failed")


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().rstrip("。.!！?？；;，,、 ")


def compose_topic_value(result: dict[str, Any], social_complete: bool) -> str:
    social_note = (
        "已有真实高赞舆论样本，可进一步拆分支持与质疑两派。"
        if social_complete
        else "高赞评论尚未补齐，暂不把媒体判断当成公众情绪。"
    )
    return (
        f"AI选题判断：{clean(result.get('judgement'))}。"
        f"标题方向：{clean(result.get('headline'))}。"
        f"核心冲突：{clean(result.get('conflict'))}。"
        f"小胡讲法：{clean(result.get('angle'))}。"
        f"避坑：{clean(result.get('risk'))}。"
        f"{social_note}"
    )


def valid_result(result: dict[str, Any]) -> bool:
    return all(clean(result.get(field)) for field in ("id", "judgement", "headline", "conflict", "angle", "risk"))


def enrich(payload: dict[str, Any], token: str, model: str, limit: int, batch_size: int) -> int:
    hotspots = payload.get("hotspots") or []
    selected = select_hotspots(hotspots, limit)
    results: dict[str, dict[str, Any]] = {}

    for start in range(0, len(selected), batch_size):
        batch = [compact_hotspot(item) for item in selected[start : start + batch_size]]
        for result in call_model_with_retries(token, model, batch):
            if valid_result(result):
                results[str(result["id"])] = result
        if start + batch_size < len(selected):
            time.sleep(2)

    enriched = 0
    enriched_at = datetime.now().astimezone().isoformat(timespec="seconds")
    for hotspot in hotspots:
        result = results.get(stable_id(str(hotspot.get("title") or "")))
        if not result:
            continue
        hotspot["topic_value"] = compose_topic_value(result, bool(hotspot.get("social_data_complete")))
        hotspot["topic_value_source"] = "github-models"
        hotspot["topic_value_model"] = model
        hotspot["topic_value_generated_at"] = enriched_at
        enriched += 1

    report = payload.setdefault("report", {})
    report["ai_topic_value"] = {
        "status": "completed" if enriched else "no-results",
        "model": model,
        "selected_count": len(selected),
        "enriched_count": enriched,
        "generated_at": enriched_at,
    }
    return enriched


def main() -> int:
    args = parse_args()
    path = Path(args.input)
    token = os.getenv("GITHUB_TOKEN") or os.getenv("AI_TOKEN")
    if not token:
        message = "AI enrichment skipped: set GITHUB_TOKEN or AI_TOKEN."
        print(message, file=sys.stderr)
        return 1 if args.strict else 0

    payload = read_payload(path)
    try:
        enriched = enrich(
            payload,
            token=token,
            model=args.model,
            limit=max(1, args.limit_per_industry),
            batch_size=max(1, args.batch_size),
        )
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, json.JSONDecodeError) as error:
        print(f"AI enrichment skipped: {error}", file=sys.stderr)
        return 1 if args.strict else 0

    if enriched:
        write_payload(path, payload)
    selected_count = payload.get("report", {}).get("ai_topic_value", {}).get("selected_count", 0)
    minimum = max(1, min(10, int(selected_count or 0)))
    if args.strict and enriched < minimum:
        print(
            f"AI enrichment failed quality gate: enriched {enriched}, minimum {minimum}.",
            file=sys.stderr,
        )
        return 1
    print(f"AI topic-value enrichment completed: {enriched} hotspots.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
