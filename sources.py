# -*- coding: utf-8 -*-
"""
Danh sách CHỦ ĐỀ và NGUỒN BÁO.
Bạn có thể tự thêm / bớt nguồn ở đây (chỉ cần dán link RSS vào danh sách "feeds").

- feeds  : link RSS trực tiếp của các báo chính thống
- gnews  : câu truy vấn Google News (tự động gom tin từ hàng trăm báo).
           Có thể dùng "site:tenmien.vn" để lấy tin từ báo không có RSS.
- filter : (tuỳ chọn) chỉ giữ bài có chứa ít nhất 1 từ trong danh sách này
           (dùng cho chủ đề không có mục RSS riêng, ví dụ "Chiến sự").
"""

VNE = "https://vnexpress.net/rss/"
TT = "https://tuoitre.vn/"
TN = "https://thanhnien.vn/rss/"
DT = "https://dantri.com.vn/rss/"
VNP = "https://www.vietnamplus.vn/rss/"
VNEC = "https://vneconomy.vn/"
TP = "https://tienphong.vn/rss/"
CF = "https://cafef.vn/"

# Mỗi chủ đề lấy tin qua 2 ĐƯỜNG song song:
#   1) RSS trực tiếp của báo  (nhanh nhất)
#   2) Google News             (dự phòng: Google đã thu thập sẵn từ hàng trăm báo, kể cả
#                               báo chặn bot hoặc không có RSS – bot chỉ giữ báo chính thống)
# Nếu RSS của báo nào bị chặn/lỗi, bot tự thêm truy vấn "site:tenbao.vn <hint>" để không sót tin.

