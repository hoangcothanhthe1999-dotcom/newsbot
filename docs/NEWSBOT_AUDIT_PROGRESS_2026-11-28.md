# Báo cáo tiến độ kiểm toán NewsBot – 2026-11-28

## 1. Mốc mã nguồn và nghiệm thu offline

- Repository: `hoangcothanhthe1999-dotcom/newsbot`
- Main SHA tại thời điểm cập nhật: `d247f9d5ea536234b793783ed12409aa7a39015c`
- CI: PASS (Ruff, Pyright, Pytest).
- EvalGolden: PASS trên main SHA nói trên, 3 lần replay:
  - Bộ chuẩn 31 tin: bỏ sót 0%, chính xác 100% ở cả 3 lần.
  - Holdout 8 tin: bỏ sót 0%, chính xác 100% ở cả 3 lần.
- Không sửa nhãn hoặc hạ ngưỡng Golden/Holdout.

## 2. Các thay đổi đã merge

| PR | Nội dung |
|---|---|
| #88 | Sửa health tracking khi robots chặn và bổ sung thống kê nguồn Telegram |
| #89 | Lọc nguồn chính thức nước ngoài theo liên quan chủ đề thực tế |
| #90 | Loại vụ bắt giữ/thu giữ ma túy thông thường khỏi luồng tin Campuchia |
| #91 | Tách lỗi RSS endpoint khỏi health trang chủ |
| #92 | Theo dõi health từng nguồn thành phần trả về từ Apps Script proxy |
| #93 | Bổ sung endpoint AKP v2 |
| #94 | Nâng cấp GitHub Actions lên các major tương thích Node.js 24 |
| #95 | Gemini review gate fail-closed, tránh dùng kết quả cũ hoặc PASS giả |
| #97 | Yêu cầu đồng thời dấu hiệu hành động và chất ma túy để tránh loại nhầm tin chính sách/điều trị |
| #98 | Fallback AI theo chủ đề và loại nguồn; không tự giữ mọi tin chỉ vì nguồn chính thức |
| #102 | Dùng ranh giới từ tiếng Anh cho bộ lọc vụ bắt giữ ma túy, tránh nhầm “internet/network” với hành động “net” |

## 3. Baseline production gần nhất – Run #93

Run #93 (ID `46124114140`) chạy ngày 28/11/2026, từ 08:04 đến 09:00 UTC (15:04–16:00 giờ Việt Nam), trên SHA `4466a097cd3c57fa781aa19d4080ab6262f1d7ea`. Đây là phiên chạy trước các PR sửa health tracking và bộ lọc nêu trên; không được coi là kiểm chứng production cho main hiện tại.

Số liệu từ RUNSUM và artifact quyết định:
- 55 nguồn được thống kê; 1.693 bài được thu thập.
- Gemini 16/16 lần thành công; không ghi nhận fallback AI.
- 83 bài bị AI loại lạc đề; 2 sự kiện trùng bị loại; 2 tin được gửi.
- 1.308 bài quá tuổi; 601 lượt loại ở bước keyword; 210 trùng tiêu đề.
- Sổ quyết định không bị cắt; không có cờ bất thường trong RUNSUM.

Tình trạng endpoint ở phiên này:
- 52 nguồn có bài; 1 nguồn AKP cũ trả rỗng; 2 upstream proxy không trả bài.
- `px:Kiripost` và `px:Nation Thailand`: mỗi nguồn lỗi 10/10 lượt, trả 0 bài.
- ODC có 1 timeout và CDC có 2 timeout; cả hai vẫn có bài trong phiên, nên chưa kết luận nguồn hỏng.
- AKP v2 đã được thêm trong PR #93 nhưng chưa có phiên production sau merge để xác nhận endpoint mới.

## 4. Trạng thái bảo mật state

PR #99 `Move NewsBot runtime state into the private ops repository` đang ở Draft.

- Repository riêng tư `newsbot-ops` đã có bản state khớp Git blob SHA với bản hiện ở repository Public; JSON và cấu trúc lõi đã được xác minh.
- PR #99 đã chuyển workflow sang checkout và ghi state ở repository riêng tư, giảm quyền GITHUB_TOKEN của repo Public xuống contents:read, kiểm tra cấu trúc trước/sau khi chạy, và xóa state khỏi cây mã nguồn trong nhánh PR.
- CI của PR #99: PASS.
- Workflow kiểm tra private state: FAIL vì Actions secret `NEWSBOT_STATE_TOKEN` chưa được cung cấp (checkout báo thiếu input token). Không merge PR và không chạy production với cấu hình chưa đủ quyền.
- Cần fine-grained PAT chỉ có quyền Contents Read/Write trên repo `newsbot-ops`, lưu trực tiếp thành Actions secret `NEWSBOT_STATE_TOKEN` trong repo Public. Không đưa token vào chat, issue, PR hoặc mã nguồn.
- Xóa file khỏi cây main không xóa các snapshot trong Git history Public. API cho thấy đường dẫn `state.json` có 91 commit lịch sử. Cần kế hoạch rewrite history/force-push riêng sau khi các PR đang mở được xử lý và đã có backup; chưa thực hiện.

## 5. Việc tiếp theo

1. Hoàn tất cấu hình secret truy cập repo riêng tư; xác minh workflow access check PASS trước khi merge PR #99.
2. Sau migration, kiểm tra state được ghi vào repo riêng tư, dedupe/offset được bảo toàn và không phát sinh gửi lại tin cũ.
3. Lập phương án rewrite lịch sử Git để loại bỏ snapshot state khỏi mọi ref công khai; không force-push khi còn PR/nhánh chưa được bảo toàn.
4. Đợi phiên production theo lịch tiếp theo để đo lại 55 nguồn, đặc biệt Kiripost, Nation Thailand, ODC, CDC và AKP v2.
5. Dựa trên artifact mới để tiếp tục phân loại false positive/false negative; không kết luận endpoint chết từ một timeout.
6. Tiếp tục kiểm toán Apps Script dispatcher/proxy và Cloudflare Worker khi có mã nguồn hoặc quyền truy cập triển khai tương ứng.

## 6. Giới hạn xác minh

- Apps Script dispatcher, Apps Script proxy và Cloudflare Worker không có đầy đủ mã nguồn/deployment trong repository này; chưa thể tuyên bố đã kiểm toán hoặc sửa các thành phần đó.
- Chưa có production run sau các PR #88–#102; kết quả CI/EvalGolden là kiểm thử offline, không thay thế kiểm tra nguồn và gửi Telegram thực tế.
- Không kích hoạt workflow production trong phiên kiểm toán này.
