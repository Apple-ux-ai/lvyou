"""Itinerary / DayPlan 数据模型校验测试（RED 阶段）"""
import pytest
from pydantic import ValidationError

from app.models.schemas import DayPlan, Itinerary, ChatRequest


class TestDayPlan:
    def test_valid_day_plan(self):
        plan = DayPlan(day=1, title="京都一日", activities=["伏见稻荷", "岚山"])
        assert plan.day == 1
        assert plan.activities == ["伏见稻荷", "岚山"]
        # 可选字段默认为 None
        assert plan.transport is None
        assert plan.budget is None

    def test_missing_day_raises(self):
        with pytest.raises(ValidationError):
            DayPlan(title="缺天数", activities=[])

    def test_empty_activities_allowed(self):
        plan = DayPlan(day=2, title="空安排", activities=[])
        assert plan.activities == []


class TestItinerary:
    def test_valid_itinerary(self):
        itin = Itinerary(
            destination="京都",
            days=7,
            total_budget=8500.0,
            day_plans=[
                DayPlan(day=1, title="抵达", activities=["入住酒店"], transport="飞机", budget=1200.0)
            ],
            tips=["提前换汇"],
        )
        assert itin.days == 7
        assert itin.total_budget == 8500.0
        assert len(itin.day_plans) == 1

    def test_null_total_budget_allowed(self):
        """LLM 未给出总预算时必须允许为 None（前端渲染「待估算」）"""
        itin = Itinerary(
            destination="京都",
            days=7,
            total_budget=None,
            day_plans=[],
        )
        assert itin.total_budget is None

    def test_empty_day_plans_allowed(self):
        """空行程列表必须可序列化（前端渲染空态）"""
        itin = Itinerary(destination="冰岛", days=5, total_budget=20000.0, day_plans=[])
        assert itin.day_plans == []

    def test_days_must_be_positive(self):
        with pytest.raises(ValidationError):
            Itinerary(destination="京都", days=0, total_budget=1.0, day_plans=[])


class TestChatRequest:
    def test_valid_request(self):
        req = ChatRequest(message="五一去日本", history=[], session_id="s1")
        assert req.message == "五一去日本"

    def test_missing_message_raises(self):
        with pytest.raises(ValidationError):
            ChatRequest(history=[])

    def test_empty_message_rejected(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="   ", history=[])
