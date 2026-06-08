from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "hotspots"
FRONTEND_DATA = ROOT / "insights" / "hotspots-data.js"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

DEFAULT_SOURCES = [
    {
        "name": "36氪综合资讯",
        "url": "https://36kr.com/feed",
        "kind": "rss",
        "weight": 1.05,
        "enabled": True,
    },
    {
        "name": "36氪快讯",
        "url": "https://36kr.com/feed-newsflash",
        "kind": "rss",
        "weight": 0.9,
        "enabled": True,
    },
    {
        "name": "虎嗅",
        "url": "https://www.huxiu.com/",
        "kind": "html",
        "weight": 1.0,
        "enabled": True,
    },
    {
        "name": "界面新闻",
        "url": "https://www.jiemian.com/",
        "kind": "html",
        "weight": 1.0,
        "enabled": True,
    },
    {
        "name": "财新网",
        "url": "https://www.caixin.com/",
        "kind": "html",
        "weight": 1.15,
        "enabled": True,
    },
    {
        "name": "晚点 LatePost",
        "url": "https://www.latepost.com/",
        "kind": "html",
        "weight": 1.2,
        "enabled": True,
    },
]

SAMPLE_ITEMS = [
    {
        "source_name": "36氪综合资讯",
        "title": "阿里加码 AI 电商工具，商家经营进入自动化竞争",
        "url": "https://example.com/ali-ai-commerce",
        "published": "2026-05-17",
        "summary": "平台把 AI 能力继续放进搜索、推荐、素材生成和商家运营，电商竞争从买流量转向经营效率。",
        "source_weight": 1.05,
    },
    {
        "source_name": "虎嗅",
        "title": "外卖补贴战继续升级，本地生活平台争夺即时零售入口",
        "url": "https://example.com/local-life-war",
        "published": "2026-05-16",
        "summary": "外卖平台围绕补贴、配送和商家供给继续竞争，用户增长与履约成本之间的矛盾被再次放大。",
        "source_weight": 1.0,
    },
    {
        "source_name": "界面新闻",
        "title": "白酒渠道价格倒挂，经销商库存压力仍在释放",
        "url": "https://example.com/baijiu-channel",
        "published": "2026-05-15",
        "summary": "消费场景变化、库存压力和价格体系松动，让白酒行业进入新的渠道再平衡阶段。",
        "source_weight": 1.0,
    },
    {
        "source_name": "晚点 LatePost",
        "title": "新能源车企财报分化，价格战进入现金流淘汰赛",
        "url": "https://example.com/ev-cashflow",
        "published": "2026-05-14",
        "summary": "头部车企用规模和供应链继续压价，中腰部品牌在销量、毛利和融资能力上承压。",
        "source_weight": 1.2,
    },
]

INDUSTRY_RULES = [
    ("互联网行业", ["阿里", "淘宝", "天猫", "腾讯", "京东", "拼多多", "抖音", "字节", "快手", "小红书", "美团", "饿了么", "携程", "网易", "知乎", "虎牙", "游戏", "云计算", "电商", "外卖", "本地生活", "直播带货"]),
    ("新能源汽车行业", ["新能源", "车企", "电动车", "汽车", "新车", "SUV", "MPV", "智驾", "自动驾驶", "动力电池", "充电", "鸿蒙智行", "问界", "智界", "享界", "比亚迪", "小米汽车", "小米", "理想", "蔚来", "小鹏", "特斯拉", "宁德时代", "零跑"]),
    ("AI与芯片行业", ["AI", "大模型", "生成式AI", "模型", "算力", "芯片", "半导体", "英伟达", "OpenAI", "百度", "华为昇腾", "云服务", "数据中心", "长鑫科技", "存储"]),
    ("消费与新零售行业", ["白酒", "茅台", "五粮液", "瑞幸", "蜜雪冰城", "泡泡玛特", "LABUBU", "小熊电器", "叮咚买菜", "名创优品", "海底捞", "霸王茶姬", "安踏", "李宁", "茶饮", "咖啡", "餐饮", "美妆", "服饰", "快消", "线下零售", "消费", "小家电", "潮玩"]),
    ("机器人行业", ["机器人", "人形机器人", "工业机器人", "服务机器人", "具身智能", "宇树", "优必选", "Figure", "波士顿动力"]),
]

TYPE_RULES = [
    ("财报", ["财报", "营收", "净利", "利润", "毛利", "亏损", "业绩"]),
    ("公司战略", ["战略", "组织", "调整", "升级", "转型", "发布", "加码", "收购", "并购"]),
    ("行业竞争", ["大战", "价格战", "竞争", "补贴", "开战", "围攻", "争夺", "淘汰"]),
    ("舆论", ["回应", "争议", "道歉", "被质疑", "热搜", "风波", "舆论"]),
    ("政策", ["监管", "政策", "新规", "处罚", "约谈", "合规", "反垄断"]),
    ("商业模式", ["模式", "变现", "会员", "广告", "渠道", "供应链", "入口", "闭环"]),
]

XIAOHU_PATTERNS = [
    ("公司深度", ["阿里", "携程", "泡泡玛特", "公司", "巨头", "市值", "财报", "战略"], 1.35),
    ("商业模式", ["赚钱", "模式", "垄断", "增长", "利润", "估值", "供应链", "渠道"], 1.25),
    ("行业战争", ["大战", "开战", "竞争", "血洗", "爆打", "外卖", "价格战", "平台"], 1.2),
    ("消费品牌", ["泡泡玛特", "洗脸巾", "白酒", "医美", "品牌", "零售", "消费", "用户"], 1.15),
    ("平台经济", ["阿里", "携程", "美团", "抖音", "小红书", "京东", "拼多多", "平台"], 1.12),
    ("企业兴衰", ["起死回生", "衰史", "崩", "翻盘", "看衰", "兴衰", "危机", "创始人"], 1.18),
]

BUSINESS_KEYWORDS = [
    "公司",
    "商业",
    "财报",
    "利润",
    "营收",
    "增长",
    "行业",
    "平台",
    "消费",
    "品牌",
    "电商",
    "外卖",
    "AI",
    "大模型",
    "新能源",
    "出海",
    "融资",
    "IPO",
    "上市",
    "并购",
    "监管",
    "政策",
    "价格战",
    "供应链",
    "渠道",
    "市值",
    "估值",
]

HOUSEHOLD_ENTITIES = [
    "阿里",
    "淘宝",
    "天猫",
    "京东",
    "美团",
    "饿了么",
    "拼多多",
    "抖音",
    "字节",
    "快手",
    "小红书",
    "腾讯",
    "微信",
    "知乎",
    "虎牙",
    "华为",
    "余承东",
    "小米",
    "雷军",
    "比亚迪",
    "特斯拉",
    "东风",
    "Jeep",
    "Stellantis",
    "理想",
    "蔚来",
    "小鹏",
    "百度",
    "携程",
    "泡泡玛特",
    "茅台",
    "五粮液",
    "瑞幸",
    "蜜雪冰城",
    "宁德时代",
    "长鑫科技",
    "苹果",
    "英伟达",
    "OpenAI",
    "工业富联",
    "荣耀",
    "谷歌",
    "SpaceX",
    "马斯克",
    "台积电",
    "博通",
    "火山引擎",
    "大疆",
    "影石",
    "李宁",
    "安踏",
    "特步",
    "名创优品",
    "海底捞",
    "霸王茶姬",
    "宇树",
    "优必选",
]

PUBLIC_CONCERN_TERMS = [
    "外卖",
    "价格战",
    "补贴",
    "电商",
    "直播带货",
    "手机",
    "汽车",
    "新能源车",
    "自动驾驶",
    "智驾",
    "AI",
    "大模型",
    "房价",
    "楼市",
    "白酒",
    "消费",
    "涨价",
    "降价",
    "食品安全",
    "打工人",
    "裁员",
    "医保",
    "旅游",
    "出行",
    "汽车",
    "新车",
    "SUV",
    "MPV",
    "快递",
    "奶茶",
    "咖啡",
    "茶饮",
    "餐饮",
    "潮玩",
]

CORE_PUBLIC_TOPICS = [
    "外卖",
    "电商",
    "补贴",
    "白酒",
    "楼市",
    "房价",
    "直播带货",
    "潮玩",
]

