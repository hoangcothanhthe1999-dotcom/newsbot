# Đưa bot 3X lên máy chủ (VPS Ubuntu). Chạy bằng file DUA_LEN_MAY_CHU.bat
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
Write-Host "=== DUA BOT 3X LEN MAY CHU (VPS) ===" -ForegroundColor Cyan

if (-not (Get-Command ssh -ErrorAction SilentlyContinue) -or -not (Get-Command scp -ErrorAction SilentlyContinue)) {
  Write-Host "Windows chua co OpenSSH. Vao Settings > Apps > Optional features > Add 'OpenSSH Client' roi chay lai." -ForegroundColor Red
  Read-Host "Nhan Enter de thoat"; exit 1
}
# Bot đang chạy trên máy tính? (2 nơi cùng chạy sẽ xung đột, tin bị gửi trùng)
try { $l = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 47391); $l.Start(); $l.Stop() }
catch {
  Write-Host "Bot dang chay tren may tinh nay. Hay DONG cua so den cua bot truoc, roi chay lai file nay." -ForegroundColor Yellow
  Read-Host "Nhan Enter de thoat"; exit 1
}
if (-not (Test-Path ".env")) { Write-Host "Khong thay file .env (token). Chay run_windows.bat mot lan truoc." -ForegroundColor Red; Read-Host; exit 1 }

$ip = Read-Host "Nhap dia chi IP may chu (vd 103.12.34.56)"
$user = Read-Host "Ten dang nhap (Enter = root)"
if (-not $user) { $user = "root" }
$port = Read-Host "Cong SSH (Enter = 22)"
if (-not $port) { $port = "22" }

$tmp = Join-Path $env:TEMP "3x_upload"
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
New-Item -ItemType Directory -Path $tmp | Out-Null
foreach ($f in @("bot.py","sources.py","tg_reader.py","requirements.txt","README.md",".env","state.json","3x_reader.session")) {
  if (Test-Path $f) { Copy-Item $f $tmp }
}
Copy-Item "assets" $tmp -Recurse -ErrorAction SilentlyContinue
Copy-Item "deploy" $tmp -Recurse
$pkg = Join-Path $env:TEMP "3x_upload.tgz"
if (Test-Path $pkg) { Remove-Item $pkg -Force }
& tar -czf $pkg -C $tmp .
if ($LASTEXITCODE -ne 0) { Write-Host "Khong dong goi duoc file." -ForegroundColor Red; Read-Host; exit 1 }
Push-Location $env:TEMP

$opts = @("-o", "StrictHostKeyChecking=accept-new", "-P", $port)
Write-Host "`n[1/2] Dang tai bot len may chu... (nhap MAT KHAU may chu khi duoc hoi - go se khong hien chu, cu go roi Enter)" -ForegroundColor Cyan
& scp @opts "3x_upload.tgz" "${user}@${ip}:/tmp/3x_upload.tgz"
Pop-Location
if ($LASTEXITCODE -ne 0) { Write-Host "Tai len that bai. Kiem tra IP / mat khau." -ForegroundColor Red; Read-Host; exit 1 }

Write-Host "`n[2/2] Dang cai dat tren may chu (2-4 phut)... (nhap MAT KHAU lan nua)" -ForegroundColor Cyan
$cmd = "rm -rf /tmp/3x_upload && mkdir -p /tmp/3x_upload && tar -xzf /tmp/3x_upload.tgz -C /tmp/3x_upload && bash /tmp/3x_upload/deploy/install_server.sh"
& ssh -o StrictHostKeyChecking=accept-new -p $port "${user}@${ip}" $cmd
if ($LASTEXITCODE -eq 0) {
  Set-Content -Path "deploy\may_chu.txt" -Value "$user@$ip port $port" -Encoding UTF8
  Write-Host "`nHOAN TAT! Bot 3X da chay 24/7 tren may chu. Ban co the tat may tinh." -ForegroundColor Green
  Write-Host "KHONG chay run_windows.bat nua (se bi trung voi may chu)." -ForegroundColor Yellow
} else {
  Write-Host "`nCai dat gap loi - chup man hinh gui lai de duoc ho tro." -ForegroundColor Red
}
Read-Host "Nhan Enter de dong"
