// ===== LỚP XÁC THỰC cho web app "đọc hộ" (thêm vào CUỐI Mã.gs) =====
// CÁCH ÁP DỤNG (chỉ khi Boss duyệt): trong Mã.gs hiện có, đổi DUY NHẤT tên hàm
//     function doGet(){      →      function fetchAll_(){
// (không sửa gì khác trong thân hàm), rồi dán toàn bộ đoạn dưới đây vào cuối tệp.
// Khóa đặt trong Project Settings → Script properties: PROXY_KEY = <chuỗi ngẫu nhiên>. KHÔNG ghi khóa trong mã.
var CACHE_TTL_ = 120;          // giây
var CACHE_KEY_ = 'px_v1';
var MIN_GOOD_  = 3;            // chỉ cache khi có ít nhất ngần này mục hợp lệ (không cache kết quả lỗi/rỗng)

function authOk_(k) {
  var want = PropertiesService.getScriptProperties().getProperty('PROXY_KEY');
  if (!want || want.length < 24 || k === undefined || k === null) return false;   // chưa cấu hình khóa mạnh → từ chối tất cả
  k = String(k);
  if (k.length !== want.length) return false;
  var d = 0;
  for (var i = 0; i < k.length; i++) d |= k.charCodeAt(i) ^ want.charCodeAt(i);    // so sánh không dừng sớm
  return d === 0;
}

function out_(txt) {
  return ContentService.createTextOutput(txt).setMimeType(ContentService.MimeType.JSON);
}

function handle_(k) {
  if (!authOk_(k)) return out_(JSON.stringify({error: 'unauthorized'}));   // TRƯỚC mọi đọc cache / UrlFetch
  var cache = CacheService.getScriptCache();
  var hit = cache.get(CACHE_KEY_);
  if (hit) {
    try {
      var raw = Utilities.ungzip(Utilities.newBlob(Utilities.base64Decode(hit), 'application/x-gzip')).getDataAsString();
      return out_(raw);
    } catch (e) { /* cache hỏng → đọc lại */ }
  }
  var txt = fetchAll_().getContent();
  try {
    var arr = JSON.parse(txt);
    var good = 0;
    for (var i = 0; i < arr.length; i++) if (arr[i] && arr[i].link && !arr[i].error) good++;
    if (good >= MIN_GOOD_) {
      var enc = Utilities.base64Encode(Utilities.gzip(Utilities.newBlob(txt, 'application/json')).getBytes());
      if (enc.length < 95000) cache.put(CACHE_KEY_, enc, CACHE_TTL_);        // giới hạn ~100KB mỗi giá trị
    }
  } catch (e) { /* không cache */ }
  return out_(txt);
}

function doGet(e)  { return handle_(e && e.parameter ? e.parameter.k : null); }   // GET ?k=… (dự phòng/so sánh)
function doPost(e) { return handle_(e && e.parameter ? e.parameter.k : null); }   // POST, khóa trong thân gói tin (ưu tiên)
