"""RAG 编排主流程

意图识别：
- 行程意图：消息含「玩X天」「去X」「X天」「预算」等关键词 → 返回 itinerary 事件
- 普通问答：仅返回文本 + citations
citations 来自 Chroma 向量检索（知识库分库），生产环境替换 LLM 生成。
"""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from app.core.config import BACKEND_ROOT, load_settings
from app.models.schemas import Itinerary, DayPlan, Citation
from app.rag.chroma_store import ChromaRetriever
from app.rag.index_versions import resolve_index_path


@dataclass
class PlanIntent:
    destination: str
    days: int


# Explicit aliases only. Do not map a country to an arbitrary city.
DESTINATIONS = {
    "日本": "日本",
    "关西": "关西",
    "京都": "京都",
    "东京": "东京",
    "冰岛": "冰岛",
    "大理": "大理",
    "云南": "大理",
    "巴厘岛": "巴厘岛",
    "东南亚": "东南亚",
    "曼谷": "曼谷",
    "泰国": "泰国",
    "大阪": "大阪",
    "奈良": "奈良",
    "神户": "神户",
}

# Information questions should stay in general RAG mode unless they also
# contain an explicit planning phrase.
INFORMATION_HINTS = ["签证", "天气", "气温", "季节", "月份", "材料", "办理", "审核", "交通怎么", "怎么走"]
PLAN_HINTS = ["行程", "规划", "推荐线路", "路线", "安排", "玩", "旅游", "旅行", "自驾", "预算"]
MAX_TRIP_DAYS = 30
TRAVEL_DESTINATION_PATTERN = re.compile(
    r"(?:想|准备|打算)?去(?P<destination>[\u4e00-\u9fff]{2,8})(?:玩|旅游|旅行|逛)"
)
DESTINATION_STOPWORDS = {"哪里", "什么地方", "一个地方"}


def detect_destination(message: str) -> Optional[str]:
    for name in sorted(DESTINATIONS, key=len, reverse=True):
        mapped = DESTINATIONS[name]
        if name in message:
            return mapped
    match = TRAVEL_DESTINATION_PATTERN.search(message)
    if match:
        destination = match.group("destination")
        if destination not in DESTINATION_STOPWORDS:
            return destination
    return None


def detect_days(message: str) -> Optional[int]:
    m = re.search(r"(\d{1,2})\s*天", message)
    if m:
        return min(int(m.group(1)), MAX_TRIP_DAYS)
    return None


def is_plan_intent(message: str) -> bool:
    if detect_destination(message) is None:
        return False
    has_plan_phrase = bool(
        re.search(r"(?:行程|规划|推荐线路|路线|安排|玩|逛|自驾|预算)", message)
        or detect_days(message) is not None
    )
    has_explicit_plan = bool(
        has_plan_phrase
        or (not any(hint in message for hint in INFORMATION_HINTS) and "旅行" in message)
    )
    if not has_explicit_plan:
        return False
    if any(hint in message for hint in INFORMATION_HINTS):
        return bool(
            re.search(
                r"(?:去|玩|旅游|旅行|行程|规划|路线|安排).*(?:玩|旅游|旅行|行程|规划|路线|安排|天)",
                message,
            )
        )
    return True


def build_mock_itinerary(destination: str, days: int) -> Itinerary:
    """构造 mock 行程（生产版由 LLM 生成 + Pydantic 校验）"""
    days = min(max(int(days), 1), MAX_TRIP_DAYS)
    day_plans = []
    for d in range(1, days + 1):
        if d == 1:
            title = f"抵达{destination}，市区漫步"
            activities = ["入住酒店", f"{destination}老城区闲逛", "当地特色晚餐"]
        elif d == days:
            title = f"返程日 · 上午购物补货"
            activities = ["伴手礼采购", "前往机场"]
        else:
            title = f"第{d}天 · 深度探索"
            activities = [f"{destination}核心景点", "午餐体验当地美食", "傍晚自由活动"]
        day_plans.append(
            DayPlan(
                day=d,
                title=title,
                activities=activities,
                transport="市内公共交通" if d > 1 else "飞机/高铁",
                budget=round(8500.0 / days, 1),
            )
        )
    return Itinerary(
        destination=destination,
        days=days,
        total_budget=round(8500.0, 1),
        day_plans=day_plans,
        tips=["提前办理签证", "购买旅行保险", "当地货币提前兑换"],
    )


_retriever_cache: Optional[ChromaRetriever] = None


def _get_retriever() -> ChromaRetriever:
    """惰性初始化 retriever using the shared retrieval settings."""
    global _retriever_cache
    if _retriever_cache is None:
        settings = load_settings()
        configured_root = Path(settings.travelmate_index_root) if settings.travelmate_index_root else None
        if configured_root is not None and not configured_root.is_absolute():
            configured_root = BACKEND_ROOT / configured_root
        _retriever_cache = ChromaRetriever(
            persist_dir=str(
                resolve_index_path(
                    configured_root,
                    settings.travelmate_index_version or None,
                    BACKEND_ROOT / "chroma_data",
                )
            ),
            collection="knowledge",
            min_score=settings.travelmate_retrieval_min_score,
        )
    return _retriever_cache


def mock_citations(message: str) -> List[Citation]:
    """基于 Chroma 向量检索返回 citations（空库/低相关 → 空列表）"""
    try:
        docs = _get_retriever().search(message, top_k=3)
    except Exception:
        return []

    citations = []
    for doc in docs:
        # 标题取首行（去 # 号），兜底用 source_id
        first_line = doc.text.splitlines()[0] if doc.text else ""
        title = first_line.lstrip("# ").strip() or doc.source_id
        citations.append(Citation(source_id=doc.source_id, title=title[:40]))
    return citations
