# 🔴 3X – Bot Telegram săn tin nóng từ báo chính thống

Bot tự quét **báo Campuchia, Thái Lan, Trung Quốc và quốc tế**, gồm (Reuters, AP, BBC, Al Jazeera, Guardian, DW…) **mỗi 3 phút**, rồi gửi bài mới qua Telegram kèm **tóm tắt 2–3 câu bằng AI** và dấu 🔥 cho tin nóng.

- Chọn chủ đề bằng nút bấm: Tin mới nhất, Thời sự, Thế giới, **Chiến sự**, **Ngoại giao**, Kinh tế, Kinh tế quốc tế, Tài chính – Chứng khoán – Vàng, BĐS, Pháp luật, Công nghệ, Giáo dục, Sức khỏe, Thể thao, Giải trí, Báo quốc tế (tiếng Anh).
- Theo dõi **từ khoá bất kỳ**: bot vừa lọc trong ~70 chuyên mục RSS, vừa tìm trên Google News (chỉ giữ báo chính thống).
- Tin trùng tiêu đề giữa các báo được lọc bớt; nếu một lúc có quá nhiều tin, phần dư được gộp thành một tin nhắn danh sách.

---

## Bước 1 – Tạo bot Telegram (2 phút)

1. Mở Telegram, tìm **@BotFather** → bấm **Start**.
2. Gõ `/newbot` → đặt tên (vd: `Tin Nóng Của Nghĩa`) → đặt username kết thúc bằng `bot` (vd: `nghia_tinnong_bot`).
3. BotFather gửi lại một **token** dạng `123456789:AAH...` → lưu lại.

## Bước 2 – Lấy API key Gemini miễn phí (1 phút)

1. Vào **https://aistudio.google.com/apikey**, đăng nhập Gmail.
2. Bấm **Create API key** → sao chép key (dạng `AIza...`).

> Gói miễn phí đủ dùng vì bot tóm tắt 8 bài trong 1 lần gọi. Không có key thì bot vẫn chạy, chỉ hiện mô tả gốc của bài thay vì tóm tắt AI.

## Chạy 24/7 trên máy chủ riêng (VPS) – khuyên dùng

1. Thuê một **VPS Ubuntu 22.04 hoặc 24.04**, cấu hình 1 CPU / 1 GB RAM là đủ (nên chọn máy chủ đặt tại Việt Nam). Nhà cung cấp sẽ gửi **IP**, tài khoản **root** và **mật khẩu**.
2. **Đóng cửa sổ đen** của bot trên máy tính.
3. Nháy đúp **`DUA_LEN_MAY_CHU.bat`** → nhập IP → nhập mật khẩu máy chủ 2 lần (gõ mật khẩu sẽ không hiện chữ, cứ gõ rồi Enter).
4. Chờ 2–4 phút đến khi hiện **"HOAN TAT"**. Xong – tắt máy tính thoải mái, bot vẫn chạy và tự khởi động lại nếu lỗi.

Cập nhật bản mới: chép file mới vào thư mục rồi chạy lại `DUA_LEN_MAY_CHU.bat` (dữ liệu theo dõi trên máy chủ được giữ nguyên). Lệnh quản lý: xem `deploy/QUAN_LY_MAY_CHU.txt`.

## Bước 3 – Cho bot chạy 24/7

### Cách A (khuyên dùng): GitHub Actions – miễn phí, chạy cả khi tắt máy

1. Tạo tài khoản tại **https://github.com** (nếu chưa có).
2. Bấm **New repository** → đặt tên `newsbot` → chọn **Public** → **Create repository**.
   *(Phải để Public thì mới được chạy không giới hạn phút miễn phí. Token và API key của bạn vẫn được giấu an toàn trong Secrets, người khác không xem được.)*
3. Trong trang repo vừa tạo, bấm **uploading an existing file** → giải nén `NewsBot.zip` rồi **kéo toàn bộ nội dung** (gồm cả thư mục `.github`) vào → **Commit changes**.
4. Vào **Settings → Secrets and variables → Actions → New repository secret**, tạo 2 secret:
   - `TELEGRAM_BOT_TOKEN` = token ở Bước 1
   - `GEMINI_API_KEY` = key ở Bước 2
5. Vào tab **Actions** → bấm nút bật Actions nếu được hỏi → chọn **NewsBot** ở cột trái → **Run workflow**.
6. Mở Telegram, tìm bot của bạn → bấm **Start** → chọn chủ đề. Xong!

