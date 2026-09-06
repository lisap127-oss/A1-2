import os
import sys
import json
import re
import argparse
import logging
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from groq import Groq

# ─────────────────────────────────────────
# 누적 오류 로그 설정  
# ─────────────────────────────────────────
LOG_FILE = Path("results/error_log.jsonl")

def setup_error_logger():
    """results/ 폴더 및 로그 파일 초기화"""
    Path("results").mkdir(exist_ok=True)
    logging.basicConfig(
        filename="results/run.log",
        level=logging.ERROR,
        format="%(asctime)s [%(levelname)s] %(message)s",
        encoding="utf-8"
    )

def append_error_log(error: dict):
    """
    실행 간 누적 오류를 error_log.jsonl에 저장 
    - 매 실행마다 append → 런 간 오류 이력 누적
    """
    LOG_FILE.parent.mkdir(exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(error, ensure_ascii=False) + "\n")
    logging.error(f"[{error['step']}] {error['type']}: {error['message']}")


# ─────────────────────────────────────────
# STEP 0: 환경 변수 로드
# ─────────────────────────────────────────
def load_api_keys() -> dict:
    load_dotenv()
    keys = {
        "groq":  os.getenv("GROQ_API_KEY", ""),
        "kakao": os.getenv("KAKAO_API_KEY", "")
    }
    missing = [k for k, v in keys.items() if not v]
    if missing:
        print(f"[오류] 누락된 API 키: {missing}")
        sys.exit(1)
    return keys


# ─────────────────────────────────────────
# STEP 1: CLI 인수 파싱 + 날짜 검증
# ─────────────────────────────────────────
def parse_arguments():
    parser = argparse.ArgumentParser(description="AI 국내 여행지 추천 플래너")
    parser.add_argument("--date",   required=True, help="여행 날짜 (예: 2026-10-10)")
    parser.add_argument("--theme",  default="힐링",  help="여행 테마 (기본: 힐링)")
    parser.add_argument("--region", default="전국",  help="여행 지역 (기본: 전국)")
    return parser.parse_args()

def validate_date(date_str: str) -> bool:
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


# ─────────────────────────────────────────
# STEP 2: 도시명 정규화 
# ─────────────────────────────────────────

# 알려진 도시 키워드 → 표준 도시명 매핑
CITY_NORMALIZE_MAP = {
    "서울특별시": "서울", "서울시": "서울",
    "부산광역시": "부산", "부산시": "부산",
    "제주특별자치도": "제주", "제주도": "제주",
    "강릉시": "강릉", "경주시": "경주",
    "전주시": "전주", "여수시": "여수",
    "인천광역시": "인천", "인천시": "인천",
    "대구광역시": "대구", "대구시": "대구",
    "광주광역시": "광주", "광주시": "광주",
    "대전광역시": "대전", "대전시": "대전",
}

# 허용된 표준 도시 목록
VALID_CITIES = [
    "서울", "부산", "제주", "강릉", "경주",
    "전주", "여수", "인천", "대구", "광주", "대전"
]

def normalize_city(city_raw: str) -> str:
    """
    도시명 정규화 
    1. 앞뒤 공백 제거
    2. 매핑 테이블로 표준명 변환
    3. 표준 도시 목록에 없으면 부분 매칭 시도
    4. 그래도 없으면 원본 반환 (재질문 로직에서 처리)
    """
    city = city_raw.strip()

    # 1) 직접 매핑
    if city in CITY_NORMALIZE_MAP:
        return CITY_NORMALIZE_MAP[city]

    # 2) 표준 도시 목록에 있으면 그대로 반환
    if city in VALID_CITIES:
        return city

    # 3) 부분 매칭 (예: "경주 불국사" → "경주")
    for valid in VALID_CITIES:
        if valid in city:
            print(f"[정규화] '{city}' → '{valid}' (부분 매칭)")
            return valid

    # 4) 매핑 테이블 부분 매칭
    for key, val in CITY_NORMALIZE_MAP.items():
        if key in city:
            print(f"[정규화] '{city}' → '{val}' (매핑 부분 매칭)")
            return val

    # 5) 정규화 실패 → 원본 반환
    print(f"[경고] 도시명 정규화 실패: '{city}' → 원본 사용")
    return city