TOPICS = {
    "moinhat": {
        "name": "🆕 Tin mới nhất Việt Nam",
        "feeds": [VNE + "tin-moi-nhat.rss", TT + "home.rss", TN + "home.rss",
                  DT + "home.rss", VNP + "home.rss", TP + "home.rss"],
        "gnews": ["site:baochinhphu.vn", "site:nhandan.vn", "site:vov.vn", "site:vietnamnet.vn",
                  "site:vtv.vn", "site:laodong.vn", "site:znews.vn", "site:nld.com.vn"],
        "hint": "",
        "gnews_en": ["Vietnam"],
    },
    "thoisu": {
        "name": "🏛 Thời sự – Chính trị",
        "feeds": [VNE + "thoi-su.rss", TT + "thoi-su.rss", TN + "chinh-tri.rss",
                  TN + "thoi-su.rss", DT + "thoi-su.rss", VNP + "chinhtri-291.rss",
                  TP + "chinh-tri-308.rss", TP + "xa-hoi-2.rss"],
        "gnews": ["site:baochinhphu.vn chính sách", "site:qdnd.vn", "Thủ tướng", "Quốc hội",
                  "Tổng Bí thư"],
        "hint": "thời sự",
        "gnews_en": ["Vietnam government"],
    },
    "thegioi": {
        "name": "🌍 Thế giới",
        "feeds": [VNE + "the-gioi.rss", TT + "the-gioi.rss", TN + "the-gioi.rss",
                  DT + "the-gioi.rss", VNP + "thegioi-209.rss", TP + "the-gioi-5.rss",
                  "https://feeds.bbci.co.uk/vietnamese/rss.xml"],
        "gnews": ["tin thế giới", "site:vov.vn thế giới", "site:vietnamnet.vn thế giới"],
        "hint": "thế giới",
        "gnews_en": ["world news"],
    },
    "chiensu": {
        "name": "⚔️ Chiến sự – Quân sự – Xung đột",
        "feeds": [VNE + "the-gioi.rss", TT + "the-gioi.rss", TN + "the-gioi.rss",
                  DT + "the-gioi.rss", VNP + "thegioi-209.rss",
                  "https://feeds.bbci.co.uk/vietnamese/rss.xml"],
        "filter": ["chiến sự", "chiến tranh", "xung đột", "quân sự", "quân đội",
                   "tên lửa", "không kích", "tấn công", "drone", "UAV", "binh sĩ",
                   "chiến trường", "mặt trận", "Ukraine", "Ukraina", "Nga", "Israel",
                   "Gaza", "Hamas", "Hezbollah", "Iran", "Houthi", "NATO",
                   "Lầu Năm Góc", "Kremlin", "ngừng bắn", "vũ khí", "pháo", "hạt nhân",
                   "Biển Đông", "Đài Loan", "Triều Tiên"],
        "gnews": ["chiến sự", "xung đột quân sự", "chiến sự Ukraine", "Trung Đông xung đột",
                  "site:qdnd.vn quân sự thế giới"],
        "gnews_en": ["war military strike"],
        "hint": "quân sự",
    },
    "ngoaigiao": {
        "name": "🤝 Ngoại giao – Quan hệ quốc tế",
        "feeds": [VNP + "chinhtri-291.rss", TN + "chinh-tri.rss"],
        "filter": ["ngoại giao", "Bộ Ngoại giao", "hội đàm", "thăm chính thức",
                   "thăm cấp nhà nước", "đối tác chiến lược", "ASEAN", "Liên hợp quốc",
                   "LHQ", "APEC", "G20", "G7", "BRICS", "hiệp định", "thượng đỉnh",
                   "đại sứ", "quan hệ song phương", "hợp tác quốc tế"],
        "gnews": ["ngoại giao Việt Nam", "site:baoquocte.vn", "site:mofa.gov.vn",
                  "Bộ trưởng Ngoại giao", "thăm chính thức Việt Nam", "hội đàm"],
        "hint": "ngoại giao",
        "gnews_en": ["Vietnam diplomacy", "Vietnam foreign minister"],
    },
    "kinhte": {
        "name": "💰 Kinh tế – Kinh doanh",
        "feeds": [VNE + "kinh-doanh.rss", TT + "kinh-doanh.rss", TN + "kinh-te.rss",
                  DT + "kinh-doanh.rss", VNP + "kinhte-311.rss", VNEC + "tin-moi.rss",
                  VNEC + "tieu-diem.rss", TP + "kinh-te-3.rss", CF + "vi-mo-dau-tu.rss"],
        "gnews": ["kinh tế Việt Nam", "GDP Việt Nam", "site:baodautu.vn"],
        "hint": "kinh tế",
        "gnews_en": ["Vietnam economy", "global economy"],
    },
    "ktquocte": {
        "name": "🌐 Kinh tế quốc tế – Thương mại",
        "feeds": [VNEC + "kinh-te-the-gioi.rss", CF + "tai-chinh-quoc-te.rss",
                  "https://www.cnbc.com/id/20910258/device/rss/rss.html"],
        "hint": "kinh tế thế giới",
        "gnews": ["kinh tế thế giới", "thuế quan", "xuất khẩu Việt Nam", "FDI Việt Nam"],
        "gnews_en": ["global trade tariffs", "world economy"],
    },
    "taichinh": {
        "name": "📈 Tài chính – Chứng khoán – Vàng",
        "feeds": [VNEC + "tai-chinh.rss", VNEC + "chung-khoan.rss",
                  VNP + "kinhte/taichinh-343.rss", VNP + "kinhte/chungkhoan-344.rss",
                  DT + "gia-vang.rss", CF + "thi-truong-chung-khoan.rss",
                  TP + "tai-chinh-chung-khoan-105.rss"],
        "gnews": ["chứng khoán VN-Index", "giá vàng", "lãi suất ngân hàng", "tỷ giá USD"],
        "hint": "tài chính",
        "gnews_en": ["stock market", "gold price", "Federal Reserve"],
    },
    "batdongsan": {
        "name": "🏠 Bất động sản",
        "feeds": [VNE + "bat-dong-san.rss", DT + "bat-dong-san.rss", VNEC + "dia-oc.rss",
                  VNP + "kinhte/batdongsan-372.rss"],
        "gnews": ["thị trường bất động sản"],
        "hint": "bất động sản",
        "gnews_en": ["Vietnam real estate"],
    },
    "phapluat": {
        "name": "⚖️ Pháp luật",
        "feeds": [VNE + "phap-luat.rss", TT + "phap-luat.rss", DT + "phap-luat.rss",
                  VNP + "xahoi/phapluat-327.rss"],
        "gnews": ["vụ án xét xử"],
        "hint": "pháp luật",
    },
    "congnghe": {
        "name": "💻 Công nghệ – Khoa học",
        "feeds": [VNE + "khoa-hoc-cong-nghe.rss", TT + "nhip-song-so.rss",
                  TN + "cong-nghe.rss", DT + "cong-nghe.rss", VNP + "congnghe-212.rss"],
        "gnews": ["công nghệ AI"],
        "hint": "công nghệ",
        "gnews_en": ["technology AI"],
    },
    "giaoduc": {
        "name": "🎓 Giáo dục",
        "feeds": [VNE + "giao-duc.rss", TT + "giao-duc.rss", TN + "giao-duc.rss",
                  DT + "giao-duc.rss"],
        "gnews": ["Bộ Giáo dục và Đào tạo"],
        "hint": "giáo dục",
    },
    "suckhoe": {
        "name": "🩺 Sức khỏe",
        "feeds": [VNE + "suc-khoe.rss", TT + "suc-khoe.rss", TN + "suc-khoe.rss",
                  DT + "suc-khoe.rss"],
        "gnews": ["Bộ Y tế"],
        "hint": "sức khỏe",
    },
    "thethao": {
        "name": "⚽ Thể thao",
        "feeds": [VNE + "the-thao.rss", TT + "the-thao.rss", TN + "the-thao.rss",
                  DT + "the-thao.rss"],
        "gnews": ["bóng đá Việt Nam"],
        "hint": "thể thao",
        "gnews_en": ["Vietnam football"],
    },
    "giaitri": {
        "name": "🎬 Giải trí – Văn hoá",
        "feeds": [VNE + "giai-tri.rss", TT + "giai-tri.rss", TN + "giai-tri.rss",
                  DT + "giai-tri.rss"],
        "gnews": ["nghệ sĩ showbiz"],
        "hint": "giải trí",
    },
    "campuchia": {
        "name": "🇰🇭 Campuchia: chính trị – quân sự – ngoại giao – kinh tế",
        # Nguồn chuyên về Campuchia: lấy HẾT, để AI lọc đúng 4 mảng (không lọc bằng chữ -> không sót)
        "feeds": ["px:docho", "src:https://www.freshnewsasia.com/", "src:https://freshnews.com.kh/", "src:https://www.akp.gov.kh/",
                  "src:https://www.dap-news.com/", "src:https://www.kampucheathmey.com/",
                  "src:https://thmeythmey.com/", "src:https://kohsantepheapdaily.com.kh/",
                  "src:https://www.postkhmer.com/", "src:https://www.cnc.com.kh/",
                  "src:https://www.khmertimeskh.com/", "src:https://www.phnompenhpost.com/",
                  "src:https://cambodianess.com/", "src:https://cambojanews.com/", "src:https://kiripost.com/",
                  "src:https://www.cc-times.com/", "src:https://jianhuadaily.com/"],
        # Báo chung (VN, quốc tế): chỉ lấy bài có nhắc tới Campuchia
        "filtered_feeds": [VNE + "the-gioi.rss", TT + "the-gioi.rss", TN + "the-gioi.rss", DT + "the-gioi.rss",
                           VNP + "thegioi-209.rss", VNP + "thegioi/asean-356.rss", TP + "the-gioi-5.rss",
                           "https://feeds.bbci.co.uk/vietnamese/rss.xml",
                           "https://www.bangkokpost.com/rss/data/topstories.xml", "https://www.nationthailand.com/rss",
                           "https://www.straitstimes.com/news/asia/rss.xml"],
        "filter": ["Campuchia", "Cam-pu-chia", "Cambodia", "Cambodian", "Khmer", "Phnom Penh", "Hun Manet",
                   "Hun Sen", "Funan Techo", "Ream", "Preah Vihear", "Siem Reap", "กัมพูชา", "เขมร", "ฮุน มาเนต",
                   "ฮุน เซน", "柬埔寨", "柬国", "洪玛奈", "洪森", "金边", "កម្ពុជា"],
        "gnews": ["Campuchia", "Thủ tướng Hun Manet", "Hun Sen", "biên giới Campuchia Thái Lan",
                  "Campuchia quân sự", "kinh tế Campuchia", "kênh Funan Techo", "biên giới Việt Nam Campuchia",
                  "Campuchia vốn vay viện trợ", "Campuchia ngừng bắn Thái Lan", "Campuchia lừa đảo trực tuyến", "Campuchia buôn người", "Mỹ Campuchia trừng phạt", "ADB viện trợ Campuchia",
                  "Campuchia (site:vnexpress.net OR site:tuoitre.vn OR site:thanhnien.vn OR site:vietnamplus.vn OR site:vov.vn OR site:nhandan.vn)",
                  "Campuchia (site:dantri.com.vn OR site:vietnamnet.vn OR site:baoquocte.vn OR site:qdnd.vn OR site:tienphong.vn OR site:laodong.vn)"],
        "gnews_en": ["site:mfaic.gov.kh", "site:thaigov.go.th Cambodia", "site:khmertimeskh.com", "site:phnompenhpost.com", "site:freshnewsasia.com", "site:freshnews.com.kh", "Cambodia site:asean.org", "Cambodia site:nationthailand.com", "Cambodia site:adb.org", "Cambodia politics", "Cambodia military", "Cambodia Thailand border", "Hun Manet",
                     "Hun Sen", "Cambodia economy", "Cambodia foreign minister", "Cambodia China", "Ream naval base",
                     "Thailand Cambodia ceasefire", "ASEAN observers Cambodia Thailand", "Thai army Cambodia",
                     "Cambodia Thailand mediation Malaysia", "ADB Cambodia loan", "World Bank Cambodia financing",
                     "Cambodia Vietnam border", "Cambodia trade customs", "Cambodia scam centers", "Cambodia human trafficking report", "Cambodia Tier 3 trafficking", "Cambodia sanctions Treasury", "US State Department Cambodia", "Cambodia cyber scam crackdown", "Cambodia European Union", "Cambodia UN human rights", "Cambodia FATF", "ADB approves Cambodia", "ADB Cambodia grant", "Cambodia development assistance aid", "Cambodia (site:state.gov OR site:treasury.gov OR site:justice.gov OR site:fincen.gov OR site:usembassy.gov OR site:whitehouse.gov OR site:congress.gov)", "Cambodia (site:un.org OR site:ohchr.org OR site:unodc.org OR site:icj-cij.org OR site:interpol.int OR site:fatf-gafi.org)", "Cambodia (site:adb.org OR site:imf.org OR site:worldbank.org OR site:aiib.org)", "Cambodia (site:eeas.europa.eu OR site:europa.eu OR site:europarl.europa.eu OR site:gov.uk OR site:diplomatie.gouv.fr OR site:auswaertiges-amt.de)", "Cambodia (site:bangkokpost.com OR site:khaosodenglish.com OR site:thaipbsworld.com OR site:thethaiger.com OR site:thaienquirer.com OR site:pattayamail.com)", "Cambodia (site:asia.nikkei.com OR site:thediplomat.com OR site:scmp.com OR site:channelnewsasia.com OR site:straitstimes.com OR site:aljazeera.com)", "Cambodia (site:reuters.com OR site:apnews.com OR site:bbc.com OR site:voanews.com OR site:rfa.org OR site:southeastasiaglobe.com)", "Cambodia (site:cambodianess.com OR site:cambojanews.com OR site:kiripost.com OR site:cambodiadaily.com OR site:vodhotnews.com OR site:voakhmer.com)", "Cambodia (site:fmprc.gov.cn OR site:gov.cn OR site:mofa.go.jp OR site:go.jp OR site:mofa.go.kr OR site:dfat.gov.au OR site:mea.gov.in OR site:kln.gov.my OR site:mfa.gov.sg OR site:mfa.go.th OR site:thaigov.go.th OR site:mofa.gov.vn)"],
        "gnews_th": ["กัมพูชา", "ชายแดนไทยกัมพูชา", "ฮุน มาเนต", "ฮุน เซน", "ทหารกัมพูชา", "หยุดยิง กัมพูชา",
                     "GBC RBC JBC กัมพูชา", "กองทัพภาคที่ 2 กัมพูชา", "ช่องบก ด่านชายแดน", "ทุ่นระเบิด ชายแดน",
                     "กัมพูชา (site:thairath.co.th OR site:matichon.co.th OR site:khaosod.co.th OR site:thaipbs.or.th OR site:dailynews.co.th OR site:bangkokbiznews.com)",
                     "กัมพูชา (site:posttoday.com OR site:prachachat.net OR site:thansettakij.com OR site:tnnthailand.com OR site:mgronline.com OR site:komchadluek.net)"],
        "gnews_zh": ["柬埔寨", "洪玛奈", "洪森", "柬泰边境", "柬埔寨 经济",
                     "柬埔寨 (site:xinhuanet.com OR site:news.cn OR site:globaltimes.cn OR site:zaobao.com.sg OR site:cctv.com)"],
        "ai_desc": "tin CẤP QUỐC GIA về chính trị, quân sự – quốc phòng – an ninh biên giới (Việt Nam–Campuchia và "
                   "Campuchia–Thái Lan, gồm ngừng bắn, GBC/RBC/JBC, ASEAN, nước thứ ba), ngoại giao, kinh tế – "
                   "tài chính – thương mại, vốn vay và viện trợ quốc tế, thuế, hải quan của Campuchia (kể cả quan hệ với Thái Lan, Việt Nam, Trung Quốc, Mỹ…); báo cáo, xếp hạng, trừng phạt, cáo buộc của nước ngoài hoặc tổ chức quốc tế (Mỹ, EU, LHQ, FATF…) nhắm vào Campuchia; khoản viện trợ, vốn vay, tài trợ mới của nước ngoài và tổ chức quốc tế (ADB, Ngân hàng Thế giới, Nhật, Trung Quốc, EU…) cho Campuchia; tội phạm lừa đảo trực tuyến và buôn người ở tầm quốc gia hoặc quốc tế (khu lừa đảo, truy quét, dẫn độ). "
                   "LOẠI: tin xã hội / địa phương (dọn vệ sinh phường xã, lễ hội, triển lãm du học, giáo dục, y tế "
                   "thường ngày), tai nạn giao thông, cháy nổ, trọng án dân sự, thời tiết, thể thao, giải trí",
        "hint": "Campuchia",
    },
    "dongnama": {
        "name": "🌏 Campuchia – Thái Lan – Đông Nam Á",
        "feeds": ["https://www.khmertimeskh.com/feed/",                 # Khmer Times (tiếng Anh)
                  "https://www.phnompenhpost.com/rss",                  # Phnom Penh Post
                  "https://www.bangkokpost.com/rss/data/topstories.xml",
                  "https://www.nationthailand.com/rss",
                  "https://www.straitstimes.com/news/asia/rss.xml",
                  VNP + "thegioi/asean-356.rss"],
        "gnews": ["Campuchia", "Thái Lan", "ASEAN"],
        "gnews_en": ["Cambodia", "Thailand", "Southeast Asia"],
        "hint": "Đông Nam Á",
    },
    "quocte_en": {
        "name": "🗞 Báo quốc tế (tiếng Anh)",
        "feeds": ["https://feeds.bbci.co.uk/news/world/rss.xml",
                  "https://www.aljazeera.com/xml/rss/all.xml",
                  "https://www.theguardian.com/world/rss",
                  "https://rss.dw.com/rdf/rss-en-world",
                  "https://www.france24.com/en/rss",
                  "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
                  "https://www.cnbc.com/id/100727362/device/rss/rss.html",
                  "https://e.vnexpress.net/rss/news.rss"],
        "gnews_en": ["site:reuters.com world", "site:apnews.com world"],
    },
}