Từ giờ GitHub tự khởi động bot mỗi 20 phút, mỗi phiên chạy 55 phút nối tiếp nhau, nên bot gần như luôn trực. Lúc chuyển phiên có thể trễ 1–2 phút; lệnh bạn gõ lúc đó sẽ được xử lý ngay khi phiên mới bắt đầu.

> Lưu ý: với GitHub Actions, trạng thái vận hành được lưu trong repository riêng tư `newsbot-ops`, không lưu trong repository mã nguồn công khai. Cần cấu hình Actions secret `NEWSBOT_STATE_TOKEN` có quyền Contents Read/Write trên repository riêng tư này trước khi bật workflow. Với VPS, file state vẫn được lưu cục bộ trên máy chủ.

### Cách B: Chạy trên máy tính Windows

1. Cài Python tại **https://www.python.org/downloads/** (nhớ tick **Add python.exe to PATH**).
2. Nháy đúp **`run_windows.bat`** → lần đầu nó mở Notepad để bạn dán token và API key vào file `.env` → lưu lại → nháy đúp `run_windows.bat` lần nữa.
3. Muốn bot tự chạy khi mở máy: nhấn `Win + R` → gõ `shell:startup` → tạo **shortcut** của `run_windows.bat` vào thư mục đó.

⚠️ Chỉ chạy **một** nơi (GitHub **hoặc** máy tính). Chạy cả hai cùng lúc Telegram sẽ báo lỗi xung đột.

---

## Cách dùng trong Telegram

Cuối màn hình chat có **7 nút**:

| Nút | Tác dụng |
|---|---|
| 📰 **Tin mới nhất** | 10 tin mới nhất theo những gì bạn theo dõi |
| 🔥 **Tin nóng hôm nay** | 10 tin quan trọng nhất 24 giờ qua (AI chấm điểm) |
| 📋 **Chủ đề** | Bật/tắt chủ đề, có nút "Tắt hết" |
| 🔎 **Từ khoá** | Xem, tìm ngay, **xoá từng cái / chọn nhiều để xoá / xoá hết** |
| ⭐ **Đã lưu** | Các tin bạn bấm ⭐ Lưu |
| 📊 **Xuất Excel** | File Excel tin hôm nay / 24 giờ / 7 ngày / tin đã lưu: giờ đăng, mức độ nóng, tiêu đề (kèm bản dịch), tóm tắt AI, nguồn, trong nước/quốc tế, chủ đề/từ khoá, link bấm được + sheet Thống kê |
| ⚙️ **Cài đặt** | Nguồn (trong nước / nước ngoài / chỉ uy tín), chỉ tin nóng, chuông, giờ yên lặng, bản tin 7h & 21h, tạm dừng |

**Dưới mỗi tin có 3 nút:** ⭐ Lưu · 🧠 Phân tích (AI phân tích sâu: nội dung, bối cảnh, tác động, cần theo dõi) · ➕ Theo dõi vụ này (AI tự tạo từ khoá để theo dõi diễn biến tiếp).

**Thông báo thông minh:**

- 🔔 Chuông: mọi tin / chỉ tin nóng (tin thường vẫn về nhưng không reo) / tắt.
- 🌙 Yên lặng 23h–6h: ban đêm chỉ reo với tin khẩn 🚨.
- ☀️🌙 Bản tin tổng hợp lúc 7h và 21h: 10 tin đáng chú ý nhất.

**Tìm kiếm nhanh & đầy đủ:** RSS báo được quét **mỗi phút**, Google News mỗi 4 phút. Từ khoá gõ có dấu hay không dấu đều được. AI tự thêm cách viết khác (Ukraina/Ukraine…) và bản tiếng Anh để tìm cả báo quốc tế.

**🧠 Gõ cả câu yêu cầu:** thay vì từ khoá, bạn có thể gõ tự nhiên như `tin tức liên quan đến chiến sự ukraina` hay `tình hình xung đột tại biên giới Campuchia Thái Lan`. AI sẽ hiểu ý, tự tạo các cụm tìm kiếm (tiếng Việt + tiếng Anh) và chỉ giữ đúng loại tin bạn muốn. Bấm vào yêu cầu trong 🔎 Từ khoá để xem AI đã hiểu thế nào.