# ─────────────────────────────────────────
# STEP 3: LLM 여행지 추천 + 재시도 프롬프트 강화
# ─────────────────────────────────────────

BASE_PROMPT_TEMPLATE = """
당신은 국내 여행 전문가입니다.
아래 조건에 맞는 여행지를 추천해주세요.

조건:
- 여행 날짜: {date}
- 여행 테마: {theme}
- 여행 지역: {region}

반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트는 포함하지 마세요.
{{
    "recommended_city": "도시명 (문자열)",
    "weather": "예상 날씨 (문자열)",
    "events": ["이벤트1", "이벤트2"],
    "reason": "추천 이유 (문자열)"
}}
"""

RETRY_PROMPT_TEMPLATE = """
당신은 국내 여행 전문가입니다.
이전 응답이 올바른 JSON 형식이 아니었습니다. 반드시 아래 규칙을 지켜주세요.

[필수 규칙]
1. 응답은 반드시 JSON 객체 하나만 출력하세요.
2. 마크다운 코드블록(```), 설명 텍스트, 줄바꿈 외 문자를 절대 포함하지 마세요.
3. events는 반드시 문자열 배열(list)이어야 합니다. 예: ["축제A", "축제B"]
4. 모든 값은 문자열 또는 배열이어야 합니다. 숫자·null·중첩 객체 금지.

조건:
- 여행 날짜: {date}
- 여행 테마: {theme}
- 여행 지역: {region}

출력 예시 (이 형식 그대로 따르세요):
{{
    "recommended_city": "경주",
    "weather": "맑고 선선함",
    "events": ["경주 벚꽃축제", "불국사 야간개장"],
    "reason": "가을 단풍과 역사 유적이 어우러진 힐링 여행지입니다."
}}
"""

def get_prompt(attempt: int, date: str, theme: str, region: str) -> str:
    """시도 횟수에 따라 프롬프트 선택"""
    template = BASE_PROMPT_TEMPLATE if attempt == 0 else RETRY_PROMPT_TEMPLATE
    return template.format(date=date, theme=theme, region=region)


def validate_recommendation(data: dict) -> list:
    """
    필수 키 존재 + 타입 검사
    반환: 오류 메시지 리스트 (비어있으면 정상)
    """
    errors = []
    required_fields = {
        "recommended_city": str,
        "weather": str,
        "events": list,
        "reason": str
    }

    for field, expected_type in required_fields.items():
        if field not in data:
            errors.append(f"필수 키 누락: '{field}'")
        elif not isinstance(data[field], expected_type):
            actual = type(data[field]).__name__
            errors.append(
                f"타입 오류: '{field}'는 {expected_type.__name__} 이어야 하나 "
                f"{actual} 가 입력됨"
            )

    # events 내부 요소 타입 검사
    if "events" in data and isinstance(data["events"], list):
        for i, item in enumerate(data["events"]):
            if not isinstance(item, str):
                errors.append(
                    f"타입 오류: 'events[{i}]'는 str 이어야 하나 "
                    f"{type(item).__name__} 가 입력됨"
                )

    return errors


