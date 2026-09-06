import argparse
import json
import re
import sys
import os
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from groq import Groq


# ─────────────────────────────────────────
# 환경변수 로드
# ─────────────────────────────────────────
def load_api_keys() -> dict:
    load_dotenv()
    keys = {
        "groq": os.getenv("GROQ_API_KEY", ""),
        "kakao": os.getenv("KAKAO_API_KEY", "")
    }
    missing = [k for k, v in keys.items() if not v]
    if missing:
        print(f"[오류] 누락된 API 키: {', '.join(missing)}")
        print()
        print("💡 API 키 설정 방법:")
        print("  1. 프로젝트 루트에 .env 파일 생성")
        print("  2. 아래 내용 입력 후 저장:")
        print()
        print("     GROQ_API_KEY=your_groq_api_key_here")
        print("     KAKAO_API_KEY=your_kakao_api_key_here")
        print()
        print("  3. Groq API 키 발급: https://console.groq.com")
        print("  4. Kakao API 키 발급: https://developers.kakao.com")
        sys.exit(1)
    print("✅ API 키 로딩 성공!")
    return keys


# ─────────────────────────────────────────
# CLI 인터페이스
# ─────────────────────────────────────────
def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI 국내 여행지 추천 플래너")
    parser.add_argument("--date",   required=True, help="여행 날짜 (예: 2026-10-10)")
    parser.add_argument("--theme",  required=True, help="여행 테마 (예: 힐링, 액티비티)")
    parser.add_argument("--region", required=True, help="여행 지역 (예: 제주, 강원)")
    return parser.parse_args()


def validate_date(date_str: str) -> bool:
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


# ─────────────────────────────────────────
# STEP 3: Groq AI 여행지 추천
# ─────────────────────────────────────────
def get_travel_recommendation(date: str, groq_key: str) -> str:
    client = Groq(api_key=groq_key)
    prompt = f"""
여행 날짜: {date}

위 날짜를 기준으로 국내 여행지를 1곳 추천해주세요.
반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트는 포함하지 마세요.
코드블록(```)을 사용하지 마세요. 오직 JSON만 출력하세요.

{{
    "recommended_city": "도시명(예: 제주, 강릉)",
    "weather": "해당 시기 일반적 날씨 요약",
    "events": ["행사/축제 1", "행사/축제 2"],
    "reason": "추천 근거 2~4문장"
}}
"""
    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=1024
    )
    return response.choices[0].message.content


def parse_recommendation(raw_text: str) -> dict:
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw_text).strip()
    data = json.loads(cleaned)
    required_keys = ["recommended_city", "weather", "events", "reason"]
    missing = [k for k in required_keys if k not in data]
    if missing:
        raise ValueError(f"필수 키 누락: {missing}")
    return data


# ─────────────────────────────────────────
# STEP 4: Kakao Local API 맛집 검색
# ─────────────────────────────────────────
def search_restaurants(city: str, kakao_key: str, errors: list) -> list:
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {kakao_key}"}
    params = {"query": f"{city} 맛집", "size": 5}

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        documents = response.json().get("documents", [])

        if not documents:
            print(f"[경고] '{city}' 맛집 검색 결과 0건 → 빈 리스트로 계속 진행")
            return []

        restaurants = []
        for doc in documents:
            restaurants.append({
                "name":     doc.get("place_name", ""),
                "address":  doc.get("address_name", ""),
                "category": doc.get("category_name", ""),
                "url":      doc.get("place_url", ""),
                "x":        doc.get("x", ""),
                "y":        doc.get("y", "")
            })
        return restaurants

    except Exception as e:
        errors.append({"step": "STEP4", "type": type(e).__name__, "message": str(e)})
        print(f"[경고] 맛집 검색 실패: {e}")
        return []


def print_restaurants(restaurants: list):
    print("\n" + "=" * 40)
    print("🍽️  추천 맛집 목록")
    print("=" * 40)
    if not restaurants:
        print("  검색된 맛집이 없습니다.")
        return
    for i, r in enumerate(restaurants, 1):
        print(f"\n  [{i}] {r['name']}")
        print(f"  📍 주소    : {r['address']}")
        print(f"  🏷️  카테고리: {r['category']}")
        print(f"  🔗 URL     : {r['url']}")
        print(f"  🗺️  좌표    : ({r['x']}, {r['y']})")


