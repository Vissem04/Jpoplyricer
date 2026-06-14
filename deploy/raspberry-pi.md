# 라즈베리파이로 배포하기

라즈베리파이는 **가정용 IP**라 YouTube 다운로드가 막히지 않고, SD카드에 데이터가
영속 저장되어 이 앱에 가장 알맞은 자가호스팅 환경입니다.

## 권장 사양
- 라즈베리파이 **4 / 5 (RAM 2GB 이상)** 권장, 64비트 Raspberry Pi OS
- (Pi 3/Zero도 가능하나 느릴 수 있음. torch는 설치하지 않으므로 메모리는 가벼움)

## 1. 기본 패키지 설치
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ffmpeg git
```

## 2. 코드 받기
```bash
cd ~
git clone https://github.com/Vissem04/Jpoplyricer.git
cd Jpoplyricer
```

## 3. 파이썬 환경 + 의존성
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
# (torch/stable-ts는 ARM에서 무겁고 불필요 — 설치 안 함.
#  싱크는 LRCLIB 동기가사 + 근사 정렬로 동작)
```

## 4. 키 설정 (.env)
```bash
cp .env.example .env
nano .env   # 아래 값 채우기
```
```
OPENAI_API_KEY=sk-...
GENIUS_ACCESS_TOKEN=...
ADMIN_USERNAME=빛샘
ADMIN_PASSWORD=강한-비밀번호
# 로컬 http로 접속하면 0, Cloudflare Tunnel(https)로 접속하면 1
COOKIE_SECURE=0
```

## 5. 실행 (테스트)
```bash
source .venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```
같은 와이파이의 다른 기기에서 `http://<파이IP>:8000` 접속 확인.
(파이 IP 확인: `hostname -I`)

## 6. 자동 시작 (systemd) — 부팅 시 항상 켜지게
```bash
sudo cp deploy/jpoplyricer.service /etc/systemd/system/
sudo nano /etc/systemd/system/jpoplyricer.service   # User/경로가 본인 것과 맞는지 확인
sudo systemctl daemon-reload
sudo systemctl enable --now jpoplyricer
sudo systemctl status jpoplyricer        # 동작 확인
journalctl -u jpoplyricer -f             # 로그 보기
```

## 7. 외부(휴대폰 LTE 등)에서 접속 — Cloudflare Tunnel (무료, 권장)
포트포워딩 없이 안전한 HTTPS 주소를 발급받는 방법:
```bash
# cloudflared 설치 (ARM64)
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 -o cloudflared
chmod +x cloudflared && sudo mv cloudflared /usr/local/bin/

# 빠른 임시 터널(테스트용): 실행하면 https://xxxx.trycloudflare.com 주소가 출력됨
cloudflared tunnel --url http://localhost:8000
```
- 이 주소로 **어디서든** 접속됩니다. (HTTPS이므로 `.env`에서 `COOKIE_SECURE=1` 권장)
- 고정 주소/자동 실행이 필요하면 Cloudflare 계정으로 "named tunnel" 구성(문서 참고).

## 업데이트(코드 변경 반영)
```bash
cd ~/Jpoplyricer
git pull
source .venv/bin/activate && pip install -r requirements.txt
sudo systemctl restart jpoplyricer
```

## 참고
- Whisper(받아쓰기)·GPT(독음/해석)는 **OpenAI API 호출**이라 파이 CPU 부담이 적습니다.
- 데이터는 `data/` (SD카드)에 저장되어 재부팅해도 유지됩니다.
- 파이는 켜져 있어야 서비스가 동작합니다.