# Các tên miền được coi là "báo chính thống" khi lấy tin qua Google News.
# Bài từ trang KHÔNG nằm trong danh sách này sẽ bị bỏ qua (nếu TRUSTED_ONLY=1).
TRUSTED_DOMAINS = [
    # Việt Nam
    "vnexpress.net", "tuoitre.vn", "thanhnien.vn", "dantri.com.vn", "vietnamplus.vn",
    "baochinhphu.vn", "chinhphu.vn", "nhandan.vn", "qdnd.vn", "vov.vn", "vtv.vn",
    "vnanet.vn", "vneconomy.vn", "cafef.vn", "vietnamnet.vn", "laodong.vn",
    "tienphong.vn", "znews.vn", "zingnews.vn", "plo.vn", "sggp.org.vn",
    "hanoimoi.vn", "baoquocte.vn", "mofa.gov.vn", "cand.com.vn", "congan.com.vn",
    "vtc.vn", "nld.com.vn", "kinhtedothi.vn", "thesaigontimes.vn", "vir.com.vn",
    "vietnamnews.vn", "baodautu.vn", "tapchicongsan.org.vn", "dangcongsan.vn",
    "quochoi.vn", "daibieunhandan.vn", "moit.gov.vn", "mof.gov.vn", "sbv.gov.vn",
    "baotintuc.vn", "vietstock.vn", "tinnhanhchungkhoan.vn", "bnews.vn",
    "congthuong.vn", "baophapluat.vn", "nguoiquansat.vn", "vnbusiness.vn",
    "vietnamfinance.vn", "thoibaotaichinhvietnam.vn", "bbc.com", "bbc.co.uk",
    "rfi.fr", "voatiengviet.com", "vov.gov.vn", "antt.vn",
    # Quốc tế
    "reuters.com", "apnews.com", "bloomberg.com", "ft.com", "wsj.com",
    "nytimes.com", "washingtonpost.com", "theguardian.com", "economist.com",
    "cnn.com", "aljazeera.com", "dw.com", "france24.com", "euronews.com",
    "nikkei.com", "asia.nikkei.com", "scmp.com", "cnbc.com", "politico.com",
    "politico.eu", "axios.com", "npr.org", "abcnews.go.com", "cbsnews.com",
    "nbcnews.com", "foreignpolicy.com", "foreignaffairs.com", "kyivindependent.com",
    "timesofisrael.com", "straitstimes.com", "channelnewsasia.com", "japantimes.co.jp",
    "koreaherald.com", "yonhapnews.co.kr", "thediplomat.com", "lemonde.fr",
    "time.com", "newsweek.com", "usnews.com", "ukrinform.net", "tass.com",
    "globaltimes.cn", "xinhuanet.com", "news.cn",
    # Campuchia, Thái Lan, Lào, Đông Nam Á
    "rfa.org", "khmertimeskh.com", "phnompenhpost.com", "freshnewsasia.com", "freshnews.com.kh", "akp.gov.kh", "cambodianess.com",
    "kohsantepheapdaily.com.kh", "postkhmer.com", "camboja.news", "bangkokpost.com", "nationthailand.com",
    "thaipbs.or.th", "thairath.co.th", "matichon.co.th", "khaosodenglish.com", "khaosod.co.th", "mfa.go.th",
    "laotiantimes.com", "kpl.gov.la", "vientianetimes.org.la", "irrawaddy.com", "inquirer.net", "rappler.com",
    "kompas.com", "thejakartapost.com", "antaranews.com", "bernama.com", "thestar.com.my", "malaymail.com",
    "cnc.com.kh", "dap-news.com", "kampucheathmey.com", "thmeythmey.com", "voakhmer.com", "cambojanews.com",
    "kiripost.com", "btv.com.kh", "tvk.gov.kh", "thethaiger.com", "thaienquirer.com", "thaipbsworld.com", "pattayamail.com", "voanews.com", "southeastasiaglobe.com", "vodhotnews.com", "rasmeinews.com", "cc-times.com", "jianhuadaily.com", "sabay.com.kh",
    "dailynews.co.th", "bangkokbiznews.com", "posttoday.com", "prachachat.net", "thansettakij.com",
    "tnnthailand.com", "ch3plus.com", "amarintv.com", "pptvhd36.com", "mgronline.com", "naewna.com",
    "springnews.co.th", "workpointtoday.com", "thestandard.co", "thaipost.net", "nationtv.tv", "komchadluek.net",
    "thepaper.cn", "ifeng.com", "sina.com.cn", "163.com", "sohu.com", "huanqiu.com", "chinanews.com.cn",
    "cctv.com", "guancha.cn", "zaobao.com.sg", "zaobao.com", "voachinese.com", "cna.com.tw", "udn.com",
    "ltn.com.tw", "hk01.com", "rfa.org", "cambodiadaily.com", "aseanbriefing.com",
    # Trung, Nhật, Hàn, Nga, châu Âu
    "people.cn", "chinadaily.com.cn", "cgtn.com", "nhk.or.jp", "asahi.com", "mainichi.jp", "yomiuri.co.jp",
    "kyodonews.net", "yna.co.kr", "chosun.com", "joongang.co.kr", "hani.co.kr", "ria.ru", "rbc.ru", "kommersant.ru",
    "interfax.ru", "lefigaro.fr", "liberation.fr", "spiegel.de", "faz.net", "elpais.com", "bbc.com",
]