**🗣 Gõ bằng ngôn ngữ khác:** tiếng Anh, Khmer, Thái, Trung, Nhật, Hàn, Nga… đều được. AI dịch yêu cầu sang tiếng Việt và tiếng Anh để tìm báo VN và quốc tế, đồng thời tìm bằng chính ngôn ngữ đó (Google News bản Thái, Trung, Nhật, Hàn, Nga…; riêng tiếng Khmer tìm qua báo Campuchia như RFA Khmer). Tin tiếng nước ngoài được dịch tiêu đề và tóm tắt sang tiếng Việt.

**🇰🇭 Chế độ Campuchia (1 chạm):** 📋 Chủ đề → bấm "🇰🇭 1 chạm: Chế độ Campuchia". Bot theo dõi chính trị – quân sự – ngoại giao – kinh tế Campuchia từ 10+ báo tiếng Khmer (Fresh News, AKP, DAP News, Kampuchea Thmey, Thmey Thmey, Koh Santepheap, Post Khmer, CNC, VOA Khmer, RFA Khmer), báo Campuchia tiếng Anh (Khmer Times, Phnom Penh Post, Cambodianess, CamboJA, Kiripost), báo Hoa ngữ (柬中时报, 柬华日报) và Google News Anh/Thái/Trung/Việt. Thứ tự ưu tiên: **Khmer > Anh > Thái > Trung > Việt** (đổi ở ⚙️ Cài đặt → 🗣 Ngôn ngữ báo → 🔢).

**🏛 Nguồn chính thức (ưu tiên số 1):** trang của Văn phòng Chính phủ (pressocm.gov.kh), Bộ Ngoại giao (mfaic.gov.kh), Bộ Quốc phòng, Bộ Kinh tế & Tài chính, Ngân hàng Quốc gia, Tổng cục Hải quan, Bộ Nội vụ, Bộ Thông tin, Bộ Thương mại, CDC, Quốc hội, Thượng viện, AKP. Bài của các trang này và bài có chữ សេចក្តីថ្លែងការណ៍ / សេចក្តីប្រកាសព័ត៌មាន / statement… được gắn nhãn **📜 THÔNG CÁO CHÍNH THỨC**, xếp đầu và luôn reo chuông.

**📣 Kênh Telegram chính thức** (Thủ tướng Hun Manet, Hun Sen, MFAIC, Bộ Quốc phòng, Fresh News…): cần 1 tài khoản Telegram phụ làm "người đọc":
1. Vào my.telegram.org (đăng nhập tài khoản phụ) → API development tools → tạo app → chép api_id, api_hash.
2. Thêm vào file `.env`: `TG_API_ID=...` và `TG_API_HASH=...`
3. Tắt bot → nháy đúp `DANG_NHAP_TELEGRAM.bat` → nhập số điện thoại tài khoản phụ + mã Telegram gửi về.
4. Chạy lại bot → ⚙️ Cài đặt → 📣 Kênh Telegram → 🔍 Gợi ý kênh chính thức → chọn kênh có dấu ✔️.

**📖 Thuật ngữ:** `/thuatngu ปุ๋ย = tân binh` để AI dịch đúng tiếng lóng. **🗑 Tin bị lọc:** `/daloc`.

**📡 Thêm báo bất kỳ:** gửi link trang chủ báo vào ô chat → bấm "📡 Thêm làm nguồn báo". Bot tự tìm RSS; báo không có RSS thì bot theo dõi trang chủ và báo bài mới xuất hiện. Quản lý ở ⚙️ Cài đặt → 📡 Nguồn báo riêng.

**Lọc 3 lớp trước khi gửi:** trùng tiêu đề → AI loại tin lạc đề → AI loại tin trùng sự kiện (nhiều báo đưa cùng một chuyện chỉ gửi một tin, trừ khi có diễn biến mới).

Lệnh gõ tay: `/tim <từ khoá>` (tìm 7 ngày) · `/nguon` (tình trạng nguồn & AI) · `/del all` (xoá hết từ khoá).

## Cho nhiều người cùng dùng

Người mới chỉ cần mở link bot và bấm **Bắt đầu**. Bạn (quản lý) sẽ nhận tin "Có người muốn dùng bot" kèm nút **✅ Cho phép / ❌ Từ chối**. Mỗi người có chủ đề, từ khoá, cài đặt, tin đã lưu riêng – không trùng, không ảnh hưởng nhau. Xem / xoá người dùng: ⚙️ Cài đặt → 👥 Người dùng (hoặc gõ `/nguoidung`).

## Đổi ảnh đại diện bot

Tên bot **3X – Săn tin nóng** được đặt tự động khi chạy. Ảnh đại diện thì Telegram chỉ cho đặt qua BotFather:

