from app.rag.chunking import split_document


def test_markdown_chunks_keep_heading_context_and_bounds():
    content = "# 京都攻略\n\n## 交通\n\n" + ("京都巴士和地铁换乘建议。 " * 30)

    chunks = split_document(content, "japan-kansai", ".md", target_chars=120, overlap_chars=20)

    assert len(chunks) > 1
    assert all(len(chunk.text) <= 120 for chunk in chunks)
    assert all("京都攻略 > 交通" in chunk.text for chunk in chunks)
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))


def test_valid_json_is_flattened_with_field_paths():
    content = '{"destination":"曼谷","days":4,"tips":["大皇宫","郑王庙"]}'

    chunks = split_document(content, "bangkok", ".json", target_chars=200, overlap_chars=20)

    assert chunks
    assert any("destination: 曼谷" in chunk.text for chunk in chunks)
    assert any("tips > 1: 大皇宫" in chunk.text for chunk in chunks)


def test_invalid_json_falls_back_to_markdown_parser():
    content = "# 关西行程\n\n- 上午：乘 Haruka 到京都"

    chunks = split_document(content, "kansai-7d", ".json")

    assert chunks
    assert "关西行程" in chunks[0].text
    assert "Haruka" in chunks[0].text