# =====================================================================================
# GÓI BÁO THEO NGÔN NGỮ – bật trong ⚙️ Cài đặt → 🗣 Ngôn ngữ báo.
# Chỉ cần ghi TRANG CHỦ: bot tự dò RSS; báo không có RSS thì bot theo dõi trang chủ và
# báo bài mới xuất hiện (tôn trọng robots.txt). Muốn thêm báo: thêm 1 dòng {"name", "url"}.
# =====================================================================================
LANG_SOURCES = {
    "km": [  # 🇰🇭 Báo tiếng Khmer
        {"name": "Fresh News", "url": "https://www.freshnewsasia.com/"},
        {"name": "AKP (Thông tấn xã Campuchia)", "url": "https://www.akp.gov.kh/"},
        {"name": "DAP News", "url": "https://www.dap-news.com/"},
        {"name": "Kampuchea Thmey", "url": "https://www.kampucheathmey.com/"},
        {"name": "Thmey Thmey", "url": "https://thmeythmey.com/"},
        {"name": "Koh Santepheap", "url": "https://kohsantepheapdaily.com.kh/"},
        {"name": "Post Khmer", "url": "https://www.postkhmer.com/"},
        {"name": "Sabay News", "url": "https://news.sabay.com.kh/"},
        {"name": "CNC News", "url": "https://www.cnc.com.kh/"},
    ],
    "zh": [  # 🇨🇳 Báo tiếng Trung (gồm báo Hoa ngữ ở Campuchia)
        {"name": "柬中时报 Cambodia China Times", "url": "https://www.cc-times.com/"},
        {"name": "柬华日报 Jianhua Daily", "url": "https://jianhuadaily.com/"},
        {"name": "新华网 Xinhua", "url": "http://www.news.cn/"},
        {"name": "联合早报 Zaobao", "url": "https://www.zaobao.com.sg/"},
        {"name": "人民网 People's Daily", "url": "http://www.people.com.cn/rss/politics.xml"},
    ],
    "th": [  # 🇹🇭 Báo tiếng Thái
        {"name": "Thai Rath", "url": "https://www.thairath.co.th/"},
        {"name": "Matichon", "url": "https://www.matichon.co.th/"},
        {"name": "Thai PBS", "url": "https://www.thaipbs.or.th/news"},
        {"name": "Khaosod", "url": "https://www.khaosod.co.th/"},
        {"name": "Manager Online (MGR)", "url": "https://mgronline.com/"},
        {"name": "Naewna", "url": "https://www.naewna.com/"},
        {"name": "Krungthep Turakij", "url": "https://www.bangkokbiznews.com/"},
        {"name": "The Standard", "url": "https://thestandard.co/"},
        {"name": "Bangkok Post", "url": "https://www.bangkokpost.com/"},
        {"name": "The Nation", "url": "https://www.nationthailand.com/"},
    ],
    "lo": [  # 🇱🇦 Báo tiếng Lào
        {"name": "KPL (Thông tấn xã Lào)", "url": "https://kpl.gov.la/"},
        {"name": "Pasaxon", "url": "https://www.pasaxon.org.la/"},
    ],
}


