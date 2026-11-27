from app.core.config import Settings


def test_settings_loads_deepseek_values_from_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DEEPSEEK_API_KEY=test-secret\n"
        "DEEPSEEK_BASE_URL=https://llm.example/v1\n"
        "DEEPSEEK_MODEL=deepseek-reasoner\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.deepseek_api_key is not None
    assert settings.deepseek_api_key.get_secret_value() == "test-secret"
    assert settings.deepseek_base_url == "https://llm.example/v1"
    assert settings.deepseek_model == "deepseek-reasoner"
    assert "test-secret" not in repr(settings)


def test_demo_rate_limit_settings_have_safe_defaults(tmp_path):
    settings = Settings(_env_file=tmp_path / ".env")

    assert settings.travelmate_rate_limit_enabled is False
    assert settings.travelmate_rate_limit_per_window == 5
    assert settings.travelmate_rate_limit_window_seconds == 600
    assert settings.travelmate_global_chat_limit == 100
    assert settings.travelmate_global_chat_window_seconds == 86400
    assert settings.travelmate_max_concurrent_chats == 2
