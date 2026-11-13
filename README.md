# Media Downloader

YouTube와 Instagram의 **동영상·이미지**를 링크 하나로 받는 로컬 웹 앱입니다.
내 PC에서 실행하면 브라우저 화면이 열리고, 링크를 붙여넣고 버튼만 누르면 됩니다.

- **YouTube**: 최고화질 mp4, 음원(mp3), 썸네일(jpg), 재생목록 전체 받기
- **Instagram**: 게시물 사진(여러 장 캐러셀 포함), 릴스·영상
- 여러 링크를 줄바꿈으로 한 번에 넣기, 진행률 표시, 받은 파일 미리보기
- **휴대폰·다른 PC에서 접속** (같은 와이파이 QR 코드, 외부 접속용 임시 주소, 접속 키 보호)

엔진으로 [yt-dlp](https://github.com/yt-dlp/yt-dlp)와 [gallery-dl](https://github.com/mikf/gallery-dl)을 사용합니다.

## 설치 및 실행

### 준비물
- [Python 3.10 이상](https://www.python.org/downloads/) (설치 시 "Add python.exe to PATH" 체크)
- [ffmpeg](https://ffmpeg.org/): 고화질 영상 합치기와 mp3 변환에 필요
- [Deno](https://deno.com/): 유튜브 고화질 포맷을 받는 데 필요 (없으면 일부 화질이 빠질 수 있음)

Windows에서는 아래 명령으로 한 번에 설치할 수 있습니다.

```powershell
winget install Python.Python.3.12 Gyan.FFmpeg DenoLand.Deno
```

### 실행
```bash
git clone https://github.com/nkiss2152-sudo/media-downloader.git
cd media-downloader
```

- **Windows**: `run.bat` 더블클릭
- **macOS / Linux**: `./run.sh`

처음 실행할 때 필요한 패키지를 자동으로 설치하고, 브라우저에서 `http://127.0.0.1:5000`을 엽니다.
받은 파일은 `downloads/` 폴더에 저장됩니다.

직접 실행하려면:

```bash
python -m venv .venv
.venv/Scripts/activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

## 휴대폰 · 다른 PC에서 쓰기

다운로더를 켠 PC 화면에 **"휴대폰 · 다른 PC에서 쓰기"** 칸이 나오고, QR 코드와 주소가 보입니다.

| 상황 | 방법 |
|---|---|
| 같은 와이파이 | QR 코드를 휴대폰 카메라로 찍거나 `http://<내부IP>:5000/?key=<접속키>` 주소로 접속 |
| 다른 네트워크(LTE, 회사 등) | **외부 접속 켜기** 버튼 → `https://….trycloudflare.com/?key=<접속키>` 주소 생성 |

- 다운로드는 **다운로더를 켠 PC**에서 일어나고, 휴대폰에서는 받은 파일 이름을 눌러 저장합니다.
- 다른 기기에서 쓰려면 다운로더 PC가 켜져 있고 실행 창이 열려 있어야 합니다.
- 다른 기기에서는 처음 한 번 **접속 키**가 필요합니다. QR 코드나 주소에 이미 들어 있습니다. 접속 키는 `access_key.txt`에 저장되며, 파일을 지우면 새 키가 만들어집니다.
- 외부 접속은 [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/)의 무료 임시 주소를 씁니다. 처음 한 번 설치하세요: `winget install Cloudflare.cloudflared`. 주소는 켤 때마다 바뀝니다.
- 처음 실행할 때 Windows 방화벽 창이 뜨면 **허용**을 누르세요(개인 네트워크). 같은 와이파이에서 접속이 안 되면 대부분 이 설정 때문입니다.
- 주소에 접속 키가 들어 있으니 아무에게나 공유하지 마세요.

## 다운로드 방식

| 방식 | YouTube | Instagram |
|---|---|---|
| 자동 | 최고화질 mp4 | 게시물의 사진·영상 전부 |
| 동영상 | 최고화질 mp4 | 영상만 |
| 음원(mp3) | mp3 | 릴스 음원 mp3 |
| 이미지·썸네일 | 썸네일 jpg | 사진만 |

## 쿠키 설정 (인스타그램은 거의 필수)

인스타그램은 로그인하지 않은 요청을 대부분 막습니다. 유튜브도 연령 제한 영상은 로그인이 필요합니다.
아래 두 방법 중 하나를 쓰세요.

**방법 1: `cookies.txt` 파일 (가장 확실함)**
1. 브라우저에서 instagram.com에 로그인합니다.
2. [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) 확장 프로그램으로 쿠키를 내보냅니다.
3. 파일 이름을 `cookies.txt`로 바꿔 이 프로젝트 폴더(`app.py`가 있는 곳)에 넣습니다.
4. 앱을 다시 실행하면 자동으로 사용합니다.

**방법 2: 브라우저 쿠키 직접 읽기**
화면의 "로그인 쿠키"에서 브라우저를 고르면 됩니다.
단, Windows의 최신 Chrome·Edge는 쿠키 암호화 방식 때문에 실패하는 경우가 많습니다. 이럴 땐 Firefox를 쓰거나 방법 1을 쓰세요.

> `cookies.txt`에는 로그인 정보가 들어 있으니 절대 다른 사람에게 공유하거나 GitHub에 올리지 마세요. (`.gitignore`에 이미 등록돼 있습니다.)

## 문제 해결

- **유튜브가 갑자기 안 받아질 때**: 유튜브는 자주 바뀝니다. `run.bat`을 다시 실행하면 yt-dlp가 최신 버전으로 업데이트됩니다.
- **"Instagram sent an empty media response"**: 로그인 쿠키가 필요하다는 뜻입니다. 위의 쿠키 설정을 하세요.
- **인스타 계정이 잠기거나 차단될 때**: 짧은 시간에 너무 많이 받으면 인스타가 계정을 제한할 수 있습니다. 적당히 나눠서 받으세요.
- **영상에 소리가 없거나 mp3 변환 실패**: ffmpeg가 설치돼 있는지 확인하세요 (`ffmpeg -version`).

## 주의사항

이 도구는 개인적인 보관·학습 목적으로 만들었습니다.
다운로드한 콘텐츠의 저작권은 원작자에게 있으며, 무단 재배포나 상업적 이용은 저작권법 및 각 플랫폼 이용약관에 어긋날 수 있습니다.
본인이 권리를 가진 콘텐츠이거나 허락받은 경우에만 사용하세요.

## 라이선스

[MIT](LICENSE)
