# Chẩn đoán nguồn lỗi (22/11/2026, đọc từ state.json lúc 16:15 giờ VN)

120 nguồn theo dõi, 27 có lỗi, 16 chết liên tục (10–12 lần chạy, 0 bài).
Bot đã tự thêm truy vấn Google News `site:` cho nguồn không khỏe (bot.py ~dòng 987), nên báo lớn vẫn có tin; các trang bộ ngành thì phủ yếu.

| Nhóm | Nguồn | Hướng xử lý (làm SAU lần kiểm tra 06:40 ngày 23/11) |
|---|---|---|
| 403 chặn IP Actions | freshnewsasia, khmertimeskh (trang + RSS), mef.gov.kh, interior.gov.kh, thaigov.go.th, adb.org/countries/cambodia | Đưa vào danh sách "đọc hộ" của Apps Script (Mã.gs, ngoài repo) |
| Không kết nối | mpwt.gov.kh, rta.mi.th, ncdm.gov.kh, secc.gov.kh, national-assembly.org.kh | Thử qua Apps Script; nếu vẫn lỗi thì bỏ khỏi danh sách |
| Trang dùng JavaScript | kiripost, asean.org, immigration.gov.kh, misti.gov.kh, thailand.go.th | Tìm RSS/API; nếu không có thì để Google News phủ |
| RSS hỏng | nationthailand.com/rss | Đã có `site:nationthailand.com` trong gnews_en |
| Lỗi nhẹ | phnompenhpost RSS, dap-news, kohsantepheap, cambojanews (415), cdc.gov.kh | Theo dõi, chưa sửa |

Không sửa production trước khi xác minh lần chạy sáng 23/11 (tránh chồng nguyên nhân).
