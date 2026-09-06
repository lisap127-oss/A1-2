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

## ❓ 자주 묻는 질문 (설계 근거)

---

### Q1. 카카오 API는 왜 GET 방식을 사용하나요?

카카오 로컬 검색 API는 **공식 문서에서 GET 방식만 지원**합니다.

- 검색 조건(키워드, 개수 등)을 URL 파라미터로 전달하는 **조회 전용 API**입니다.
- 서버 데이터를 변경하지 않으므로 REST 설계 원칙상 GET이 적합합니다.
- POST는 서버에 데이터를 **생성/변경**할 때 사용하며, 단순 검색에는 해당하지 않습니다.

```python
# MapSearchClient.search() 내부 - GET 방식 사용
response = requests.get(
    self.config["url"],       # https://dapi.kakao.com/v2/local/search/keyword.json
    headers=headers,          # Authorization: KakaoAK {key}
    params={"query": query, "size": size},  # URL 파라미터로 전달
    timeout=10
)
```

> 📌 참고: [카카오 로컬 API 공식 문서](https://developers.kakao.com/docs/latest/ko/local/dev-guide)
> 명세상 `GET /v2/local/search/keyword.json` 으로 고정되어 있습니다.

---

### Q2. LLM 응답을 왜 JSON으로 강제하나요?

LLM은 기본적으로 **자유 형식 텍스트**를 반환합니다.
이를 코드에서 안정적으로 처리하려면 구조화된 형식이 필요합니다.

| 항목 | 자유 텍스트 | JSON 강제 |
|------|------------|-----------|
| 파싱 | 불안정 (정규식 필요) | `json.loads()` 한 줄 |
| 필드 누락 | 감지 불가 | `validate_recommendation()`으로 즉시 감지 |
| 타입 오류 | 감지 불가 | `isinstance()` 검사 가능 |
| 후속 처리 | 매번 파싱 로직 변경 | 딕셔너리로 바로 사용 |

```python
# 프롬프트에서 JSON 형식 명시적 강제
"""
반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트는 포함하지 마세요.
{
    "recommended_city": "도시명 (문자열)",
    "weather": "예상 날씨 (문자열)",
    "events": ["이벤트1", "이벤트2"],
    "reason": "추천 이유 (문자열)"
}
"""

# 파싱 실패 시 → 강화된 프롬프트로 재시도
cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw_text).strip()
data = json.loads(cleaned)
```

> 📌 JSON 강제 이유 요약:
> **"LLM 출력의 불확실성을 줄이고, 코드가 예측 가능하게 동작하도록 하기 위함"**

---

### Q3. 401 오류가 발생하면 어떻게 처리하나요?

401은 **인증 실패(Unauthorized)** 를 의미합니다.
주로 API 키가 없거나 잘못된 경우 발생합니다.

**발생 원인 및 해결 방법:**

| 원인 | 해결 방법 |
|------|-----------|
| `.env` 파일 누락 | 프로젝트 루트에 `.env` 파일 생성 |
| API 키 오타 | `.env`의 키 값 재확인 |
| 카카오 앱 설정 오류 | 카카오 개발자 콘솔 → 앱 → REST API 키 확인 |
| Groq 키 만료 | Groq 콘솔에서 키 재발급 |

**코드 내 처리 흐름:**

```python
# 1단계: 실행 전 키 존재 여부 사전 검증
def load_api_keys() -> dict:
    keys = {
        "groq":  os.getenv("GROQ_API_KEY", ""),
        "kakao": os.getenv("KAKAO_API_KEY", "")
    }
    missing = [k for k, v in keys.items() if not v]
    if missing:
        print(f"[오류] 누락된 API 키: {missing}")
        sys.exit(1)          # 키 없으면 즉시 종료
    return keys

# 2단계: API 호출 시 HTTP 오류 캐치 (401 포함)
except requests.exceptions.HTTPError as e:
    status = e.response.status_code   # 401, 403, 429 등
    msg = f"맛집 검색 HTTP 오류 ({status}): {e}"
    errors.append({"step": "맛집검색", "type": "HTTPError", "message": msg})
    append_error_log({                 # error_log.jsonl에 누적 저장
        "timestamp": datetime.now().isoformat(),
        "step": "맛집검색",
        "type": "HTTPError",
        "message": msg
    })
    return []                          # 빈 리스트 반환 → 프로그램 계속 실행
```

**`.env` 파일 작성 예시:**
```
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx
KAKAO_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

> 📌 401 발생 시 프로그램은 **종료되지 않고**,
> 맛집 검색 결과를 빈 리스트로 처리한 뒤 나머지 리포트를 정상 출력합니다.

---