def get_travel_recommendation(client: Groq, date: str, theme: str, region: str,
                               errors: list) -> dict | None:
    """LLM 호출 + 파싱 실패 시 강화된 프롬프트로 재시도"""
    for attempt in range(2):
        try:
            prompt = get_prompt(attempt, date, theme, region)
            response = client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=500
            )
            raw_text = response.choices[0].message.content
            cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw_text).strip()
            data = json.loads(cleaned)

            # 타입 검사
            type_errors = validate_recommendation(data)
            if type_errors:
                msg = f"[시도 {attempt+1}] 필드 검증 실패: {type_errors}"
                print(msg)
                errors.append({"step": "LLM검증", "type": "ValidationError", "message": msg})
                append_error_log({"timestamp": datetime.now().isoformat(),
                                  "step": "LLM검증", "type": "ValidationError", "message": msg})
                continue

            # 도시명 정규화
            data["recommended_city"] = normalize_city(data["recommended_city"])
            return data

        except json.JSONDecodeError as e:
            msg = f"[시도 {attempt+1}] JSON 파싱 실패: {e}"
            print(msg)
            errors.append({"step": "LLM파싱", "type": "JSONDecodeError", "message": msg})
            append_error_log({"timestamp": datetime.now().isoformat(),
                              "step": "LLM파싱", "type": "JSONDecodeError", "message": msg})
        except Exception as e:
            msg = f"[시도 {attempt+1}] LLM 호출 오류: {e}"
            print(msg)
            errors.append({"step": "LLM호출", "type": type(e).__name__, "message": msg})
            append_error_log({"timestamp": datetime.now().isoformat(),
                              "step": "LLM호출", "type": type(e).__name__, "message": msg})
            break

    return None


# ─────────────────────────────────────────
# STEP 4: API 추상화 레이어 + 카카오 맛집 검색
# ─────────────────────────────────────────

class MapSearchClient:
    """
    지도 검색 API 추상화 레이어.
    provider 설정만 바꾸면 다른 API로 교체 가능한 구조.
    현재 지원: kakao
    """
    PROVIDERS = {
        "kakao": {
            "url": "https://dapi.kakao.com/v2/local/search/keyword.json",
            "method": "GET",
            "auth_header": lambda key: {"Authorization": f"KakaoAK {key}"}
        }
    }

    def __init__(self, provider: str, api_key: str):
        if provider not in self.PROVIDERS:
            raise ValueError(f"지원하지 않는 provider: {provider}. 가능: {list(self.PROVIDERS)}")
        self.provider = provider
        self.config = self.PROVIDERS[provider]
        self.api_key = api_key

    def search(self, query: str, size: int = 5) -> list:
        """키워드 검색 → 결과 리스트 반환"""
        headers = self.config["auth_header"](self.api_key)
        params  = {"query": query, "size": size}
        response = requests.get(self.config["url"], headers=headers, params=params, timeout=10)
        response.raise_for_status()
        return response.json().get("documents", [])

# ─────────────────────────────────────────
# STEP 5: 맛집 검색
# ─────────────────────────────────────────

def search_restaurants(map_client: MapSearchClient, city: str, errors: list) -> list:
    """MapSearchClient를 통해 맛집 검색"""
    try:
        results = map_client.search(query=f"{city} 맛집", size=5)
        restaurants = []
        for place in results:
            restaurants.append({
                "name":     place.get("place_name", ""),
                "category": place.get("category_name", ""),
                "address":  place.get("road_address_name") or place.get("address_name", ""),
                "phone":    place.get("phone", ""),
                "url":      place.get("place_url", "")
            })
        return restaurants

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else "unknown"
        msg = f"맛집 검색 HTTP 오류 ({status}): {e}"
        print(f"[오류] {msg}")
        errors.append({"step": "맛집검색", "type": "HTTPError", "message": msg})
        append_error_log({"timestamp": datetime.now().isoformat(),
                          "step": "맛집검색", "type": "HTTPError", "message": msg})
        return []

    except Exception as e:
        msg = f"맛집 검색 오류: {e}"
        print(f"[오류] {msg}")
        errors.append({"step": "맛집검색", "type": type(e).__name__, "message": msg})
        append_error_log({"timestamp": datetime.now().isoformat(),
                          "step": "맛집검색", "type": type(e).__name__, "message": msg})
        return []