NICHE_TERMS = [
    "研报",
    "基金经理",
    "化工",
    "有色",
    "宠物大模型",
    "科创板IPO招股说明书",
    "早报",
    "投资早报",
    "融资首发",
    "净息差",
    "债市",
    "衍生品",
    "结构过度复杂合约",
]

HARD_EXCLUDE_TERMS = [
    "投资早报",
    "早报|",
    "7x24",
    "快讯合集",
    "阿里健康",
    "医药",
    "医学",
    "医院",
    "医疗",
    "健康大模型",
    "宠物",
    "银行净息差",
    "不良贷款",
    "债务逾期",
    "海上安保",
    "阿曼湾",
    "硬氪首发",
    "融资首发",
    "氪星晚报",
    "出海日报",
    "特别呈现",
    "成立新汽车销售公司",
    "成立新公司",
    "行业认证",
    "样品订单",
    "拟发行",
    "控制权变更",
    "股票复牌",
    "股票停牌",
    "中文在线",
    "SpaceX",
]

MAJOR_EVENT_TERMS = [
    "争议",
    "大战",
    "内卷",
    "涨价",
    "降价",
    "补贴",
    "裁员",
    "财报",
    "营收",
    "利润",
    "亏损",
    "市值",
    "估值",
    "收购",
    "并购",
    "IPO",
    "上市",
    "监管",
    "新规",
    "回应",
    "产品发布",
    "发布新品",
    "战略",
    "合作",
    "出海",
    "价格",
    "增长",
    "份额",
    "关税",
    "开放",
    "接入",
    "反垄断",
    "风波",
    "跑路",
    "安全",
]


@dataclass
class RawItem:
    source_name: str
    title: str
    url: str
    published: str = ""
    summary: str = ""
    source_weight: float = 1.0


@dataclass
class Cluster:
    title: str
    items: list[RawItem] = field(default_factory=list)
    tokens: set[str] = field(default_factory=set)