# =====================================================================================
# CAMPUCHIA – THỨ TỰ ƯU TIÊN NGUỒN
#   Tầng 1 🏛  Trang CHÍNH THỨC của cơ quan nhà nước (bài đăng = thông cáo chính thức)
#   Tầng 2 📰  Báo chính thống lớn (Fresh News, AKP…)
#   Tầng 3     Các nguồn khác
# =====================================================================================
OFFICIAL_SITES = [   # tầng 1 – bot tự dò RSS, không có thì theo dõi trang chủ
    {"name": "Văn phòng Chính phủ – Press OCM", "url": "https://pressocm.gov.kh/"},
    {"name": "Bộ Ngoại giao & Hợp tác quốc tế (MFAIC)", "url": "https://www.mfaic.gov.kh/"},
    {"name": "Bộ Quốc phòng", "url": "https://www.mod.gov.kh/"},
    {"name": "Bộ Kinh tế & Tài chính (MEF)", "url": "https://mef.gov.kh/"},
    {"name": "Ngân hàng Quốc gia (NBC)", "url": "https://www.nbc.gov.kh/"},
    {"name": "Tổng cục Hải quan (GDCE)", "url": "https://www.customs.gov.kh/"},
    {"name": "Bộ Nội vụ", "url": "https://www.interior.gov.kh/en"},
    {"name": "Bộ Thông tin", "url": "https://www.information.gov.kh/"},
    {"name": "Bộ Thương mại", "url": "https://www.moc.gov.kh/"},
    {"name": "Hội đồng Phát triển Campuchia (CDC)", "url": "https://www.cdc.gov.kh/"},
    {"name": "Quốc hội Campuchia", "url": "https://en.nac.org.kh/"},
    {"name": "Thượng viện Campuchia", "url": "https://www.senate.gov.kh/"},
    {"name": "ODC – tổng hợp thông cáo các bộ (thay cho MEF bị chặn)", "url": "https://opendevelopmentcambodia.net/en/public_announcement_source/government"},
    {"name": "AKP – Thông tấn xã Campuchia", "url": "https://www.akp.gov.kh/"},
    {"name": "Truyền hình quốc gia TVK", "url": "https://www.tvk.gov.kh/"},
    {"name": "Tổng cục Xuất nhập cảnh", "url": "https://immigration.gov.kh/"},
    {"name": "Tổng cục Thuế", "url": "https://www.tax.gov.kh/"},
    {"name": "Ủy ban Bầu cử Quốc gia (NEC)", "url": "https://www.nec.gov.kh/"},
    {"name": "Bộ Công chính", "url": "https://www.mpwt.gov.kh/"},
    {"name": "Bộ Nông nghiệp", "url": "https://www.maff.gov.kh/"},
    {"name": "Bộ Lao động", "url": "https://www.mlvt.gov.kh/"},
    {"name": "Bộ Ngoại giao Thái Lan", "url": "https://www.mfa.go.th/en/page/news"},
    {"name": "Bộ Quốc phòng Thái Lan", "url": "https://www.mod.go.th/"},
    {"name": "Văn phòng Thủ tướng Thái Lan", "url": "https://www.thaigov.go.th/"},
    {"name": "Lục quân Hoàng gia Thái", "url": "https://www.rta.mi.th/"},
    {"name": "Bộ Ngoại giao Việt Nam", "url": "https://www.mofa.gov.vn/"},
    {"name": "Cổng thông tin Chính phủ Việt Nam", "url": "https://chinhphu.vn/"},
    {"name": "Bộ Tư pháp", "url": "https://moj.gov.kh/"},
    {"name": "Hội đồng Hiến pháp", "url": "https://ccc.gov.kh/"},
    {"name": "Cơ quan Chống tham nhũng (ACU)", "url": "https://acu.gov.kh/"},
    {"name": "Ủy ban Quốc gia chống ma túy", "url": "https://nacd.gov.kh/"},
    {"name": "Ủy ban Quản lý thiên tai", "url": "https://ncdm.gov.kh/"},
    {"name": "Bộ Kế hoạch", "url": "https://mop.gov.kh/"},
    {"name": "Bộ Mỏ & Năng lượng", "url": "https://mme.gov.kh/"},
    {"name": "Bộ Bưu chính & Viễn thông", "url": "https://mptc.gov.kh/"},
    {"name": "Ủy ban Chứng khoán (SECC)", "url": "https://secc.gov.kh/"},
    {"name": "Bộ Quản lý đất đai", "url": "https://mlmupc.gov.kh/"},
    {"name": "Bộ Công nghiệp, Khoa học & Đổi mới", "url": "https://misti.gov.kh/"},
    {"name": "Chính phủ Thái Lan (thailand.go.th)", "url": "https://www.thailand.go.th/"},
    {"name": "Cục Quan hệ công chúng Thái Lan (PRD)", "url": "https://thailand.prd.go.th/en"},
    {"name": "Đại sứ quán Mỹ tại Campuchia", "url": "https://kh.usembassy.gov/"},
    {"name": "ASEAN", "url": "https://asean.org/"},
    {"name": "ADB – tin Campuchia", "url": "https://www.adb.org/where-we-work/cambodia"},
    {"name": "Ngân hàng Thế giới – Campuchia", "url": "https://www.worldbank.org/en/country/cambodia"},
]
OFFICIAL_DOMAINS = ["gov.kh", "usembassy.gov", "state.gov", "treasury.gov", "justice.gov", "un.org", "ohchr.org", "unodc.org", "icj-cij.org", "adb.org", "imf.org", "eeas.europa.eu", "fmprc.gov.cn", "mofa.go.jp", "dfat.gov.au", "kln.gov.my", "mea.gov.in", "kh.usembassy.gov", "thailand.go.th", "prd.go.th", "national-assembly.org.kh", "nac.org.kh", "senate.gov.kh", "mfa.go.th", "mod.go.th", "thaigov.go.th", "rta.mi.th", "mofa.gov.vn", "chinhphu.vn", "asean.org", "adb.org", "worldbank.org"]   # mọi trang .gov.kh = chính thức
MAINSTREAM_KH = ["freshnewsasia.com", "freshnews.com.kh", "dap-news.com", "kampucheathmey.com", "thmeythmey.com",
                 "kohsantepheapdaily.com.kh", "postkhmer.com", "cnc.com.kh", "khmertimeskh.com",
                 "phnompenhpost.com", "cambodianess.com", "cambojanews.com", "kiripost.com", "tvk.gov.kh",
                 "cc-times.com", "jianhuadaily.com", "sabay.com.kh", "vodhotnews.com", "voakhmer.com", "rasmeinews.com"]

