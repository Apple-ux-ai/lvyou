"""LLM 输出解析降级链测试（RED 阶段，对应缺陷 H1）"""
from app.rag.llm_output import parse_llm_output


class TestParseLlLMOutput:
    def test_valid_json_returns_itinerary(self):
        raw = '{"destination":"京都","days":7,"total_budget":8500.0,"day_plans":[{"day":1,"title":"抵达","activities":["入住"],"transport":"飞机","budget":1200.0}],"tips":["提前换汇"]}'
        result = parse_llm_output(raw)
        assert result.type == "itinerary"
        assert result.itinerary is not None
        assert result.itinerary.destination == "京都"

    def test_malformed_json_falls_back_to_text(self):
        """坏 JSON 必须降级为纯文本，而不是抛异常"""
        raw = '{"day_plans": [bad json'
        result = parse_llm_output(raw)
        assert result.type == "text"
        assert result.error_code == "invalid_json"

    def test_empty_string_falls_back_to_text(self):
        result = parse_llm_output("")
        assert result.type == "text"
        assert result.error_code == "invalid_json"

    def test_schema_mismatch_falls_back_to_text(self):
        """合法 JSON 但缺必填字段 → 同样降级而非崩溃"""
        raw = '{"destination":"京都"}'  # 缺 days / total_budget / day_plans
        result = parse_llm_output(raw)
        assert result.type == "text"
        assert result.error_code == "invalid_json"

    def test_partial_itinerary_allows_null_budget(self):
        """total_budget 为 null 的 JSON 应被接受（前端渲染「待估算」）"""
        raw = '{"destination":"京都","days":7,"total_budget":null,"day_plans":[],"tips":null}'
        result = parse_llm_output(raw)
        assert result.type == "itinerary"
        assert result.itinerary.total_budget is None
