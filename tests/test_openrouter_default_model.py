import bot


def test_model_mac_dinh_khong_phai_slug_da_chet():
    assert bot.OPENROUTER_MODEL.endswith(":free") or bot.os.environ.get("OPENROUTER_MODEL")
    assert "llama-3.3-70b-instruct" not in bot.OPENROUTER_MODEL