# ─────────────────────────────────────────
# STEP 6: 리포트 생성
# ─────────────────────────────────────────

def generate_report(recommendation: dict, restaurants: list,
                    date: str, theme: str) -> str:
    city   = recommendation["recommended_city"]
    weather = recommendation["weather"]
    events  = recommendation["events"]
    reason  = recommendation["reason"]

    events_str = "\n".join(f"  - {e}" for e in events) if events else "  - 정보 없음"
    rest_lines = []
    for r in restaurants:
        rest_lines.append(
            f"  - {r['name']} ({r['category']})\n"
            f"    주소: {r['address']} | 전화: {r['phone']}"
        )
    rest_str = "\n".join(rest_lines) if rest_lines else "  - 검색 결과 없음"

    return f"""
========================================
   🗺️  AI 국내 여행지 추천 리포트
========================================
📅 여행 날짜 : {date}
🎯 여행 테마 : {theme}
📍 추천 도시 : {city}
🌤️  예상 날씨 : {weather}

📝 추천 이유:
  {reason}

🎉 주요 이벤트:
{events_str}

🍽️  추천 맛집:
{rest_str}
========================================
"""


# ─────────────────────────────────────────
# STEP 7: 결과 저장
# ─────────────────────────────────────────

def save_results(recommendation: dict, restaurants: list,
                 report: str, date: str, errors: list) -> Path:
    Path("results").mkdir(exist_ok=True)
    filename = Path(f"results/travel_{date}.json")
    payload = {
        "generated_at":  datetime.now().isoformat(),
        "recommendation": recommendation,
        "restaurants":    restaurants,
        "report":         report,
        "errors":         errors
    }
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[저장] {filename}")
    return filename


# ─────────────────────────────────────────
# STEP 8: 캐시 확인
# ─────────────────────────────────────────

def load_cache(date: str) -> dict | None:
    """
    동일 날짜 결과 파일이 있으면 불러와 재사용.
    없으면 None 반환.
    """
    cache_path = Path(f"results/travel_{date}.json")
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(f"[캐시] 기존 결과 재사용: {cache_path}")
            return data
        except Exception as e:
            print(f"[캐시] 파일 읽기 실패, 새로 실행합니다: {e}")
    return None


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

def main():
    setup_error_logger()
    args   = parse_arguments()
    errors = []

    # 날짜 검증
    if not validate_date(args.date):
        print("[오류] 날짜 형식이 올바르지 않습니다. 예: 2026-10-10")
        sys.exit(1)

    # 캐시 확인
    cached = load_cache(args.date)
    if cached:
        print(cached["report"])
        print("[안내] 캐시된 결과를 출력했습니다. 새로 실행하려면 results/ 파일을 삭제하세요.")
        return

    # API 키 로드
    keys = load_api_keys()

    # 클라이언트 초기화
    groq_client = Groq(api_key=keys["groq"])
    map_client  = MapSearchClient(provider="kakao", api_key=keys["kakao"])

    # LLM 추천
    print("[1/3] 여행지 추천 중...")
    recommendation = get_travel_recommendation(
        groq_client, args.date, args.theme, args.region, errors
    )
    if not recommendation:
        print("[오류] 여행지 추천에 실패했습니다.")
        sys.exit(1)

    # 맛집 검색
    print("[2/3] 맛집 검색 중...")
    restaurants = search_restaurants(map_client, recommendation["recommended_city"], errors)

    # 리포트 생성
    print("[3/3] 리포트 생성 중...")
    report = generate_report(recommendation, restaurants, args.date, args.theme)
    print(report)

    # 결과 저장
    save_results(recommendation, restaurants, report, args.date, errors)

    if errors:
        print(f"\n[경고] 실행 중 {len(errors)}개의 오류가 발생했습니다. results/error_log.jsonl 확인 바랍니다.")


if __name__ == "__main__":
    main()    