1. Mở **@BotFather** → gõ `/setuserpic` → chọn bot của bạn.
2. Gửi ảnh `assets/3X_avatar.png` (gửi dạng **ảnh**, không gửi dạng file).

**Cú pháp từ khoá**

- Mỗi cụm được tìm **đúng nguyên cụm** (tiếng Việt mỗi chữ là một âm tiết, tách rời sẽ ra sai nghĩa): `nguyễn đức anh`.
- Dấu phẩy = HOẶC: `ukraina, ukraine`.
- Dấu cộng = VÀ, bài phải có đủ các cụm dù nằm cách xa nhau: `chiến sự + ukraina`, `nguyễn đức anh + đồng nai`.
- Ngoài ra bot tìm thêm trên Google News theo nghĩa (để không sót bài viết khác chữ), rồi **AI tự loại các bài chỉ trùng chữ mà khác nghĩa**.
- `/tim` tìm lại trong 7 ngày gần nhất; theo dõi liên tục thì chỉ báo bài mới.

Khi vừa thêm chủ đề/từ khoá, bot gửi ngay 5 tin mới nhất, sau đó chỉ báo bài **mới đăng**.

---

## Khi báo chặn bot – bot xử lý thế nào?

Bot lấy tin qua **2 đường song song** nên một báo chặn không làm sót tin:

1. **RSS trực tiếp** của báo – kênh các báo mở sẵn cho phần mềm đọc tin, nhanh nhất.
2. **Google News** – Google đã thu thập sẵn tin từ hàng trăm báo (kể cả báo chặn bot hoặc không có RSS). Bot chỉ giữ bài của báo chính thống.

Khi một nguồn từ chối (lỗi 403/429, trả về trang xác minh "bạn có phải người không"…), bot tự động:

- **Lùi lại** không truy cập nguồn đó một thời gian (5 phút → 10 → 20 … tối đa 6 giờ) thay vì gõ cửa liên tục, tránh bị chặn nặng hơn.
- **Chuyển sang lấy tin báo đó qua Google News** (truy vấn `site:tenbao.vn`) cho đến khi RSS hoạt động lại.
- Nếu không đọc được toàn văn bài, AI **tóm tắt từ phần mô tả** – tin vẫn được gửi đầy đủ.
- Nguồn lỗi quá 3 giờ → **nhắn cảnh báo cho chủ bot**. Gõ `/nguon` để xem chi tiết bất cứ lúc nào.

Bot cũng "lịch sự" để ít bị chặn: tự giới thiệu là trình đọc RSS, tối đa 2 kết nối cùng lúc tới một báo, chỉ tải lại khi báo có tin mới, và tôn trọng file `robots.txt` khi đọc toàn văn.

> Bot **không** vượt captcha, tường phí hay cơ chế chống bot của báo – việc đó vi phạm điều khoản của báo và dễ gặp rắc rối pháp lý. Thay vào đó, bot có nhiều đường lấy tin hợp lệ nên vẫn đủ tin.
>
> Mẹo: một số báo Việt Nam hạn chế truy cập từ máy chủ nước ngoài. Khi làm cho khách, nên thuê **VPS đặt tại Việt Nam** (khoảng 100–200 nghìn/tháng) để RSS trực tiếp hoạt động tốt nhất.

---

## Tuỳ chỉnh (không bắt buộc)

- **Thêm/bớt báo, thêm chủ đề**: sửa `sources.py` (dán link RSS vào `feeds`, hoặc thêm `site:tenbao.vn` vào `gnews`).
- **Danh sách báo chính thống** cho kết quả Google News: `TRUSTED_DOMAINS` trong `sources.py`.
- **Các thông số khác** (đặt trong `.env` hoặc phần `env:` của file `.github/workflows/newsbot.yml`):
  - `CHECK_INTERVAL` – số giây giữa 2 lần quét (mặc định 180).
  - `MAX_AGE_HOURS` – chỉ gửi bài trong N giờ gần nhất (mặc định 12).
  - `INIT_COUNT` – số tin gửi ngay khi vừa đăng ký (mặc định 5).
  - `MAX_PER_CYCLE` – quá số tin này trong 1 lượt thì gộp phần dư thành danh sách (mặc định 40).
  - `LINK_PREVIEW=1` – hiện ảnh xem trước của bài.
  - `ALLOWED_USERS` – ID Telegram được phép dùng bot (mặc định: người đầu tiên bấm Start là chủ bot; người khác nhắn vào sẽ thấy ID của họ để bạn thêm vào đây nếu muốn chia sẻ).