# ─────────────────────────────────────────
# STEP 5: 최종 리포트 생성 + 파일 저장
# ─────────────────────────────────────────
def generate_report(recommendation: dict, restaurants: list, groq_key: str, errors: list) -> str:
    """Groq AI로 Markdown 여행 리포트 생성"""

    # 맛집 목록 텍스트 구성
    if not restaurants:
        restaurant_info = "데이터 없음"
    else:
        restaurant_info = "\n".join([
            f"- {r['name']} ({r['address']})" for r in restaurants
        ])

    client = Groq(api_key=groq_key)

    prompt = f"""
아래 정보를 바탕으로 국내 여행 리포트를 Markdown 형식으로 작성해주세요.

[추천 정보]
- 도시: {recommendation['recommended_city']}
- 날씨: {recommendation['weather']}
- 행사: {', '.join(recommendation['events'])}
- 추천 이유: {recommendation['reason']}

[맛집 목록]
{restaurant_info}

리포트에는 반드시 아래 5가지 항목을 Markdown 헤더(##)로 구분하여 포함하세요:
1. 추천 지역 및 이유
2. 날씨 요약
3. 행사/축제 목록
4. 맛집 리스트 (0건이면 "데이터 없음" 표기)
5. 오전/오후/저녁 1일 일정 제안
"""

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1024
        )
        return response.choices[0].message.content

    except Exception as e:
        errors.append({"step": "STEP5", "type": type(e).__name__, "message": str(e)})
        print(f"[경고] 리포트 생성 실패: {e}")
        return ""


def save_results(date_str: str, recommendation: dict, restaurants: list, report_md: str, errors: list):
    """results/ 폴더에 JSON + MD 파일 저장"""

    # results/ 폴더 생성 (없으면 자동 생성)
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)

    # 파일명 기준 날짜
    file_date = date_str  # 예: 2026-10-10

    # ── JSON 저장 ──────────────────────────
    json_data = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "travel_date":  date_str,
        "recommendation": recommendation,
        "restaurants":    restaurants,
        "errors":         errors
    }
    json_path = results_dir / f"{file_date}_travel_plan.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    # ── Markdown 저장 ──────────────────────
    md_path = results_dir / f"{file_date}_travel_plan.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report_md)

    print(f"\n📁 결과 저장 완료!")
    print(f"  JSON : {json_path}")
    print(f"  MD   : {md_path}")

    return json_path, md_path


# ─────────────────────────────────────────
# 메인
# ─────────────────────────────────────────
def main():
    print("=" * 40)
    print("🗺️  AI 국내 여행지 추천 플래너")
    print("=" * 40)

    errors = []

    # 1. API 키 로드
    keys = load_api_keys()

    # 2. CLI 인수 파싱 및 날짜 검증
    args = parse_arguments()
    if not validate_date(args.date):
        print("[오류] 날짜 형식이 올바르지 않습니다. (예: 2026-10-10)")
        sys.exit(1)

    date_obj = datetime.strptime(args.date, "%Y-%m-%d")
    print(f"✅ 여행 날짜 확인: {args.date}")
    print(f"🎨 여행 테마: {args.theme}")
    print(f"📍 여행 지역: {args.region}")
    print(f"🗓️  {date_obj.year}년 {date_obj.month}월 {date_obj.day}일 여행 준비 시작!")

    # 3. AI 여행지 추천
    print("\n🤖 AI 여행지 추천 중...\n")
    recommendation = None
    for attempt in range(2):
        try:
            raw = get_travel_recommendation(args.date, keys["groq"])
            recommendation = parse_recommendation(raw)
            break
        except Exception as e:
            if attempt == 0:
                print(f"[경고] JSON 파싱 실패. 1회 재시도합니다.")
            else:
                errors.append({"step": "STEP3", "type": type(e).__name__, "message": str(e)})
                print(f"[오류] AI 추천 실패: {e}")

    restaurants = []

    if recommendation:
        city = recommendation["recommended_city"]

        print("=" * 40)
        print("🤖 AI 1차 여행지 추천 결과")
        print("=" * 40)
        print(f"  📍 추천 도시  : {city}")
        print(f"  🌤️  날씨 정보  : {recommendation['weather']}")
        print(f"  🎉 주요 행사  : {', '.join(recommendation['events'])}")
        print(f"  💡 추천 이유  : {recommendation['reason']}")

        # 4. 맛집 검색
        print(f"\n🍽️  '{city}' 맛집 검색 중...")
        restaurants = search_restaurants(city, keys["kakao"], errors)
        print_restaurants(restaurants)

        # 5. 최종 리포트 생성
        print(f"\n📝 최종 여행 리포트 생성 중...")
        report_md = generate_report(recommendation, restaurants, keys["groq"], errors)

        if report_md:
            print("\n" + "=" * 40)
            print("📄 생성된 리포트 미리보기 (앞 300자)")
            print("=" * 40)
            print(report_md[:300] + "...")

            # 6. 파일 저장
            save_results(args.date, recommendation, restaurants, report_md, errors)

    # 최종 오류 요약
    print("\n" + "=" * 40)
    if errors:
        print(f"⚠️  STEP 5 완료! (오류 수: {len(errors)})")
        for err in errors:
            print(f"  - [{err['step']}] {err['type']}: {err['message']}")
    else:
        print(f"✅ STEP 5 완료! (오류 수: 0)")
    print("=" * 40)


if __name__ == "__main__":
    main()