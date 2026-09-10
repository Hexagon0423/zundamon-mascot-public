from mascot.config import Config, VoiceParams, WindowPosition, load_config, save_config


def test_load_config_missing_file_returns_defaults(tmp_path):
    config = load_config(tmp_path / "missing.json")
    assert config.port == 50022
    assert config.voice == VoiceParams()
    assert config.window_position is None
    assert config.scale == 1.0


def test_load_config_corrupt_file_falls_back_to_defaults(tmp_path):
    """A broken config must not stop startup -- under autostart there's no
    console, so the failure would be invisible."""
    path = tmp_path / "config.json"
    path.write_text("{ this is not json", encoding="utf-8")
    assert load_config(path) == Config()


def test_load_config_unexpected_field_falls_back_to_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"voice": {"nonexistent_field": 1}}', encoding="utf-8")
    assert load_config(path) == Config()


def test_save_then_load_round_trips(tmp_path):
    path = tmp_path / "config.json"
    original = Config(
        port=50099,
        voice=VoiceParams(speaker=3, speed_scale=1.2),
        window_position=WindowPosition(screen_name="\\\\.\\DISPLAY1", x_fraction=0.9, y_fraction=0.8),
        click_through=True,
        scale=1.5,
    )
    save_config(original, path)
    loaded = load_config(path)
    assert loaded == original