# Dấu hiệu THÔNG CÁO CHÍNH THỨC trong tiêu đề / nội dung
STATEMENT_WORDS = ["សេចក្តីថ្លែងការណ៍", "សេចក្ដីថ្លែងការណ៍", "សេចក្តីប្រកាសព័ត៌មាន", "សេចក្ដីប្រកាសព័ត៌មាន",
                   "សេចក្តីជូនដំណឹង", "សេចក្ដីជូនដំណឹង", "ព្រឹត្តិបត្រព័ត៌មាន", "សេចក្តីប្រកាស", "សារលិខិត",
                   "ថ្លែងការណ៍រួម", "press release", "statement", "joint statement", "communiqué", "announcement",
                   "thông cáo", "tuyên bố chung", "แถลงการณ์", "ประกาศ", "声明", "公告", "新闻公报"]

# Khi bật "chỉ báo uy tín": chặn mạng xã hội & trang tổng hợp lại tin của báo khác
BLOCK_DOMAINS = ["facebook.com", "fb.com", "fb.watch", "headtopics.com", "today.line.me", "line.me",
                 "msn.com", "yahoo.com", "newsbreak.com", "flipboard.com", "youtube.com", "tiktok.com",
                 "x.com", "twitter.com", "instagram.com", "pinterest.com", "scribd.com", "ground.news",
                 "news.google.com", "inf.news", "baomoi.com", "24h.com.vn", "soha.vn", "kenh14.vn"]

