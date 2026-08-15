"""Travel intent detection regression tests."""

from app.rag.pipeline import detect_destination, is_plan_intent


def test_detect_destination_extracts_destination_from_travel_phrase():
    assert detect_destination("我想去贵州玩") == "贵州"


def test_destination_only_request_is_plan_intent():
    assert is_plan_intent("我想去贵州玩") is True


def test_informational_question_is_not_plan_intent():
    assert is_plan_intent("贵州五一期间天气怎么样？") is False


def test_country_name_is_not_mapped_to_an_arbitrary_city():
    assert detect_destination("去日本玩7天") == "日本"


def test_visa_duration_question_is_not_plan_intent():
    assert is_plan_intent("日本签证审核要几天？") is False
