# 외부(같은 네트워크의 폰 등) 접속 허용 실행 스크립트
# 사용: PowerShell에서  ./run.ps1
$env:PYTHONIOENCODING = "utf-8"
$ip = (Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -ne '127.0.0.1' -and $_.PrefixOrigin -eq 'Dhcp' } |
    Sort-Object InterfaceMetric | Select-Object -First 1).IPAddress
Write-Host ""
Write-Host "  로컬:   http://127.0.0.1:8000" -ForegroundColor Cyan
if ($ip) { Write-Host "  외부:   http://$ip:8000  (같은 네트워크의 폰에서 접속)" -ForegroundColor Green }
Write-Host "  (중지: Ctrl+C)"
Write-Host ""
& ".\.venv\Scripts\python.exe" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