# Kênh Telegram: bot gợi ý tìm theo các tên này (chỉ nên thêm kênh có dấu ✔️ chính thức / đúng tên cơ quan)
TG_PRESET_SEARCHES = ["Hun Manet", "Hun Sen", "Fresh News", "MFAIC", "Ministry of Foreign Affairs Cambodia",
                      "Ministry of National Defence Cambodia", "Press OCM", "AKP Cambodia",
                      "ហ៊ុន ម៉ាណែត", "ក្រសួងការបរទេស", "ក្រសួងការពារជាតិ"]

# BẢNG THUẬT NGỮ / TIẾNG LÓNG cho AI khi tóm tắt & dịch (thêm trong Telegram bằng /thuatngu từ = nghĩa)
GLOSSARY = {
    "ปุ๋ย": "tân binh / lính mới (tiếng lóng quân đội Thái) – KHÔNG phải phân bón",
    "សម្តេចមហាបវរធិបតី": "Samdech Moha Borvor Thipadei – tước hiệu của Thủ tướng Hun Manet",
    "សម្តេចធិបតី": "Samdech Thipadei – Thủ tướng Hun Manet",
    "សម្តេចអគ្គមហាសេនាបតីតេជោ": "Samdech Techo – Hun Sen (Chủ tịch Thượng viện)",
    "សម្តេចតេជោ": "Samdech Techo – Hun Sen",
    "ទ.ព.ខ": "Quân đội Hoàng gia Campuchia (RCAF)",
    "កងទ័ពជើងគោក": "Lục quân",
    "កងទ័ពជើងទឹក": "Hải quân",
    "កងទ័ពអាកាស": "Không quân",
    "ព្រែកជីកហ្វូណនតេជោ": "kênh đào Funan Techo",
    "ทบ.": "Lục quân Thái Lan (RTA)",
    "กองทัพภาคที่ 2": "Quân khu 2 của Thái (phụ trách biên giới Campuchia)",
    "ฉก.": "lực lượng đặc nhiệm",
}


