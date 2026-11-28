# Baseline Newsbot – 2026-11-28

## Mốc mã nguồn
- Repo: `hoangcothanhthe1999-dotcom/newsbot`
- SHA `main` sau khi PR #87 merge: `e461fe3996c2dfbcc09940b2e325a5cae25cd09a`
- Nhánh kiểm toán: `audit/comprehensive-review`
- `bot.py`: khoảng 157 KB; `sources.py`: khoảng 38 KB.
- `.github/workflows/newsbot.yml` chỉ khai báo `workflow_dispatch`; lịch gọi định kỳ dựa vào Apps Script bên ngoài repo.
- Workflow NewsBot có bước upload `decisions.jsonl` artifact 1 ngày và bước lưu `state.json` với tối đa 7 lần thử push/rebase.
- Cấu hình proxy lấy từ Secrets `APPS_PROXY_URL`, `APPS_PROXY_KEY`.
- Không đọc nội dung `state.json`, không ghi bất kỳ ID hay dữ liệu cá nhân nào.

## Các thành phần mã
`sources.py`, `bot.py`, `web_reader.py`, `tg_reader.py`, `check_run.py`, `trace_item.py`, `investigate.py`, `replay_dec.py`, `daily_table.py`, `daily_alert.py`, `watchdog.py`, `eval_golden.py`, `tests/`, `golden/`, workflows GitHub Actions.

## PR đang xử lý lúc khởi động
- PR #87 “Lọc bỏ tin bắt giữ ma túy đơn lẻ khỏi chế độ Campuchia”.
- CI PASS; Gemini review PASS trên SHA `0b26e5212adee2aa0da4ed8d9b35a38448d79d04`.
- Đã merge theo quyền Boss giao; merge SHA `e461fe3996c2dfbcc09940b2e325a5cae25cd09a`.
- Chỉ sửa prompt lọc AI và thêm test offline; không chạy deploy.
- NewsBot run #93 đã được kích hoạt trước khi merge và vẫn đang chạy ở thời điểm snapshot; không phải do kiểm toán kích hoạt.

## Tài liệu cũ
Tài liệu gộp và bối cảnh 22/11 có giá trị lịch sử nhưng không còn mô tả đầy đủ hiện trạng. Lịch workflow, proxy, lưu state, nguồn và bộ lọc phải xác minh trực tiếp từ mã/log mới.

## Việc cần làm
1. Thu log hoàn chỉnh các run NewsBot gần nhất, đặc biệt #93 khi hoàn tất.
2. Dựng inventory tất cả endpoint trong `sources.py` và mapping tới luồng thu thập trong `bot.py`.
3. Đo lỗi qua nhiều run; không dùng một lần lỗi làm kết luận.
4. Kiểm tra Apps Script và Cloudflare Worker riêng; repo không chứa đủ mã/deployment để xác nhận.
5. Xây bộ ca tin rác/tin sót được Boss xác nhận; không sửa Holdout riêng.
6. Xếp backlog theo ảnh hưởng, độ chắc chắn và chi phí.
