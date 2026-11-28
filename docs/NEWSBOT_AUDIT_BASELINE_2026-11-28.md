# Baseline Newsbot – 2026-11-28

> Snapshot ban đầu để kiểm toán; không thay thế log vận hành mới. Mọi kết luận phải được cập nhật khi có phép đo mới.

## Mốc mã nguồn
- Repository: `hoangcothanhthe1999-dotcom/newsbot`
- Branch vận hành: `main`
- SHA đọc được khi khởi động kiểm toán: `4466a097cd3c57fa781aa19d4080ab6262f1d7ea`
- Nhánh kiểm toán: `audit/comprehensive-review-2026-11-28`
- `bot.py`: khoảng 157 KB; `sources.py`: khoảng 38 KB.
- Workflow `.github/workflows/newsbot.yml`: chỉ có `workflow_dispatch`; lịch gọi định kỳ phụ thuộc bộ điều phối Apps Script bên ngoài.
- Workflow hiện có bước upload artifact `decisions.jsonl` giữ 1 ngày và bước lưu `state.json` với tối đa 7 lần thử push/rebase.

## Hạ tầng nhìn thấy trong mã
- Thu thập kết hợp nguồn trực tiếp, Google News và proxy.
- Cấu hình proxy lấy từ GitHub Secrets `APPS_PROXY_URL` và `APPS_PROXY_KEY`.
- Có các tầng AI dự phòng và cơ chế ghi log quyết định.
- Có công cụ `daily_table.py`, `trace_item.py`, `check_run.py`, `investigate.py`, `replay_dec.py` để phân tích đường đi của tin.
- Không đọc nội dung `state.json` trong baseline này; không ghi nhận bất kỳ dữ liệu cá nhân nào.

## Tình trạng workflow tại thời điểm snapshot
- NewsBot run #93 (workflow_dispatch, SHA main nêu trên) đang chạy ở bước `Chạy bot`; chưa có artifact vì phiên chưa hoàn tất.
- PR #87: CI đã PASS; Gemini review chưa kết luận cuối cùng ở lần kiểm tra đầu, do workflow còn ở bước chờ lần thử lại. PR chưa được merge tại thời điểm snapshot.
- Không sử dụng run #92 làm đại diện cho mã mới vì run đó chạy trên SHA cũ.

## Tài liệu cũ
Các tài liệu dự án được cập nhật 22/11 và gói mã đính kèm có thông tin lịch sử hữu ích nhưng không còn đủ để mô tả hiện trạng. Đặc biệt, lịch workflow, proxy, cách lưu trạng thái, quy tắc lọc và cấu hình nguồn phải được xác minh lại trực tiếp từ mã và log mới nhất.

## Việc cần làm tiếp
1. Lấy log hoàn chỉnh của các run NewsBot gần nhất, nhất là #93 sau khi hoàn tất.
2. Dựng bảng kiểm kê endpoint từ `sources.py` và luồng gọi trong `bot.py`.
3. Đối chiếu nguồn lỗi với log thực tế theo cửa sổ nhiều run, không dùng một lần chạy làm kết luận.
4. Rà Apps Script proxy và Cloudflare Worker: cần kiểm tra cấu hình/deployment và log thực thi riêng; repo không đủ dữ liệu để xác nhận toàn bộ.
5. Dựng bộ ca tin rác/tin sót có nhãn Boss xác nhận; không tự ý đọc tập Holdout riêng.
6. Lập backlog sửa theo mức ảnh hưởng, độ chắc chắn và chi phí.