# Nguồn mới thêm 19/11/2026: chưa báo "nguồn lỗi" trước thời điểm này (cho bot tự thử rồi mới lọc bỏ trang hỏng)
PROBATION_UNTIL = 1795280400
PROBATION_URLS = ['https://freshnews.com.kh/', 'https://kh.usembassy.gov/', 'https://moj.gov.kh/', 'https://ccc.gov.kh/', 'https://acu.gov.kh/', 'https://nacd.gov.kh/', 'https://ncdm.gov.kh/', 'https://mop.gov.kh/', 'https://mme.gov.kh/', 'https://mptc.gov.kh/', 'https://secc.gov.kh/', 'https://mlmupc.gov.kh/', 'https://misti.gov.kh/', 'https://www.thailand.go.th/', 'https://thailand.prd.go.th/en']


# Cơ quan / tổ chức NƯỚC NGOÀI: tin của họ nói về Campuchia luôn được gửi (không qua bộ lọc "lạc đề" của AI)
FOREIGN_OFFICIAL_DOMAINS = ['state.gov', 'treasury.gov', 'justice.gov', 'fincen.gov', 'usembassy.gov', 'whitehouse.gov', 'congress.gov', 'un.org', 'ohchr.org', 'unodc.org', 'icj-cij.org', 'interpol.int', 'fatf-gafi.org', 'adb.org', 'imf.org', 'worldbank.org', 'aiib.org', 'eeas.europa.eu', 'europa.eu', 'europarl.europa.eu', 'gov.uk', 'diplomatie.gouv.fr', 'auswaertiges-amt.de', 'fmprc.gov.cn', 'gov.cn', 'mofa.go.jp', 'go.jp', 'mofa.go.kr', 'dfat.gov.au', 'mea.gov.in', 'kln.gov.my', 'mfa.gov.sg', 'mfa.go.th', 'thaigov.go.th', 'mofa.gov.vn']