class LinkCollector(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href")
        if not href:
            return
        self._href = urllib.parse.urljoin(self.base_url, href)
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._href:
            return
        title = clean_text(" ".join(self._text))
        if title:
            self.links.append((title, self._href))
        self._href = None
        self._text = []


def main() -> int:
    parser = argparse.ArgumentParser(description="采集商业媒体热点并输出给选题工作台导入的 CSV/JSON。")
    parser.add_argument("--days", type=int, default=7, help="保留最近多少天的内容，默认 7。HTML 来源没有日期时默认保留。")
    parser.add_argument("--limit", type=int, default=40, help="输出热点数量上限，默认 40。")
    parser.add_argument("--wechat-index", type=Path, help="微信指数手动 CSV，用于给相关关键词加权。")
    parser.add_argument("--kol-mentions", type=Path, help="大 V 提及手动 CSV，用于统计相关内容和高粉账号。")
    parser.add_argument("--video-sources", type=Path, help="抖音/B站等视频源 CSV，用于补充热点原始信息链接。")
    parser.add_argument("--social-opinions", type=Path, help="高赞舆论观点 CSV；不提供时不生成热评。")
    parser.add_argument("--raw-items", type=Path, help="复用已采集的 raw-items.json，不重新联网采集。")
    parser.add_argument("--sources", type=Path, help="可选来源配置 JSON；未提供时使用内置商业媒体来源。")
    parser.add_argument("--offline-sample", action="store_true", help="不用联网，使用内置样例验证流程。")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sources = load_sources(args.sources)
    wechat_index = load_wechat_index(args.wechat_index) if args.wechat_index else {}
    kol_mentions = load_kol_mentions(args.kol_mentions) if args.kol_mentions else []
    video_sources = load_video_sources(args.video_sources) if args.video_sources else []
    social_opinions = load_social_opinions(args.social_opinions) if args.social_opinions else []

    if args.raw_items:
        raw_items = load_raw_items(args.raw_items)
        errors = []
    elif args.offline_sample:
        raw_items = [RawItem(**item) for item in SAMPLE_ITEMS]
        errors: list[str] = []
    else:
        raw_items, errors = collect_sources(sources, args.days)

    clusters = cluster_items(raw_items)
    clusters = [cluster for cluster in clusters if is_public_hotspot(cluster)]
    hotspots = [build_hotspot(cluster, wechat_index, kol_mentions, video_sources, social_opinions) for cluster in clusters]
    hotspots.sort(key=lambda item: item["_rank_score"], reverse=True)
    hotspots = hotspots[: args.limit]

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    csv_path = OUT_DIR / f"{timestamp}-business-hotspots.csv"
    json_path = OUT_DIR / f"{timestamp}-business-hotspots.json"
    raw_path = OUT_DIR / f"{timestamp}-raw-items.json"
    report_path = OUT_DIR / f"{timestamp}-collection-report.json"

    write_hotspots_csv(csv_path, hotspots)
    write_hotspots_json(json_path, hotspots)
    raw_path.write_text(
        json.dumps([raw_item.__dict__ for raw_item in raw_items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "days": args.days,
        "source_count": len([source for source in sources if source.get("enabled", True)]),
        "raw_item_count": len(raw_items),
        "hotspot_count": len(hotspots),
        "wechat_index_file": str(args.wechat_index) if args.wechat_index else None,
        "kol_mentions_file": str(args.kol_mentions) if args.kol_mentions else None,
        "video_sources_file": str(args.video_sources) if args.video_sources else None,
        "social_opinions_file": str(args.social_opinions) if args.social_opinions else None,
        "errors": errors,
        "outputs": {
            "csv": str(csv_path),
            "json": str(json_path),
            "raw": str(raw_path),
            "report": str(report_path),
            "frontend_data": str(FRONTEND_DATA),
        },
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_frontend_data(FRONTEND_DATA, hotspots, raw_items, report)

    print(f"CSV: {csv_path}")
    print(f"JSON: {json_path}")
    print(f"RAW: {raw_path}")
    print(f"REPORT: {report_path}")
    print(f"FRONTEND_DATA: {FRONTEND_DATA}")
    if errors:
        print("\n部分来源采集失败：", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
    return 0


def load_sources(config_path: Path | None) -> list[dict[str, Any]]:
    if not config_path:
        return DEFAULT_SOURCES
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("sources config must be a list")
    return data


def load_raw_items(path: Path) -> list[RawItem]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("raw items file must contain a list")
    items = []
    for row in data:
        if not isinstance(row, dict):
            continue
        items.append(
            RawItem(
                source_name=clean_text(row.get("source_name", "")),
                title=clean_text(row.get("title", "")),
                url=clean_text(row.get("url", "")),
                published=clean_text(row.get("published", "")),
                summary=clean_text(row.get("summary", "")),
                source_weight=float(row.get("source_weight", 1.0) or 1.0),
            )
        )
    return items


def collect_sources(sources: list[dict[str, Any]], days: int) -> tuple[list[RawItem], list[str]]:
    raw_items: list[RawItem] = []
    errors: list[str] = []
    for source in sources:
        if not source.get("enabled", True):
            continue
        try:
            kind = source.get("kind", "html")
            if kind == "rss":
                items = collect_rss(source, days)
            elif kind == "html":
                items = collect_html(source)
            else:
                raise ValueError(f"unsupported source kind: {kind}")
            raw_items.extend(items)
            time.sleep(0.8)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{source.get('name', source.get('url'))}: {type(exc).__name__}: {exc}")
    return raw_items, errors


def collect_rss(source: dict[str, Any], days: int) -> list[RawItem]:
    content = fetch_url(source["url"])
    root = ElementTree.fromstring(content)
    cutoff = datetime.now().astimezone() - timedelta(days=days)
    items: list[RawItem] = []

    for node in root.findall(".//item"):
        title = clean_text(node_text(node, "title"))
        link = clean_text(node_text(node, "link"))
        summary = trim_text(clean_text(node_text(node, "description")), 220)
        published = parse_date(node_text(node, "pubDate"))
        if published and published < cutoff:
            continue
        if is_business_title(title):
            items.append(
                RawItem(
                    source_name=source["name"],
                    title=title,
                    url=link,
                    published=format_date(published),
                    summary=summary,
                    source_weight=float(source.get("weight", 1.0)),
                )
            )

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for node in root.findall(".//atom:entry", ns):
        title = clean_text(node_text(node, "atom:title", ns))
        link_node = node.find("atom:link", ns)
        link = link_node.get("href", "") if link_node is not None else ""
        summary = trim_text(clean_text(node_text(node, "atom:summary", ns) or node_text(node, "atom:content", ns)), 220)
        published = parse_date(node_text(node, "atom:published", ns) or node_text(node, "atom:updated", ns))
        if published and published < cutoff:
            continue
        if is_business_title(title):
            items.append(
                RawItem(
                    source_name=source["name"],
                    title=title,
                    url=link,
                    published=format_date(published),
                    summary=summary,
                    source_weight=float(source.get("weight", 1.0)),
                )
            )
    return items


def collect_html(source: dict[str, Any]) -> list[RawItem]:
    content = fetch_url(source["url"])
    charset = guess_charset(content)
    text = content.decode(charset, errors="replace")
    collector = LinkCollector(source["url"])
    collector.feed(text)

    items: list[RawItem] = []
    seen: set[str] = set()
    for title, url in collector.links:
        title = normalize_title(title)
        if not title or title in seen:
            continue
        if not is_business_title(title):
            continue
        if not looks_like_article_url(url):
            continue
        seen.add(title)
        items.append(
            RawItem(
                source_name=source["name"],
                title=title,
                url=url,
                published="",
                summary="",
                source_weight=float(source.get("weight", 1.0)),
            )
        )
    return items[:80]


def fetch_url(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


def node_text(node: ElementTree.Element, path: str, ns: dict[str, str] | None = None) -> str:
    found = node.find(path, ns or {})
    return "".join(found.itertext()) if found is not None else ""


def parse_date(value: str) -> datetime | None:
    value = clean_text(value)
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(value[: len(fmt)], fmt).astimezone()
        except ValueError:
            continue
    return None


def format_date(value: datetime | None) -> str:
    if not value:
        return datetime.now().strftime("%Y-%m-%d")
    return value.strftime("%Y-%m-%d")


def guess_charset(content: bytes) -> str:
    head = content[:5000].decode("ascii", errors="ignore")
    match = re.search(r"charset=['\"]?([A-Za-z0-9_-]+)", head, re.I)
    return match.group(1) if match else "utf-8"


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def trim_text(value: str, limit: int) -> str:
    value = clean_text(value)
    if len(value) <= limit:
        return value
    return value[:limit].rstrip("，。；、 ") + "..."


def normalize_title(title: str) -> str:
    title = clean_text(title)
    title = re.sub(r"^(原创|独家|深度|快讯|重磅)[｜丨\-\s：:]+", "", title)
    title = re.sub(r"[丨｜]\s*.*$", "", title)
    return title.strip()


def is_business_title(title: str) -> bool:
    if len(title) < 8 or len(title) > 90:
        return False
    if re.search(r"(登录|注册|广告|招聘|关于我们|下载|查看更多|专题|隐私|版权)", title):
        return False
    return any(keyword.lower() in title.lower() for keyword in BUSINESS_KEYWORDS)


def is_public_hotspot(cluster: Cluster) -> bool:
    text = " ".join([cluster.title] + [f"{item.title} {item.summary}" for item in cluster.items])
    if keyword_hits(text, HARD_EXCLUDE_TERMS) >= 1:
        return False
    if not infer_industry(text):
        return False
    entity_hits = keyword_hits(text, HOUSEHOLD_ENTITIES)
    core_hits = keyword_hits(text, CORE_PUBLIC_TOPICS)
    event_hits = keyword_hits(text, MAJOR_EVENT_TERMS)
    if keyword_hits(text, NICHE_TERMS) >= 1 and entity_hits == 0:
        return False
    return event_hits >= 1 and (entity_hits >= 1 or core_hits >= 1)


def public_topic_score(text: str) -> float:
    entity_hits = keyword_hits(text, HOUSEHOLD_ENTITIES)
    concern_hits = keyword_hits(text, PUBLIC_CONCERN_TERMS)
    source_bonus = 0.5 if keyword_hits(text, ["36氪", "虎嗅", "界面", "财新", "晚点"]) else 0
    return entity_hits * 1.4 + concern_hits * 0.8 + source_bonus


def infer_industry(text: str) -> str:
    if keyword_hits(text, ["机器人", "人形机器人", "工业机器人", "服务机器人", "具身智能", "宇树", "优必选", "Figure", "波士顿动力"]):
        return "机器人行业"
    if keyword_hits(text, ["工业富联", "英伟达", "台积电", "博通", "长鑫科技", "芯片", "半导体", "AI智能体", "大模型", "DeepSeek"]):
        return "AI与芯片行业"
    if keyword_hits(text, ["外卖", "即时零售", "淘宝闪购"]):
        return "互联网行业"
    if keyword_hits(text, ["泡泡玛特", "LABUBU", "小熊电器", "叮咚买菜", "潮玩", "小家电", "名创优品", "海底捞", "霸王茶姬", "安踏", "李宁", "瑞幸", "蜜雪冰城", "茅台"]):
        return "消费与新零售行业"
    if keyword_hits(text, ["新能源", "车企", "电动车", "汽车", "新车", "SUV", "MPV", "智驾", "比亚迪", "小米汽车", "特斯拉", "理想", "蔚来", "小鹏"]):
        return "新能源汽车行业"
    return infer_label(text, INDUSTRY_RULES, "")


def looks_like_article_url(url: str) -> bool:
    if not url.startswith("http"):
        return False
    blocked = ["javascript:", "#", "/about", "/user", "/login", "/search", "/app", "/download"]
    if any(part in url for part in blocked):
        return False
    return bool(re.search(r"(\d{4,}|article|news|post|p/|story|detail)", url, re.I))


def cluster_items(raw_items: list[RawItem]) -> list[Cluster]:
    clusters: list[Cluster] = []
    for item in raw_items:
        tokens = title_tokens(item.title)
        if not tokens:
            continue
        item_text = f"{item.title} {item.summary}"
        item_topic_key = topic_cluster_key(item_text)
        matched = None
        for cluster in clusters:
            if item.url and any(existing.url == item.url for existing in cluster.items):
                matched = cluster
                break
            cluster_text = " ".join([cluster.title] + [f"{existing.title} {existing.summary}" for existing in cluster.items])
            cluster_topic_key = topic_cluster_key(cluster_text)
            if item_topic_key and item_topic_key == cluster_topic_key:
                matched = cluster
                break
            similarity = jaccard(tokens, cluster.tokens)
            if similarity >= 0.46 or normalize_key(item.title) == normalize_key(cluster.title):
                matched = cluster
                break
        if matched:
            matched.items.append(item)
            matched.tokens.update(tokens)
        else:
            clusters.append(Cluster(title=item.title, items=[item], tokens=tokens))
    return clusters


def topic_cluster_key(text: str) -> str:
    lowered = text.lower()
    if "叮咚买菜" in text:
        return "叮咚买菜美团交易"
    if "京东" in text and "外卖" in text and any(term in text for term in ["财报", "Q1", "一季度", "业绩", "营收", "减亏"]):
        return "京东财报与外卖投入"
    if "阿里" in text and any(term in text for term in ["财报", "Q4", "云", "AI"]):
        return "阿里云AI与财报"
    rules = [
        ("京东财报与外卖投入", ["京东", "财报", "外卖"], 3),
        ("外卖/即时零售大战", ["外卖", "即时零售", "淘宝闪购", "美团"], 2),
        ("AI电商/618购物入口", ["AI", "电商", "购物", "千问", "豆包", "618"], 2),
        ("互联网大厂AI投入与财报", ["阿里", "腾讯", "京东", "财报", "AI投入"], 3),
        ("长鑫科技国产DRAM IPO", ["长鑫科技", "DRAM", "IPO", "招股"], 2),
        ("人形机器人融资上市", ["人形机器人", "机器人", "宇树", "优必选", "智元", "融资", "IPO"], 2),
        ("泡泡玛特LABUBU溢价争议", ["泡泡玛特", "LABUBU", "小家电", "联名", "毛利率", "成本"], 2),
        ("新能源车涨价潮", ["新能源", "车企", "涨价", "价格战", "特斯拉", "比亚迪", "小米汽车"], 2),
        ("小米/鸿蒙智行新能源新车", ["小米", "鸿蒙智行", "SUV", "MPV", "新车"], 2),
        ("比亚迪海外产能", ["比亚迪", "欧洲", "海外", "工厂"], 2),
    ]
    for key, keywords, min_hits in rules:
        hits = sum(1 for keyword in keywords if keyword.lower() in lowered)
        if hits >= min_hits:
            return key
    return ""


def title_tokens(title: str) -> set[str]:
    candidates = set(re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fa5]{2,}", title))
    keywords = {keyword for keyword in BUSINESS_KEYWORDS if keyword.lower() in title.lower()}
    return candidates | keywords


def normalize_key(title: str) -> str:
    return re.sub(r"[\W_]+", "", title.lower())


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def build_hotspot(
    cluster: Cluster,
    wechat_index: dict[str, dict[str, Any]],
    kol_mentions: list[dict[str, Any]],
    video_sources: list[dict[str, Any]],
    social_opinions: list[dict[str, Any]],
) -> dict[str, Any]:
    best = max(cluster.items, key=lambda item: len(item.summary) + item.source_weight * 20)
    title = choose_display_title(cluster)
    text = " ".join([item.title + " " + item.summary for item in cluster.items])
    industry = infer_industry(text) or "商业综合"
    event_type = infer_label(text, TYPE_RULES, "公司/行业动态")
    matched_wechat = match_wechat_index(text, wechat_index)
    matched_kols = match_kol_mentions(text, kol_mentions)
    matched_videos = match_video_sources(text, video_sources)
    matched_opinions = match_social_opinions(text, social_opinions)
    media_names = sorted({item.source_name for item in cluster.items})
    source_parts = media_names[:4]
    if matched_wechat:
        source_parts.append(
            "微信指数：" + "、".join(
                f"{item['keyword']}={item['index']}" for item in matched_wechat[:3]
            )
        )

    business_value = score_business_value(text, cluster.items)
    controversy = score_controversy(text)
    longevity = score_longevity(text)
    fit = score_xiaohu_fit(text)
    public_score = public_topic_score(text)
    wechat_boost = sum(item["score"] for item in matched_wechat[:3])
    kol_boost = score_kol_confidence(matched_kols)
    video_boost = score_video_confidence(matched_videos)
    difficulty = infer_difficulty(text, len(cluster.items), matched_wechat)
    risk = infer_risk(text, event_type)
    difficulty_reverse = {"低": 10, "中": 7, "高": 4}[difficulty]
    risk_reverse = {"低": 10, "中": 7, "高": 4}[risk]
    rank_score = (
        business_value * 0.24
        + controversy * 0.14
        + longevity * 0.2
        + fit * 0.24
        + min(10, wechat_boost) * 0.06
        + kol_boost * 0.08
        + video_boost * 0.04
        + min(10, public_score) * 0.08
        + difficulty_reverse * 0.04
        + risk_reverse * 0.04
    )
    confidence = compute_confidence(media_names, matched_kols, matched_videos, matched_wechat, cluster.items)

    summary = best.summary or synthesize_summary(title, industry, event_type)
    core_summary = synthesize_core_summary(title, summary, industry, event_type)
    why_now = synthesize_why_now(cluster, matched_wechat)
    business_angle = synthesize_business_angle(title, text, industry, event_type)
    social_analysis = build_social_analysis(matched_opinions)

    return {
        "title": title,
        "source": "；".join(source_parts),
        "date": best.published or datetime.now().strftime("%Y-%m-%d"),
        "industry": industry,
        "type": event_type,
        "summary": summary,
        "core_summary": core_summary,
        "key_nodes": build_key_nodes(cluster, event_type),
        "social_opinions": matched_opinions[:5],
        "public_consensus": social_analysis["consensus"],
        "public_controversies": social_analysis["controversies"],
        "social_data_complete": len(matched_opinions) >= 5,
        "why_now": why_now,
        "business_angle": business_angle,
        "topic_value": synthesize_topic_value(title, text, industry, event_type, matched_opinions),
        "risk": risk,
        "difficulty": difficulty,
        "media_channel_count": len(media_names),
        "media_channels": "、".join(media_names),
        "media_items": format_media_items(cluster),
        "big_v_count": len(matched_kols),
        "big_v_highlights": format_kol_highlights(matched_kols),
        "big_v_items": matched_kols[:5],
        "video_source_count": len(matched_videos),
        "video_items": format_video_items(matched_videos),
        "wechat_index": format_wechat_index(matched_wechat),
        "confidence": confidence,
        "confidence_reason": synthesize_confidence_reason(media_names, matched_kols, matched_videos, matched_wechat, confidence),
        "public_interest": round(min(10, public_score), 1),
        "businessValue": round(business_value, 1),
        "controversy": round(controversy, 1),
        "longevity": round(longevity, 1),
        "fit": round(fit, 1),
        "volume": infer_volume(difficulty, longevity),
        "note": build_note(cluster, matched_wechat),
        "_rank_score": round(rank_score, 3),
    }


def format_media_items(cluster: Cluster) -> list[dict[str, str]]:
    items = []
    seen: set[str] = set()
    for item in cluster.items:
        key = item.url or item.title
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "source": item.source_name,
                "title": item.title,
                "url": item.url,
                "date": item.published,
            }
        )
    return items[:5]


def choose_display_title(cluster: Cluster) -> str:
    def score(item: RawItem) -> float:
        title = item.title
        value = item.source_weight
        if len(title) <= 42:
            value += 2.0
        if any(mark in title for mark in ["【评论】", "｜", "|", "：", "？"]):
            value += 0.8
        if len(title) > 70 or title.endswith(("。", "。", ".")):
            value -= 1.4
        if keyword_hits(title, HARD_EXCLUDE_TERMS):
            value -= 10
        return value

    return max(cluster.items, key=score).title


def infer_label(text: str, rules: list[tuple[str, list[str]]], fallback: str) -> str:
    scores = []
    lowered = text.lower()
    for label, keywords in rules:
        score = sum(1 for keyword in keywords if keyword.lower() in lowered)
        if score:
            scores.append((score, label))
    if not scores:
        return fallback
    return sorted(scores, reverse=True)[0][1]


def score_business_value(text: str, items: list[RawItem]) -> float:
    keywords = ["财报", "利润", "营收", "估值", "市值", "战略", "并购", "融资", "IPO", "供应链", "渠道", "平台"]
    base = 5.8 + min(2.2, len(items) * 0.35)
    return clamp_score(base + keyword_hits(text, keywords) * 0.42 + max(item.source_weight for item in items) * 0.5)


def score_controversy(text: str) -> float:
    keywords = ["争议", "回应", "风波", "价格战", "补贴", "监管", "约谈", "处罚", "危机", "亏损", "倒挂", "裁员"]
    return clamp_score(5.0 + keyword_hits(text, keywords) * 0.65)


def score_longevity(text: str) -> float:
    keywords = ["模式", "周期", "行业", "转型", "组织", "战略", "全球", "供应链", "渠道", "平台", "基础设施"]
    return clamp_score(5.7 + keyword_hits(text, keywords) * 0.52)


def score_xiaohu_fit(text: str) -> float:
    score = 5.6
    for _, keywords, weight in XIAOHU_PATTERNS:
        hits = keyword_hits(text, keywords)
        if hits:
            score += min(1.8, hits * 0.38 * weight)
    return clamp_score(score)


def keyword_hits(text: str, keywords: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for keyword in keywords if keyword.lower() in lowered)


def clamp_score(value: float) -> float:
    return min(10.0, max(0.0, round(value, 1)))


def infer_difficulty(text: str, source_count: int, matched_wechat: list[dict[str, Any]]) -> str:
    if source_count >= 3 and matched_wechat:
        return "中"
    if keyword_hits(text, ["财报", "监管", "并购", "政策", "供应链", "海外", "IPO"]) >= 2:
        return "高"
    if source_count <= 1:
        return "中"
    return "低"


def infer_risk(text: str, event_type: str) -> str:
    if event_type in {"舆论", "政策"}:
        return "中"
    if keyword_hits(text, ["爆料", "传闻", "网传", "裁员", "处罚", "约谈", "监管", "财务造假"]) >= 2:
        return "高"
    if keyword_hits(text, ["回应", "争议", "亏损", "倒挂", "价格战"]) >= 2:
        return "中"
    return "低"


def infer_volume(difficulty: str, longevity: float) -> str:
    if difficulty == "高" or longevity >= 8.3:
        return "长"
    if difficulty == "低" and longevity < 7.0:
        return "短"
    return "中"


def synthesize_summary(title: str, industry: str, event_type: str) -> str:
    return f"{title}。该事件属于{industry}的{event_type}，需要结合公司动作、行业格局和商业模式变化判断选题价值。"


def synthesize_core_summary(title: str, summary: str, industry: str, event_type: str) -> str:
    base = summary or synthesize_summary(title, industry, event_type)
    base = clean_text(base)
    if len(base) < 100:
        base = (
            f"{base} 该事件涉及{industry}头部公司或知名平台的{event_type}，"
            "会影响行业竞争格局、消费者体验或资本市场预期，适合作为本周商业热点持续观察。"
        )
    return trim_text(base, 200)


def build_key_nodes(cluster: Cluster, event_type: str) -> list[str]:
    items = sorted(cluster.items, key=lambda item: item.published or "", reverse=True)
    nodes = []
    for item in items[:4]:
        date = item.published or "时间未记录"
        nodes.append(f"{date}：{item.source_name}报道/收录《{item.title}》。")
    if len(nodes) < 3:
        nodes.append(f"事件类型被归类为{event_type}，需要继续核对后续公开报道。")
    return nodes[:5]


def synthesize_why_now(cluster: Cluster, matched_wechat: list[dict[str, Any]]) -> str:
    source_count = len({item.source_name for item in cluster.items})
    if matched_wechat:
        names = "、".join(item["keyword"] for item in matched_wechat[:3])
        return f"本周至少 {source_count} 个媒体入口出现相关信息，且微信指数关键词 {names} 有热度，可作为公众兴趣校准。"
    return f"本周至少 {source_count} 个媒体入口出现相关信息，适合先判断是否具备跨平台传播和商业解释空间。"


def synthesize_business_angle(title: str, text: str, industry: str, event_type: str) -> str:
    strategy = topic_strategy(title, text)
    if strategy:
        return strategy["angle"]
    fallback = fallback_topic_strategy(title, text, industry, event_type)
    if fallback:
        return fallback["angle"]
    if event_type == "行业竞争":
        return f"从{industry}的成本结构、补贴效率和赢家通吃逻辑切入，解释这场竞争最后会由谁买单。"
    if event_type == "财报":
        return f"从收入质量、利润弹性和现金流拆解，判断这家公司是真增长还是周期性修复。"
    if event_type == "政策":
        return f"从监管目标、平台激励和行业秩序重建切入，解释政策如何改变商业预期。"
    if event_type == "商业模式":
        return f"从用户、渠道和变现链路切入，解释这个模式为什么现在成立，天花板又在哪里。"
    return f"围绕“{title}”背后的利益分配和行业排位变化，提炼一个适合长视频的商业判断。"


def synthesize_topic_value(
    title: str,
    text: str,
    industry: str,
    event_type: str,
    matched_opinions: list[dict[str, Any]],
) -> str:
    social_note = "已有高赞舆论样本，可进一步拆分支持/质疑两派。" if len(matched_opinions) >= 5 else "高赞评论尚未补齐，评论区结论先留白，避免把媒体判断当成公众情绪。"
    strategy = topic_strategy(title, text)
    if not strategy:
        strategy = fallback_topic_strategy(title, text, industry, event_type)
    if strategy:
        return (
            f"标题方向：{strip_sentence_end(strategy['headline'])}。核心冲突：{strip_sentence_end(strategy['conflict'])}。"
            f"小胡讲法：{strip_sentence_end(strategy['angle'])}。避坑：{strip_sentence_end(strategy['risk'])}。{social_note}"
        )
    return f"该热点涉及{industry}的{event_type}，建议先找到一个具体商业冲突，再判断是否具备争议、反差和跨圈层讨论。{social_note}"


def topic_strategy(title: str, text: str) -> dict[str, str] | None:
    combined = f"{title} {text}"
    if "财报" in title and any(term in title for term in ["阿里", "京东", "腾讯", "大厂"]):
        return {
            "headline": "大厂财报都在说 AI，但真正的问题是利润去哪了",
            "conflict": "收入增长、AI 投入和新业务烧钱同时发生，资本市场关心的是 AI 何时从故事变成利润。",
            "angle": "把阿里、腾讯、京东放在一张表里讲：谁用 AI 拉云收入，谁用外卖换用户频次，谁在用利润换未来入口。",
            "risk": "避免堆财报数字，必须把指标翻译成一句商业判断：增长质量、利润压力和下一轮入口下注。",
        }
    if any(term in title for term in ["AI电商", "千问", "豆包", "AI购物"]):
        return {
            "headline": "淘宝和豆包都在抢一个新入口：以后购物先问 AI 吗",
            "conflict": "传统电商靠搜索、推荐和低价，AI 电商想把用户决策前置到对话框，平台入口可能重新洗牌。",
            "angle": "从普通人的购物路径切入：搜商品、比价格、算优惠、看评价哪些环节会被 AI 接管，再讲阿里和字节的入口争夺。",
            "risk": "不要把 AI 电商讲成技术发布会，重点放在流量入口、佣金分配和商家经营成本变化。",
        }
    if "外卖" in title or "即时零售" in title:
        return {
            "headline": "外卖大战不是补贴战，是美团入口保卫战",
            "conflict": "用户想要便宜、商家担心被平台抽走利润，平台则用补贴换日活和即时零售入口。",
            "angle": "用“谁在买单”做主线，拆用户、商家、骑手、平台四方账本，再解释京东和阿里为什么一定要打进美团腹地。",
            "risk": "不要简单站队美团或京东，也不要把短期补贴直接等同于长期胜负。",
        }
    if any(term in title for term in ["泡泡玛特", "LABUBU"]):
        return {
            "headline": "LABUBU越火，泡泡玛特越像一家奢侈品公司吗",
            "conflict": "消费者把潮玩当社交货币和投资品，品牌享受高溢价，但黄牛炒作、成本上行和毛利率压力会反过来考验泡泡玛特。",
            "angle": "用“一个小玩偶为什么能带火小家电”切入，拆IP溢价、跨界联名、二手炒作和海外增长四条线。",
            "risk": "不要把二级市场炒价等同于公司真实收入，也不要只讲猎奇价格，要落到IP商业化和品牌可持续。",
        }
    if "叮咚买菜" in title:
        return {
            "headline": "叮咚买菜终于赚钱了，为什么还要靠美团",
            "conflict": "生鲜电商从烧钱扩张走到盈利验证，但平台交易又意味着流量、履约和独立性都要重新算账。",
            "angle": "用“生鲜电商十年亏损后终于算账”切入，讲叮咚买菜的盈利质量、美团入口价值和华东即时零售格局。",
            "risk": "不要把单季盈利直接讲成模式胜利，要区分经营效率改善、交易过渡期和平台协同预期。",
        }
    if "涨价" in title and any(term in title for term in ["车企", "新能源", "价格战"]):
        return {
            "headline": "新能源车不打价格战了，为什么突然集体涨价",
            "conflict": "消费者习惯等降价，车企却需要修复利润，涨价潮让“买早亏、买晚贵”的情绪重新发酵。",
            "angle": "用普通消费者的买车心理切入，解释车企从抢销量转向保利润，以及价格战结束到底对谁有利。",
            "risk": "不要只罗列涨价品牌，要区分真涨价、权益回收和配置变化，避免把短期营销动作讲成行业拐点。",
        }
    if any(term in combined for term in ["AI电商", "千问", "豆包", "AI购物"]):
        return {
            "headline": "淘宝和豆包都在抢一个新入口：以后购物先问 AI 吗",
            "conflict": "传统电商靠搜索、推荐和低价，AI 电商想把用户决策前置到对话框，平台入口可能重新洗牌。",
            "angle": "从普通人的购物路径切入：搜商品、比价格、算优惠、看评价哪些环节会被 AI 接管，再讲阿里和字节的入口争夺。",
            "risk": "不要把 AI 电商讲成技术发布会，重点放在流量入口、佣金分配和商家经营成本变化。",
        }
    if "外卖" in combined and any(term in combined for term in ["即时零售", "美团", "补贴", "京东外卖"]):
        return {
            "headline": "外卖大战不是补贴战，是美团入口保卫战",
            "conflict": "用户想要便宜、商家担心被平台抽走利润，平台则用补贴换日活和即时零售入口。",
            "angle": "用“谁在买单”做主线，拆用户、商家、骑手、平台四方账本，再解释京东和阿里为什么一定要打进美团腹地。",
            "risk": "不要简单站队美团或京东，也不要把短期补贴直接等同于长期胜负。",
        }
    if "财报" in combined and all(term in combined for term in ["阿里", "京东"]) and "AI" in combined:
        return {
            "headline": "大厂财报都在说 AI，但真正的问题是利润去哪了",
            "conflict": "收入增长、AI 投入和新业务烧钱同时发生，资本市场关心的是 AI 何时从故事变成利润。",
            "angle": "把阿里、腾讯、京东放在一张表里讲：谁用 AI 拉云收入，谁用外卖换用户频次，谁在用利润换未来入口。",
            "risk": "避免堆财报数字，必须把指标翻译成一句商业判断：增长质量、利润压力和下一轮入口下注。",
        }
    strategies = [
        (
            ["阿里", "腾讯", "京东", "财报", "AI投入"],
            {
                "headline": "大厂财报都在说 AI，但真正的问题是利润去哪了",
                "conflict": "收入增长、AI 投入和新业务烧钱同时发生，资本市场关心的是 AI 何时从故事变成利润。",
                "angle": "把阿里、腾讯、京东放在一张表里讲：谁用 AI 拉云收入，谁用外卖换用户频次，谁在用利润换未来入口。",
                "risk": "避免堆财报数字，必须把指标翻译成一句商业判断：增长质量、利润压力和下一轮入口下注。",
            },
        ),
        (
            ["AI电商", "千问", "豆包", "AI购物"],
            {
                "headline": "淘宝和豆包都在抢一个新入口：以后购物先问 AI 吗",
                "conflict": "传统电商靠搜索、推荐和低价，AI 电商想把用户决策前置到对话框，平台入口可能重新洗牌。",
                "angle": "从普通人的购物路径切入：搜商品、比价格、算优惠、看评价哪些环节会被 AI 接管，再讲阿里和字节的入口争夺。",
                "risk": "不要把 AI 电商讲成技术发布会，重点放在流量入口、佣金分配和商家经营成本变化。",
            },
        ),
        (
            ["外卖", "即时零售", "美团"],
            {
                "headline": "外卖大战不是补贴战，是美团入口保卫战",
                "conflict": "用户想要便宜、商家担心被平台抽走利润，平台则用补贴换日活和即时零售入口。",
                "angle": "用“谁在买单”做主线，拆用户、商家、骑手、平台四方账本，再解释京东和阿里为什么一定要打进美团腹地。",
                "risk": "不要简单站队美团或京东，也不要把短期补贴直接等同于长期胜负。",
            },
        ),
        (
            ["叮咚买菜", "美团", "生鲜"],
            {
                "headline": "叮咚买菜终于赚钱了，为什么还要靠美团",
                "conflict": "生鲜电商从烧钱扩张走到盈利验证，但平台交易又意味着流量、履约和独立性都要重新算账。",
                "angle": "用“生鲜电商十年亏损后终于算账”切入，讲叮咚买菜的盈利质量、美团入口价值和华东即时零售格局。",
                "risk": "不要把单季盈利直接讲成模式胜利，要区分经营效率改善、交易过渡期和平台协同预期。",
            },
        ),
        (
            ["泡泡玛特", "LABUBU", "小家电"],
            {
                "headline": "LABUBU越火，泡泡玛特越像一家奢侈品公司吗",
                "conflict": "消费者把潮玩当社交货币和投资品，品牌享受高溢价，但黄牛炒作、成本上行和毛利率压力会反过来考验泡泡玛特。",
                "angle": "用“一个小玩偶为什么能带火小家电”切入，拆IP溢价、跨界联名、二手炒作和海外增长四条线。",
                "risk": "不要把二级市场炒价等同于公司真实收入，也不要只讲猎奇价格，要落到IP商业化和品牌可持续。",
            },
        ),
        (
            ["涨价", "新能源", "车企"],
            {
                "headline": "新能源车不打价格战了，为什么突然集体涨价",
                "conflict": "消费者习惯等降价，车企却需要修复利润，涨价潮让“买早亏、买晚贵”的情绪重新发酵。",
                "angle": "用普通消费者的买车心理切入，解释车企从抢销量转向保利润，以及价格战结束到底对谁有利。",
                "risk": "不要只罗列涨价品牌，要区分真涨价、权益回收和配置变化，避免把短期营销动作讲成行业拐点。",
            },
        ),
        (
            ["长鑫科技", "DRAM", "存储", "IPO"],
            {
                "headline": "AI 火了，为什么存储芯片公司先暴涨",
                "conflict": "大众关注大模型和 GPU，但产业链里存储价格、国产替代和 IPO 估值也在吃 AI 红利。",
                "angle": "用“谁在 AI 浪潮里闷声赚钱”做切口，解释 DRAM 在算力链条中的位置，再讲国产存储为什么突然被资本重估。",
                "risk": "芯片细节不要过深，少讲制程参数，多讲供需、国产替代和估值预期。",
            },
        ),
        (
            ["机器人", "人形机器人", "宇树", "优必选", "智元"],
            {
                "headline": "人形机器人到底是产业爆发，还是资本抢跑",
                "conflict": "融资和上市热度很高，但真正量产、交付和商业回款仍需要验证。",
                "angle": "从“为什么资本突然扎堆”切入，拆三件事：技术成熟度、工厂场景落地、上市窗口期。",
                "risk": "不要把演示视频等同于商业化，重点追问订单、成本和真实场景。",
            },
        ),
        (
            ["小米", "鸿蒙智行", "SUV", "MPV", "新车"],
            {
                "headline": "新能源车又卷到家庭车：小米和华为系都在抢客厅",
                "conflict": "新能源竞争从续航、价格转向家庭场景和智能座舱，车企在抢家庭预算而不只是汽车预算。",
                "angle": "用家庭用户决策链切入：空间、智驾、品牌信任和生态绑定，解释为什么 SUV/MPV 成为新战场。",
                "risk": "不要做车型导购，重点讲车企战略和用户心智变化。",
            },
        ),
        (
            ["比亚迪", "欧洲", "海外", "工厂"],
            {
                "headline": "比亚迪出海下一步：买工厂比卖车更重要吗",
                "conflict": "中国车企出海不只是出口，还要面对关税、产能、本地就业和品牌信任。",
                "angle": "从“为什么要在欧洲接工厂”切入，讲比亚迪如何从出口商变成全球制造玩家。",
                "risk": "海外并购信息要严格引用公开报道，避免过度推断交易细节。",
            },
        ),
    ]
    for keywords, strategy in strategies:
        if sum(1 for keyword in keywords if keyword in combined) >= 2:
            return strategy
    return None


def fallback_topic_strategy(title: str, text: str, industry: str, event_type: str) -> dict[str, str] | None:
    combined = f"{title} {text}"
    subject = extract_subject(title, industry)
    if industry == "互联网行业":
        if event_type == "财报":
            return {
                "headline": f"{subject}这份财报，真正要看用户增长还是利润质量",
                "conflict": "大平台既要给资本市场交利润，又要继续投新入口，短期利润和长期防守之间存在拉扯。",
                "angle": "从普通人能感知的服务频次切入，拆这家公司到底靠广告、电商、会员、云或本地生活哪条线撑增长。",
                "risk": "不要只读营收和净利，要把一次性因素、补贴投入和新业务亏损拆开看。",
            }
        return {
            "headline": f"{subject}的新动作，是抢用户时间还是抢交易入口",
            "conflict": "平台想扩大使用场景，用户关心价格和体验，商家则担心流量规则和成本变化。",
            "angle": "用一个用户日常场景开头，再解释平台为什么要从内容、支付、外卖或电商里多拿一个入口。",
            "risk": "不要把产品更新直接讲成战略胜负，先区分已发布事实和市场猜测。",
        }
    if industry == "消费与新零售行业":
        return {
            "headline": f"{subject}的热度背后，是品牌溢价还是消费降级",
            "conflict": "消费者一边追求情绪价值和性价比，一边对涨价、缩水、排队和黄牛更敏感，品牌增长很容易转成信任考验。",
            "angle": "从普通消费者的一笔账切入，讲价格、渠道、供应链和品牌故事如何共同决定这门生意能不能持续。",
            "risk": "不要把社交平台热度等同于真实复购，也不要用个别门店或个别商品代表整个品牌。",
        }
    if industry == "新能源汽车行业":
        return {
            "headline": f"{subject}这次变化，谁在为新能源车内卷买单",
            "conflict": "车企要销量、利润和智能化投入，消费者则担心刚买就降价、配置缩水或服务不稳定。",
            "angle": "从家庭买车决策切入，把价格、智驾、售后和品牌安全感放在一起讲，而不是做车型参数导购。",
            "risk": "不要用单月销量或单款车型推断公司长期胜负，需区分官方披露、媒体报道和市场预期。",
        }
    if industry == "AI与芯片行业":
        return {
            "headline": f"{subject}的 AI 故事，最后要落到成本还是收入",
            "conflict": "市场愿意为 AI 想象力买单，但企业必须证明算力、芯片或模型投入能转化为订单、利润和用户效率。",
            "angle": "用“谁付钱、谁省钱、谁被替代”三问切入，把复杂技术翻译成商业账本。",
            "risk": "不要展开过多技术细节，也不要把概念热度直接等同于商业化落地。",
        }
    if industry == "机器人行业":
        return {
            "headline": f"{subject}火起来以后，机器人离真实赚钱还有多远",
            "conflict": "展示和融资带来想象力，但量产成本、稳定交付和真实场景订单才决定公司能否穿越热度。",
            "angle": "从一个具体使用场景切入，解释机器人公司要跨过演示、试点、批量交付和售后维护四道门槛。",
            "risk": "不要把发布会视频和样机演示等同于规模商业化，重点核对订单、价格和交付对象。",
        }
    return None


def extract_subject(title: str, industry: str) -> str:
    candidates = [
        "阿里", "腾讯", "京东", "美团", "字节", "华为", "小米", "比亚迪", "理想", "小鹏", "蔚来",
        "泡泡玛特", "瑞幸", "名创优品", "海底捞", "霸王茶姬", "安踏", "李宁", "长鑫科技", "英伟达",
        "宇树", "优必选", "智元", "特斯拉",
    ]
    for candidate in candidates:
        if candidate in title:
            return candidate
    compact = re.sub(r"[【】\[\]（）()｜|:：,，。].*$", "", clean_text(title))
    if compact:
        return trim_text(compact, 18)
    return industry.replace("行业", "")


def strip_sentence_end(value: str) -> str:
    return clean_text(value).rstrip("。.!！?？；;，,、 ")


def build_note(cluster: Cluster, matched_wechat: list[dict[str, Any]]) -> str:
    links = [f"{item.source_name}: {item.url}" for item in cluster.items[:3] if item.url]
    index_note = ""
    if matched_wechat:
        index_note = "；微信指数参考：" + "、".join(
            f"{item['keyword']}({item['index']}, {item.get('trend', '未知趋势')})"
            for item in matched_wechat[:3]
        )
    return "待核查来源：" + " | ".join(links) + index_note


def load_wechat_index(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        keyword = clean_text(row.get("keyword") or row.get("关键词") or "")
        if not keyword:
            continue
        index_value = clean_text(row.get("index") or row.get("微信指数") or row.get("hot_index") or "0")
        trend = clean_text(row.get("trend") or row.get("趋势") or "")
        note = clean_text(row.get("note") or row.get("备注") or "")
        numeric = parse_number(index_value)
        result[keyword] = {
            "keyword": keyword,
            "index": index_value,
            "numeric_index": numeric,
            "trend": trend,
            "note": note,
        }
    return result


def parse_number(value: str) -> float:
    value = value.replace(",", "").strip()
    match = re.search(r"\d+(?:\.\d+)?", value)
    if not match:
        return 0.0
    number = float(match.group(0))
    if "亿" in value:
        number *= 100000000
    elif "万" in value:
        number *= 10000
    return number


def match_wechat_index(text: str, wechat_index: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    matched = []
    for keyword, item in wechat_index.items():
        if keyword not in text:
            continue
        numeric = item.get("numeric_index", 0.0)
        score = min(10.0, math.log10(max(numeric, 10)) * 1.3)
        trend = item.get("trend", "")
        if any(word in trend for word in ["升", "涨", "上行", "增长"]):
            score += 0.8
        elif any(word in trend for word in ["降", "跌", "下行"]):
            score -= 0.5
        matched.append({**item, "score": clamp_score(score)})
    matched.sort(key=lambda item: item["score"], reverse=True)
    return matched


def load_kol_mentions(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    mentions: list[dict[str, Any]] = []
    for row in rows:
        keyword = clean_text(row.get("keyword") or row.get("关键词") or "")
        author = clean_text(row.get("author") or row.get("大V") or row.get("账号") or "")
        title = clean_text(row.get("title") or row.get("内容标题") or "")
        if not keyword or not author or not title:
            continue
        mentions.append(
            {
                "keyword": keyword,
                "platform": clean_text(row.get("platform") or row.get("平台") or ""),
                "author": author,
                "followers": clean_text(row.get("followers") or row.get("粉丝量") or ""),
                "numeric_followers": parse_number(row.get("followers") or row.get("粉丝量") or "0"),
                "title": title,
                "url": clean_text(row.get("url") or row.get("链接") or ""),
                "date": clean_text(row.get("date") or row.get("日期") or ""),
            }
        )
    return mentions


def match_kol_mentions(text: str, mentions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matched = []
    lowered = text.lower()
    for mention in mentions:
        keyword = mention["keyword"]
        if keyword.lower() in lowered:
            matched.append(mention)
    matched.sort(key=lambda item: item.get("numeric_followers", 0), reverse=True)
    return matched


def load_video_sources(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    videos: list[dict[str, Any]] = []
    for row in rows:
        keyword = clean_text(row.get("keyword") or row.get("关键词") or "")
        platform = clean_text(row.get("platform") or row.get("平台") or "")
        title = clean_text(row.get("title") or row.get("视频标题") or row.get("内容标题") or "")
        url = clean_text(row.get("url") or row.get("链接") or row.get("视频链接") or "")
        if not keyword or not platform or not title or not url:
            continue
        videos.append(
            {
                "keyword": keyword,
                "platform": platform,
                "author": clean_text(row.get("author") or row.get("账号") or row.get("UP主") or row.get("作者") or ""),
                "title": title,
                "url": url,
                "date": clean_text(row.get("date") or row.get("日期") or row.get("发布时间") or ""),
                "views": clean_text(row.get("views") or row.get("播放量") or row.get("观看量") or ""),
                "likes": clean_text(row.get("likes") or row.get("点赞数") or ""),
                "comments": clean_text(row.get("comments") or row.get("评论数") or ""),
                "numeric_views": parse_number(row.get("views") or row.get("播放量") or row.get("观看量") or "0"),
                "numeric_likes": parse_number(row.get("likes") or row.get("点赞数") or "0"),
                "numeric_comments": parse_number(row.get("comments") or row.get("评论数") or "0"),
                "note": clean_text(row.get("note") or row.get("备注") or ""),
            }
        )
    return videos


def match_video_sources(text: str, videos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matched = []
    lowered = text.lower()
    for video in videos:
        keyword = video["keyword"]
        if keyword.lower() in lowered:
            matched.append(video)
    matched.sort(
        key=lambda item: (
            item.get("numeric_views", 0),
            item.get("numeric_likes", 0),
            item.get("numeric_comments", 0),
        ),
        reverse=True,
    )
    return matched


def load_social_opinions(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    opinions: list[dict[str, Any]] = []
    for row in rows:
        keyword = clean_text(row.get("keyword") or row.get("关键词") or "")
        platform = clean_text(row.get("platform") or row.get("平台") or "")
        opinion = clean_text(row.get("opinion") or row.get("热评") or row.get("comment") or "")
        if not keyword or not platform or not opinion:
            continue
        opinions.append(
            {
                "keyword": keyword,
                "platform": platform,
                "opinion": opinion,
                "likes": clean_text(row.get("likes") or row.get("点赞数") or ""),
                "numeric_likes": parse_number(row.get("likes") or row.get("点赞数") or "0"),
                "stance": clean_text(row.get("stance") or row.get("立场") or ""),
                "url": clean_text(row.get("url") or row.get("链接") or ""),
                "article_title": clean_text(row.get("article_title") or row.get("内容标题") or row.get("文章标题") or ""),
                "article_url": clean_text(row.get("article_url") or row.get("内容链接") or row.get("文章链接") or ""),
                "article_heat_score": clean_text(row.get("article_heat_score") or row.get("文章热度") or row.get("内容热度") or ""),
                "numeric_article_heat_score": parse_number(
                    row.get("article_heat_score") or row.get("文章热度") or row.get("内容热度") or "0"
                ),
                "comment_author": clean_text(row.get("comment_author") or row.get("评论用户") or ""),
                "comment_id": clean_text(row.get("comment_id") or row.get("评论ID") or ""),
                "comment_reply_count": clean_text(row.get("comment_reply_count") or row.get("回复数") or ""),
                "combined_score": clean_text(row.get("combined_score") or row.get("综合分") or ""),
            }
        )
    return opinions


def match_social_opinions(text: str, opinions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matched = []
    lowered = text.lower()
    for opinion in opinions:
        if opinion["keyword"].lower() in lowered:
            matched.append(opinion)
    matched.sort(key=lambda item: item.get("numeric_likes", 0), reverse=True)
    return matched


def build_social_analysis(opinions: list[dict[str, Any]]) -> dict[str, list[str]]:
    if len(opinions) < 5:
        return {
            "consensus": ["高赞评论样本不足，暂不归纳公众共识。"],
            "controversies": ["高赞评论样本不足，暂不归纳主要争议。"],
        }
    stances = " ".join([item.get("stance", "") + " " + item.get("opinion", "") for item in opinions[:8]])
    consensus = [
        "事件影响的不只是公司本身，也会影响用户、商家或行业竞争秩序。",
        "公众更关注大公司动作背后的成本、体验和公平性变化。",
        "多数讨论会把该事件与同业竞争、平台责任或长期商业模式联系起来。",
    ]
    controversies = [
        "争议集中在企业行为究竟是正常商业竞争，还是会带来新的内卷和成本转嫁。",
        "不同群体对事件影响判断不一致：用户、商家、投资者和从业者的关注点存在分歧。",
    ]
    if "支持" in stances and "质疑" in stances:
        controversies[0] = "舆论同时存在支持和质疑：支持者强调效率或创新，质疑者担心成本转嫁、垄断或体验下降。"
    return {"consensus": consensus, "controversies": controversies}


def score_kol_confidence(matched_kols: list[dict[str, Any]]) -> float:
    if not matched_kols:
        return 0.0
    score = min(6.5, len(matched_kols) * 1.5)
    high_followers = sum(1 for item in matched_kols if item.get("numeric_followers", 0) >= 1000000)
    score += min(3.5, high_followers * 1.2)
    return clamp_score(score)


def score_video_confidence(matched_videos: list[dict[str, Any]]) -> float:
    if not matched_videos:
        return 0.0
    score = min(5.0, len(matched_videos) * 1.2)
    hot_count = sum(1 for item in matched_videos if item.get("numeric_views", 0) >= 100000)
    score += min(5.0, hot_count * 1.5)
    return clamp_score(score)


def compute_confidence(
    media_names: list[str],
    matched_kols: list[dict[str, Any]],
    matched_videos: list[dict[str, Any]],
    matched_wechat: list[dict[str, Any]],
    items: list[RawItem],
) -> int:
    media_score = min(35, len(media_names) * 12)
    kol_score = min(25, len(matched_kols) * 5)
    video_score = min(12, len(matched_videos) * 4)
    high_follower_score = min(10, sum(1 for item in matched_kols if item.get("numeric_followers", 0) >= 1000000) * 5)
    wechat_score = min(20, round(sum(item["score"] for item in matched_wechat[:3]) * 2))
    source_weight_score = min(10, round(max(item.source_weight for item in items) * 8))
    return int(min(100, media_score + kol_score + video_score + high_follower_score + wechat_score + source_weight_score))


def format_kol_highlights(matched_kols: list[dict[str, Any]]) -> str:
    if not matched_kols:
        return ""
    highlights = []
    for item in matched_kols[:5]:
        followers = f"（{item['followers']}）" if item.get("followers") else ""
        platform = f"{item['platform']} · " if item.get("platform") else ""
        highlights.append(f"{platform}{item['author']}{followers}: {item['title']}")
    return "；".join(highlights)


def format_video_items(matched_videos: list[dict[str, Any]]) -> list[dict[str, str]]:
    items = []
    seen: set[str] = set()
    for video in matched_videos[:5]:
        key = video.get("url") or f"{video.get('platform')}::{video.get('title')}"
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "platform": video.get("platform", ""),
                "author": video.get("author", ""),
                "title": video.get("title", ""),
                "url": video.get("url", ""),
                "date": video.get("date", ""),
                "views": video.get("views", ""),
                "likes": video.get("likes", ""),
                "comments": video.get("comments", ""),
                "note": video.get("note", ""),
            }
        )
    return items


def format_wechat_index(matched_wechat: list[dict[str, Any]]) -> str:
    if not matched_wechat:
        return ""
    return "；".join(
        f"{item['keyword']}={item['index']}({item.get('trend') or '趋势未填'})"
        for item in matched_wechat[:5]
    )


def synthesize_confidence_reason(
    media_names: list[str],
    matched_kols: list[dict[str, Any]],
    matched_videos: list[dict[str, Any]],
    matched_wechat: list[dict[str, Any]],
    confidence: int,
) -> str:
    parts = [f"{len(media_names)} 个媒体渠道"]
    if matched_kols:
        high_count = sum(1 for item in matched_kols if item.get("numeric_followers", 0) >= 1000000)
        parts.append(f"{len(matched_kols)} 条大 V 内容")
        if high_count:
            parts.append(f"{high_count} 个百万粉以上账号")
    else:
        parts.append("暂无大 V 提及录入")
    if matched_videos:
        parts.append(f"{len(matched_videos)} 条抖音/B站视频源")
    else:
        parts.append("暂无视频源录入")
    if matched_wechat:
        parts.append("微信指数有命中")
    else:
        parts.append("微信指数未录入或未命中")
    return f"置信度 {confidence}/100，依据：" + "，".join(parts) + "。"


def write_hotspots_csv(path: Path, hotspots: list[dict[str, Any]]) -> None:
    fields = [
        "title",
        "source",
        "date",
        "industry",
        "type",
        "summary",
        "core_summary",
        "key_nodes",
        "social_opinions",
        "public_consensus",
        "public_controversies",
        "social_data_complete",
        "why_now",
        "business_angle",
        "topic_value",
        "risk",
        "difficulty",
        "media_channel_count",
        "media_channels",
        "media_items",
        "big_v_count",
        "big_v_highlights",
        "big_v_items",
        "video_source_count",
        "video_items",
        "wechat_index",
        "confidence",
        "confidence_reason",
        "public_interest",
        "businessValue",
        "controversy",
        "longevity",
        "fit",
        "volume",
        "note",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for hotspot in hotspots:
            row = {}
            for field in fields:
                value = hotspot.get(field, "")
                if field in {"big_v_items", "media_items", "key_nodes", "social_opinions", "public_consensus", "public_controversies"} and value:
                    value = json.dumps(value, ensure_ascii=False)
                row[field] = value
            writer.writerow(row)


def write_hotspots_json(path: Path, hotspots: list[dict[str, Any]]) -> None:
    clean_hotspots = []
    for hotspot in hotspots:
        clean_hotspots.append({key: value for key, value in hotspot.items() if not key.startswith("_")})
    path.write_text(json.dumps(clean_hotspots, ensure_ascii=False, indent=2), encoding="utf-8")


def write_frontend_data(path: Path, hotspots: list[dict[str, Any]], raw_items: list[RawItem], report: dict[str, Any]) -> None:
    clean_hotspots = [
        {key: value for key, value in hotspot.items() if not key.startswith("_")}
        for hotspot in hotspots
    ]
    visible_keys = {
        (media.get("url") or media.get("title") or "").strip()
        for hotspot in clean_hotspots
        for media in hotspot.get("media_items", [])
        if (media.get("url") or media.get("title") or "").strip()
    }
    visible_raw_items = [
        raw_item
        for raw_item in raw_items
        if (raw_item.url or raw_item.title).strip() in visible_keys
    ]
    frontend_report = dict(report)
    frontend_report["visible_raw_item_count"] = len(visible_raw_items)
    if isinstance(frontend_report.get("outputs"), dict):
        frontend_report["outputs"] = {
            key: Path(value).name
            for key, value in frontend_report["outputs"].items()
        }
    payload = {
        "meta": {
            "generated_at": report["generated_at"],
            "note": "Generated by scripts/collect_business_hotspots.py. Safe to overwrite.",
        },
        "report": frontend_report,
        "hotspots": clean_hotspots,
        "rawItems": [raw_item.__dict__ for raw_item in visible_raw_items],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "window.XIAOHU_HOTSPOTS_DATA = "
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + ";\n",
        encoding="utf-8",
    )


def stable_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]


if __name__ == "__main__":
    raise SystemExit(main())
