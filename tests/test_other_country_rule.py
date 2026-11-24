import inspect

import bot


def test_prompt_co_quy_tac_nuoc_khac():
    src = inspect.getsource(bot.ai_relevant)
    assert "KHÔNG nhắc Campuchia" in src and "lộ trình xe điện của Lào" in src


def test_quy_tac_quan_su_thai_van_con():
    src = inspect.getsource(bot.ai_relevant)
    assert "quân đội Thái Lan mua sắm vũ khí" in src


def test_prompt_cho_ai_biet_trang_nuoc_ngoai_khong_phai_kh():
    src = inspect.getsource(bot.ai_relevant)
    assert "Trang nguồn nước ngoài" in src and '.endswith(".kh")' in src
