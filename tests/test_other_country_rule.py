import inspect

import bot


def test_prompt_co_quy_tac_nuoc_khac():
    src = inspect.getsource(bot.ai_relevant)
    assert "KHÔNG nhắc Campuchia" in src and "lộ trình xe điện của Lào" in src


def test_quy_tac_quan_su_thai_van_con():
    src = inspect.getsource(bot.ai_relevant)
    assert "quân đội Thái Lan mua sắm vũ khí" in src
