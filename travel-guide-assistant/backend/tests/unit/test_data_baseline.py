"""真实知识语料与黄金问答的最小基线契约。"""

import json
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_ROOT = BACKEND_ROOT / "data" / "knowledge"
GOLDEN_QA_PATH = BACKEND_ROOT / "tests" / "golden_qa.json"


def test_knowledge_and_golden_qa_meet_phase_1_5_baseline() -> None:
    knowledge_files = [*KNOWLEDGE_ROOT.rglob("*.md"), *KNOWLEDGE_ROOT.rglob("*.json")]
    source_ids = {path.stem for path in knowledge_files}

    with GOLDEN_QA_PATH.open(encoding="utf-8") as file:
        golden_qa = json.load(file)
    pairs = golden_qa["pairs"]

    assert len(knowledge_files) >= 10
    assert 20 <= len(pairs) <= 30

    pair_ids = [pair.get("id") for pair in pairs]
    assert all(isinstance(pair_id, str) and pair_id.strip() for pair_id in pair_ids)
    assert len(pair_ids) == len(set(pair_ids))

    for pair in pairs:
        assert isinstance(pair.get("question"), str) and pair["question"].strip()
        assert isinstance(pair.get("expected_sources"), list) and pair["expected_sources"]
        assert all(
            isinstance(source_id, str) and source_id in source_ids
            for source_id in pair["expected_sources"]
        )
        assert isinstance(pair.get("expected_answer_contains"), list) and pair["expected_answer_contains"]
        assert all(
            isinstance(keyword, str) and keyword.strip()
            for keyword in pair["expected_answer_contains"]
        )
