from check_run import join_log_files


def test_zip_log_khong_dem_doi():
    files = {"0_run.txt": b"LEDGER|a|x|send|sent|sent|T\n", "run/1_step.txt": b"LEDGER|a|x|send|sent|sent|T\n"}
    assert join_log_files(files).count("LEDGER|a") == 1


def test_chi_co_tep_con_van_doc():
    assert "X" in join_log_files({"run/1.txt": b"X"})
