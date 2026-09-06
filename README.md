# 🗺️ 국내 여행지 추천 프로그램

## 📌 프로그램 개요
- 날짜를 입력하면 LLM이 국내 여행지를 추천하고,
  지도 API로 맛집을 검색하여 여행 리포트를 생성합니다.
- 사용 API: Groq OpenAI 계열 API(openai/gpt-oss-120b) + Kakao Local

## 🚀 실행 방법

```bash
# 1. 패키지 설치
pip install -r requirements.txt

# 2. 환경변수 설정 (.env 파일 생성)
# 아래 "API 키 설정 방법" 참고

# 3. 프로그램 실행
python travel_planner.py --date "2025-08-15"
```

## 🔑 API 키 설정 방법
프로젝트 루트에 `.env` 파일을 생성하고 아래 내용을 입력하세요.  
(실제 키 값은 절대 GitHub 등에 업로드하지 마세요!)

```
GROQ_API_KEY=여기에_본인_키_입력
KAKAO_API_KEY=여기에_본인_키_입력
```

### 환경변수 직접 설정 방법 (선택)

**macOS/Linux:**
```bash
export GROQ_API_KEY="YOUR_KEY"
export KAKAO_API_KEY="YOUR_KEY"
```

**Windows PowerShell:**
```powershell
$env:GROQ_API_KEY="YOUR_KEY"
$env:KAKAO_API_KEY="YOUR_KEY"
```

- Groq API 키 발급: https://console.groq.com
- Kakao API 키 발급: https://developers.kakao.com

## 📂 결과물 확인 방법
실행 후 `results/` 폴더에 아래 파일이 생성됩니다.

```
results/
├── YYYY-MM-DD_data.json    # 원본 데이터 (추천 결과 + 맛집 + 오류 목록)
└── YYYY-MM-DD_report.md    # 최종 여행 리포트
```

## ⚠️ API 키 보안 주의사항
- `.env` 파일을 절대 GitHub 등에 업로드하지 마세요.
- `.gitignore`에 `.env`가 포함되어 있는지 반드시 확인하세요.
- README, 결과 JSON, 리포트 파일에 키가 노출되지 않도록 주의하세요.
- 키가 유출된 경우 즉시 해당 서비스에서 키를 재발급하세요.
- API 키는 과금/쿼터가 걸린 서비스이므로 유출 시 금전적 피해가 발생할 수 있습니다.