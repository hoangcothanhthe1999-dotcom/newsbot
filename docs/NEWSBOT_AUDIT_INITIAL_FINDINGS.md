# Phát hiện sơ bộ – kiểm toán Newsbot 2026-11-28

> Đây là phát hiện tĩnh từ mã `main` tại SHA `4466a097cd3c57fa781aa19d4080ab6262f1d7ea`, trước khi PR #87 được merge. Chưa phải kết luận từ log production.

## 1. CHẮC CHẮN – trạng thái nguồn trang chủ có thể bị báo sai khi robots.txt chặn
- `bot.py:679-682` – `fetch_page()`: nếu `robots_allows(url)` trả false, hàm gọi `mark_fail("src:"+url, ...)` rồi trả `[]`.
- `bot.py:820-843` – `fetch_source()`: sau khi nhận `[]` (không có exception), vẫn gọi `mark_ok(key)` và `stat_src(key, items=items)`.
- Hệ quả: lỗi robots có thể bị xóa ngay trong cùng lượt và nguồn bị ghi nhận như truy cập thành công/trang trống. Điều này làm sai bảng sức khỏe, gây khó ưu tiên sửa nguồn.
- Hướng sửa: trả trạng thái phân biệt (success/empty/blocked/error) hoặc ném exception có kiểu riêng; caller không được mark_ok khi robots bị chặn. Viết test mock robots=false và xác nhận fail không bị reset.

## 2. CHẮC CHẮN – lỗi RSS bên dưới có thể bị che ở cấp nguồn trang chủ
- `fetch_source()` gọi `fetch_feed(res["url"])`; `fetch_feed()` có nhánh bắt lỗi HTTP/parse và trả cache thay vì ném exception.
- Sau đó `fetch_source()` vẫn `mark_ok(key)` cho khóa `src:<homepage>`, dù endpoint RSS bên dưới có thể đang lỗi.
- Hệ quả: trạng thái endpoint logic (homepage) có thể xanh trong khi RSS thực sự hỏng; cần log riêng homepage và RSS endpoint, không gộp hai lớp.

## 3. CHẮC CHẮN – nguồn Telegram không được đưa vào bảng thống kê nguồn theo phiên
- `fetch_channel()` (khoảng dòng 870) cập nhật `mark_ok/mark_fail` nhưng không gọi `stat_src()`.
- `log_session_summary()` chỉ in các nguồn nằm trong `SESSION_STATS["src"]`.
- Hệ quả: báo cáo cuối phiên không thể hiện đầy đủ số bài/lỗi theo kênh Telegram; gây điểm mù khi kiểm toán nguồn.

## 4. CHẮC CHẮN – proxy có thống kê lỗi từng trang nhưng backoff sức khỏe chủ yếu ở cấp proxy chung
- `fetch_proxy()` ghi `stat_src("px:"+src, err=...)` cho từng mục lỗi, nhưng `mark_ok/mark_fail` chỉ áp dụng cho `px:docho`.
- Hệ quả: một trang phía sau proxy lỗi liên tục vẫn có thể bị gọi lại theo nhịp chung, không có backoff riêng; trạng thái tổng thể của proxy không phản ánh endpoint thành phần.
- Cần xác minh schema JSON Apps Script trước khi sửa để tránh thay đổi giao thức đang chạy.

## 5. SUY ĐOÁN – fallback khi AI hết hạn mức có thể làm tăng tin rác từ nguồn tầng 1
- `fallback_ok()` trả true ngay với `item_tier(it) <= 1`.
- Nếu AI không chấm được, tin từ nguồn được phân loại chính thức có thể được giữ dù chưa khớp chủ đề cụ thể.
- Có thể là chủ ý chống bỏ sót thông cáo chính thức; cần đo trên log và tập ca thực tế trước khi thay đổi.

## 6. SUY ĐOÁN – ngoại lệ nguồn nước ngoài chính thức đang rất rộng
- `foreign_official()` trả true chỉ dựa trên domain trong `FOREIGN_OFFICIAL_DOMAINS`; `drop_irrelevant()` bỏ qua AI khi điều kiện này đúng.
- Cơ chế có thể giữ cả bài không liên quan nếu một feed/truy vấn rộng trả nhầm bài từ domain đó. Cần replay các quyết định thực tế trước khi thu hẹp.

## 7. CẦN KIỂM CHỨNG – Apps Script/Worker và danh sách endpoint thực sự đang hoạt động
- Mã repo chỉ cho thấy giao thức gọi proxy; không có mã nguồn/deployment hiện tại của Apps Script và Cloudflare Worker.
- Cần log Executions của Apps Script và kết quả HTTP theo endpoint để phân biệt lỗi website với lỗi parser/proxy.
- Cần chờ run NewsBot #93 hoàn tất để lấy số liệu hiện tại; không dùng run cũ làm baseline mới.

## Ưu tiên sửa đề xuất
1. Sửa độ chính xác health tracking (mục 1–4) trước; đây là nền để mọi báo cáo nguồn không đánh lừa người vận hành.
2. Sau khi có dữ liệu health sạch, phân loại endpoint và khôi phục/thêm nguồn.
3. Cuối cùng mới tinh chỉnh fallback/ngoại lệ lọc theo bằng chứng.
