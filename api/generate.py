import json
import os
import re
import time
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler
from services.recommendations import _RecommendationError, _recommend
from services.catalog import _catalog_response
from services.anime import _anime_catalog, _anime_detail, _recommend_anime
from services.anime_schedule import _anime_schedule
from services.boardgames import _boardgame_catalog, _recommend_boardgames
from urllib.parse import parse_qs, urlsplit


def validate_destination_precheck(destination: str):
    """
    기본 형식 및 명백한 비정상 입력/가상 단어 1차 필터링.
    (실제 지명 여부는 Gemini/OpenAI 모델이 2차로 정밀 검증)
    """
    if not destination or len(destination.strip()) < 2:
        return False, "여행 목적지는 최소 2글자 이상 입력해주세요 (예: 제주도, 강릉, 부산)."

    dest = destination.strip()

    # 1. 특수문자나 숫자만으로 이루어진 경우
    clean_text = re.sub(r'[\s\-_,.]', '', dest)
    if not clean_text or clean_text.isdigit():
        return False, f"'{dest}'은(는) 유효한 여행 목적지가 아닙니다. 실제 도시나 지역명을 입력해주세요."

    # 2. 한글 자음/모음만 연속된 경우 (ㅋㅋㅋ, ㅎㅎㅎ, ㅠㅠ 등)
    if re.fullmatch(r'[ㄱ-ㅎㅏ-ㅣ]+', clean_text):
        return False, f"'{dest}'은(는) 올바른 지역명이 아닙니다. 실제 존재하는 도시나 지역명을 입력해주세요."

    # 3. 명백한 비여행지/테스트용/인명 단어 목록 (빠른 차단)
    obvious_invalid = {
        "다인", "테스트", "test", "asdf", "qwerty", "아무거나", "아무데나", "어딘가",
        "모름", "없음", "모르겠음", "아무곳", "집", "우리집", "내집", "회사", "학교",
        "방구석", "침대", "식당", "카페", "병원", "학원", "화장실", "지구", "우주"
    }
    if dest.lower() in obvious_invalid:
        return False, f"'{dest}'은(는) 실제 존재하는 여행지로 확인되지 않습니다. 올바른 도시나 지역명을 입력해주세요 (예: 제주도, 강릉, 부산, 경주, 도쿄 등)."

    return True, ""


def generate_mock_plan(destination, duration, travelers, theme, budget, notes):
    """API 키가 없거나 테스트 환경일 때 반환하는 현실적이고 지능적인 시뮬레이션 데이터"""
    # 1. 목적지 기본 유효성 검사
    is_valid, err_msg = validate_destination_precheck(destination)
    if not is_valid:
        return {
            "success": False,
            "error": err_msg
        }

    # 2. 모의 모드에서도 무분별한 가상 지명 생성을 막기 위한 키워드 검증
    valid_keywords = [
        "도", "시", "군", "구", "읍", "면", "동", "리", "산", "섬", "해변", "비치",
        "계곡", "온천", "공원", "랜드", "월드", "타워", "호수", "강", "바다", "역", "공항",
        "서울", "부산", "제주", "강릉", "속초", "경주", "여수", "전주", "인천", "대구", "대전",
        "광주", "울산", "수원", "포항", "통영", "거제", "춘천", "남해", "단양", "안동", "평창",
        "태안", "부여", "공주", "순천", "목포", "군산", "가평", "양양", "동해", "삼척", "보성",
        "도쿄", "오사카", "후쿠오카", "교토", "삿포로", "오키나와", "다낭", "방콕", "타이베이",
        "싱가포르", "파리", "런던", "로마", "바르셀로나", "뉴욕", "하와이", "괌", "발리"
    ]
    dest_lower = destination.strip().lower()
    has_valid_keyword = any(kw in dest_lower for kw in valid_keywords)
    if not has_valid_keyword:
        return {
            "success": False,
            "error": f"'{destination}'은(는) 실제 존재하는 여행지로 확인되지 않습니다. 올바른 도시나 지역명을 입력해주세요 (예: 제주도, 강릉, 부산, 경주, 도쿄 등)."
        }

    theme_str = ", ".join(theme) if isinstance(theme, list) else str(theme)
    return {
        "success": True,
        "is_mock": True,
        "message": "현재 스마트 시뮬레이션 모드로 생성되었습니다. Vercel 환경 변수(OPENAI_API_KEY 또는 GEMINI_API_KEY)를 설정하면 실시간 최신 AI 모델과 바로 연동됩니다.",
        "data": {
            "title": f"✨ {destination} {duration} 맞춤 여행 코스 ({travelers})",
            "summary": f"{destination}(으)로 떠나는 맞춤형 여행입니다. {theme_str} 테마를 중심으로 {budget} 예산에 최적화된 동선과 감성 스팟을 엄선했습니다.",
            "destination": destination,
            "duration": duration,
            "travelers": travelers,
            "theme": theme,
            "budget": budget,
            "days": [
                {
                    "day": 1,
                    "title": "설레는 첫걸음 & 랜드마크 탐방",
                    "schedule": [
                        {
                            "time": "오전 (10:00 - 12:00)",
                            "place": f"{destination} 도착 및 대표 랜드마크",
                            "activity": f"{destination} 주요 명소 산책 및 포토존에서 인생샷 남기기",
                            "tip": "대중교통 또는 렌터카 이동 시 주차 공간을 사전 확인하세요."
                        },
                        {
                            "time": "점심 (12:30 - 14:00)",
                            "place": f"{destination} 로컬 시그니처 맛집",
                            "activity": f"현지인들이 추천하는 대표 먹거리와 제철 별미 즐기기",
                            "tip": "웨이팅이 있을 수 있으니 테이블링/캐치테이블 현장 등록을 추천합니다."
                        },
                        {
                            "time": "오후 (14:30 - 17:30)",
                            "place": f"감성 오션뷰/마운틴뷰 카페 & {theme_str} 명소",
                            "activity": "여유로운 커피 타임과 함께 현지 감성 골목 둘러보기",
                            "tip": "시그니처 음료와 디저트를 주문해보세요."
                        },
                        {
                            "time": "저녁 (18:00 - 20:30)",
                            "place": f"{destination} 야경 명소 및 감성 디너",
                            "activity": "일몰 감상 후 분위기 좋은 식당에서 저녁 식사",
                            "tip": "일몰 30분 전 도착하여 노을을 감상하면 가장 아름답습니다."
                        },
                        {
                            "time": "숙소 (21:00 이후)",
                            "place": f"{destination} 인근 아늑한 숙소 체크인",
                            "activity": "하루의 피로를 풀며 야식 및 다음 날 일정 정리",
                            "tip": "다음 날 이른 일정을 위해 꿀잠 준비!"
                        }
                    ]
                },
                {
                    "day": 2,
                    "title": "자연과 힐링 & 완벽한 마무리",
                    "schedule": [
                        {
                            "time": "오전 (09:30 - 11:30)",
                            "place": "피톤치드 숲길 or 해안 산책로",
                            "activity": "상쾌한 아침 공기를 마시며 힐링 산책",
                            "tip": "편안한 운동화 착용을 권장합니다."
                        },
                        {
                            "time": "점심 (12:00 - 13:30)",
                            "place": "든든한 향토 한식당",
                            "activity": "속 편하고 든든한 점심 식사",
                            "tip": "기념품/지역 특산물 구입도 함께 챙겨보세요."
                        },
                        {
                            "time": "오후 (14:00 - 16:30)",
                            "place": "지역 기념품 샵 & 복귀 준비",
                            "activity": "소품샵 투어 후 아쉬운 여행 마무리",
                            "tip": "교통편 시간 40분 전에는 역/터미널/공항으로 이동하세요."
                        }
                    ]
                }
            ],
            "budget_breakdown": {
                "transport": "약 30% (교통비/주유/대중교통)",
                "food": "약 40% (맛집 탐방 및 감성 카페)",
                "accommodation": "약 20% (가성비 및 분위기 숙소)",
                "etc": "약 10% (입장료, 체험비 및 기념품)"
            },
            "packing_checklist": [
                "신분증 및 카드/교통카드",
                "보조배터리 및 스마트폰 충전기",
                "카메라 또는 휴대폰 여유 용량 확보",
                "날씨에 맞는 여벌 옷 및 편한 신발",
                "상비약 (소화제, 두통약, 밴드)"
            ],
            "ai_advice": f"{travelers} 여행에 걸맞게 무리한 이동을 줄이고 만족도를 극대화했습니다. {notes if notes else '현지 사정에 따라 날씨와 휴무일을 꼭 확인하세요.'}"
        }
    }


def call_openai_api(api_key, destination, duration, travelers, theme, budget, notes):
    """OpenAI API (gpt-4o-mini)를 호출하여 구조화된 여행 계획을 생성"""
    theme_str = ", ".join(theme) if isinstance(theme, list) else str(theme)
    prompt = f"""
당신은 최고의 여행 플래너 AI '트립스파크'입니다.

[중요 지명 검증 규칙 - 최우선 순위]
1. 사용자가 입력한 여행 목적지('{destination}')가 실제로 여행할 수 있는 실존 지역(도시, 군, 구, 도, 국가, 섬, 대표 관광 명소 등)인지 가장 먼저 철저히 판별하십시오.
2. 만약 '{destination}'이(가):
   - 실제 존재하지 않는 가상의 지명 또는 판타지 세계 (예: 아틀란티스, 호그와트 등)
   - 단순한 사람 이름 (예: 다인, 철수, 영희, 민수 등)
   - 의미 없는 단어나 무작위 글자/오타/초성 (예: 다인, 블라블라, 어디가지, 밥, 테스터 등)
   - 여행 목적지(도시/지역/관광지)로 특정할 수 없는 추상적/무의미한 단어인 경우,
   절대로 가상의 식당(예: '다인식당')이나 임의의 랜드마크를 지어내지(Hallucination/환각) 마십시오!
   반드시 아래의 '검증 실패 JSON 포맷'으로만 응답해야 합니다:
{{
  "valid": false,
  "error": "'{destination}'은(는) 실제 존재하는 여행지로 확인되지 않습니다. 올바른 도시나 지역명을 입력해주세요 (예: 제주도, 강릉, 부산, 경주, 도쿄 등)."
}}

3. 만약 '{destination}'이(가) 실제 존재하는 정상적인 여행지라면:
   "valid": true 를 포함하여 아래 포맷에 맞춰 구체적이고 현실적인 여행 일정을 순수 JSON으로 응답하세요. 백틱(```json)이나 다른 설명 텍스트를 포함하지 마세요.

[정상 일정 JSON 포맷]
{{
  "valid": true,
  "title": "매력적인 여행 코스 제목",
  "summary": "코스 전체를 아우르는 2~3줄 요약 설명",
  "destination": "{destination}",
  "duration": "{duration}",
  "travelers": "{travelers}",
  "theme": "{theme_str}",
  "budget": "{budget}",
  "days": [
    {{
      "day": 1,
      "title": "1일차 테마/소제목",
      "schedule": [
        {{
          "time": "오전 (10:00 - 12:00)",
          "place": "실제 존재하는 구체적인 장소명",
          "activity": "구체적인 활동 내용",
          "tip": "방문 팁 또는 이동 팁"
        }},
        {{
          "time": "점심 (12:00 - 13:30)",
          "place": "실제 유명 추천 식당 또는 음식 종류",
          "activity": "식사 내용",
          "tip": "웨이팅/예약 팁"
        }},
        {{
          "time": "오후 (14:00 - 17:30)",
          "place": "실제 존재하는 오후 명소 및 감성 카페",
          "activity": "체험 및 휴식",
          "tip": "사진 스팟 팁"
        }},
        {{
          "time": "저녁 (18:00 - 20:30)",
          "place": "실제 저녁 식사 및 야경 명소",
          "activity": "저녁 활동",
          "tip": "야경 관람 팁"
        }}
      ]
    }}
  ],
  "budget_breakdown": {{
    "transport": "예상 교통비 비율 및 설명",
    "food": "예상 식음료비 비율 및 설명",
    "accommodation": "예상 숙박비 비율 및 설명",
    "etc": "예상 입장료 및 기타비용"
  }},
  "packing_checklist": [
    "준비물 항목 1",
    "준비물 항목 2",
    "준비물 항목 3",
    "준비물 항목 4",
    "준비물 항목 5"
  ],
  "ai_advice": "여행자를 위한 특별 맞춤 조언 (1~2줄)"
}}

[사용자 입력 정보]
- 여행 목적지: {destination}
- 여행 기간: {duration}
- 동행자: {travelers}
- 여행 테마: {theme_str}
- 1인당 예상 예산: {budget}
- 추가 요청사항: {notes if notes else '없음'}
"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "You are TripSpark, a travel concierge AI. Always validate the destination first. Respond only in valid JSON without markdown fences."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.5,
        "max_tokens": 2000
    }
    
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    
    with urllib.request.urlopen(req, timeout=25) as response:
        res_body = response.read().decode("utf-8")
        parsed = json.loads(res_body)
        raw_content = parsed["choices"][0]["message"]["content"].strip()
        
        # 혹시 마크다운 코드블록(```json ... ```)으로 감싸져 있는 경우 제거
        if raw_content.startswith("```json"):
            raw_content = raw_content[7:]
        if raw_content.startswith("```"):
            raw_content = raw_content[3:]
        if raw_content.endswith("```"):
            raw_content = raw_content[:-3]
        raw_content = raw_content.strip()

        # JSON 부분 안전 추출
        s_idx = raw_content.find('{')
        e_idx = raw_content.rfind('}')
        if s_idx != -1 and e_idx != -1:
            raw_content = raw_content[s_idx:e_idx+1]
        
        plan_data = json.loads(raw_content)

        # 목적지 유효성 검증 실패 여부 확인
        if plan_data.get("valid") is False or "error" in plan_data:
            return {
                "success": False,
                "error": plan_data.get("error") or f"'{destination}'은(는) 실제 존재하는 여행지로 확인되지 않습니다. 올바른 도시나 지역명을 입력해주세요 (예: 제주도, 강릉, 부산 등)."
            }

        return {
            "success": True,
            "is_mock": False,
            "data": plan_data
        }


def call_gemini_api(api_key, destination, duration, travelers, theme, budget, notes):
    """Google Gemini API를 호출하여 구조화된 여행 계획을 생성"""
    theme_str = ", ".join(theme) if isinstance(theme, list) else str(theme)
    prompt = f"""
당신은 최고의 여행 플래너 AI '트립스파크'입니다.

[중요 지명 검증 규칙 - 최우선 순위]
1. 사용자가 입력한 여행 목적지('{destination}')가 실제로 여행할 수 있는 실존 지역(도시, 군, 구, 도, 국가, 섬, 대표 관광 명소 등)인지 가장 먼저 철저히 판별하십시오.
2. 만약 '{destination}'이(가):
   - 실제 존재하지 않는 가상의 지명 또는 판타지 세계 (예: 아틀란티스, 호그와트 등)
   - 단순한 사람 이름 (예: 다인, 철수, 영희, 민수 등)
   - 의미 없는 단어나 무작위 글자/오타/초성 (예: 다인, 블라블라, 어디가지, 밥, 테스터 등)
   - 여행 목적지(도시/지역/관광지)로 특정할 수 없는 추상적/무의미한 단어인 경우,
   절대로 가상의 식당(예: '다인식당')이나 임의의 랜드마크를 지어내지(Hallucination/환각) 마십시오!
   반드시 아래의 '검증 실패 JSON 포맷'으로만 응답해야 합니다:
{{
  "valid": false,
  "error": "'{destination}'은(는) 실제 존재하는 여행지로 확인되지 않습니다. 올바른 도시나 지역명을 입력해주세요 (예: 제주도, 강릉, 부산, 경주, 도쿄 등)."
}}

3. 만약 '{destination}'이(가) 실제 존재하는 정상적인 여행지라면:
   "valid": true 를 포함하여 아래 포맷에 맞춰 구체적이고 현실적인 여행 일정을 순수 JSON으로 응답하세요. 백틱(```json)이나 다른 설명 텍스트를 포함하지 마세요.

[정상 일정 JSON 포맷]
{{
  "valid": true,
  "title": "매력적인 여행 코스 제목",
  "summary": "코스 전체를 아우르는 2~3줄 요약 설명",
  "destination": "{destination}",
  "duration": "{duration}",
  "travelers": "{travelers}",
  "theme": "{theme_str}",
  "budget": "{budget}",
  "days": [
    {{
      "day": 1,
      "title": "1일차 테마/소제목",
      "schedule": [
        {{
          "time": "오전 (10:00 - 12:00)",
          "place": "실제 존재하는 구체적인 장소명",
          "activity": "구체적인 활동 내용",
          "tip": "방문 팁 또는 이동 팁"
        }},
        {{
          "time": "점심 (12:00 - 13:30)",
          "place": "실제 유명 추천 식당 또는 음식 종류",
          "activity": "식사 내용",
          "tip": "웨이팅/예약 팁"
        }},
        {{
          "time": "오후 (14:00 - 17:30)",
          "place": "실제 존재하는 오후 명소 및 감성 카페",
          "activity": "체험 및 휴식",
          "tip": "사진 스팟 팁"
        }},
        {{
          "time": "저녁 (18:00 - 20:30)",
          "place": "실제 저녁 식사 및 야경 명소",
          "activity": "저녁 활동",
          "tip": "야경 관람 팁"
        }}
      ]
    }}
  ],
  "budget_breakdown": {{
    "transport": "예상 교통비 비율 및 설명",
    "food": "예상 식음료비 비율 및 설명",
    "accommodation": "예상 숙박비 비율 및 설명",
    "etc": "예상 입장료 및 기타비용"
  }},
  "packing_checklist": [
    "준비물 항목 1",
    "준비물 항목 2",
    "준비물 항목 3",
    "준비물 항목 4",
    "준비물 항목 5"
  ],
  "ai_advice": "여행자를 위한 특별 맞춤 조언 (1~2줄)"
}}

[사용자 입력 정보]
- 여행 목적지: {destination}
- 여행 기간: {duration}
- 동행자: {travelers}
- 여행 테마: {theme_str}
- 1인당 예상 예산: {budget}
- 추가 요청사항: {notes if notes else '없음'}
"""
    gemini_model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.4
        }
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    
    with urllib.request.urlopen(req, timeout=25) as response:
        res_body = response.read().decode("utf-8")
        parsed = json.loads(res_body)
        raw_text = parsed["candidates"][0]["content"]["parts"][0]["text"].strip()

        # 마크다운 코드블록 방어
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()

        # JSON 부분 안전 추출
        s_idx = raw_text.find('{')
        e_idx = raw_text.rfind('}')
        if s_idx != -1 and e_idx != -1:
            raw_text = raw_text[s_idx:e_idx+1]

        plan_data = json.loads(raw_text)

        # 목적지 유효성 검증 실패 여부 확인
        if plan_data.get("valid") is False or "error" in plan_data:
            return {
                "success": False,
                "error": plan_data.get("error") or f"'{destination}'은(는) 실제 존재하는 여행지로 확인되지 않습니다. 올바른 도시나 지역명을 입력해주세요 (예: 제주도, 강릉, 부산 등)."
            }

        return {
            "success": True,
            "is_mock": False,
            "data": plan_data
        }


class handler(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200, _cache_control=None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if _cache_control:
            self.send_header("Cache-Control", _cache_control)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        """CORS Preflight 대응"""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        """API 헬스체크"""
        _parameters = parse_qs(urlsplit(self.path).query)
        if _parameters.get("resource") == ["anime_schedule"]:
            try:
                self._send_json(_anime_schedule(_parameters), _cache_control="public, max-age=300, s-maxage=3600, stale-while-revalidate=86400")
            except _RecommendationError as _error:
                self._send_json({"success": False, "error": str(_error)}, status=_error.status, _cache_control="no-store")
            return
        if _parameters.get("resource") == ["anime_detail"]:
            try:
                self._send_json(_anime_detail(_parameters.get("id", [""])[0], int(time.time() // 600)))
            except _RecommendationError as _error:
                self._send_json({"success": False, "error": str(_error)}, status=_error.status)
            return
        if _parameters.get("resource") == ["boardgame_catalog"]:
            self._send_json(_boardgame_catalog())
            return
        if _parameters.get("resource") == ["anime_catalog"]:
            try:
                self._send_json(_anime_catalog(_parameters))
            except _RecommendationError as _error:
                self._send_json({"success": False, "error": str(_error)}, status=_error.status)
            return
        if _parameters.get("resource") == ["catalog"]:
            if os.environ.get("VERCEL"):
                # Serve the large snapshot through the CDN instead of a function response.
                self.send_response(307)
                self.send_header("Location", "/data/webtoons.json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self._send_json(_catalog_response())
            return
        res = {
            "service": "오늘의 덕질 AI recommendations API",
            "status": "online",
            "model": os.environ.get("AI_MODEL", ""),
            "configured": bool(os.environ.get("AI_API_KEY", "").strip() and os.environ.get("AI_MODEL", "").strip()),
            "usage": "POST /api/generate with type=webtoon and preferences"
        }
        self._send_json(res, 200)

    def do_POST(self):
        """AI 여행 일정 생성 요청 처리"""
        try:
            try:
                content_length = int(self.headers.get("Content-Length", 0))
            except ValueError:
                self._send_json({"success": False, "error": "요청 길이가 올바르지 않습니다."}, status=400)
                return
            if content_length <= 0:
                self._send_json({
                    "success": False,
                    "error": "요청 본문(Body)이 비어있습니다. 필수 정보를 전송해주세요."
                }, status=400)
                return

            # Accommodate the bounded browser-local exclusion list without accepting unbounded bodies.
            if content_length > 1048576:
                self._send_json({"success": False, "error": "요청 본문이 너무 큽니다."}, status=413)
                return

            try:
                body = self.rfile.read(content_length).decode("utf-8")
                data = json.loads(body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._send_json({
                    "success": False,
                    "error": "올바른 JSON 형식이 아닙니다."
                }, status=400)
                return

            if not isinstance(data, dict):
                self._send_json({"success": False, "error": "요청은 JSON 객체여야 합니다."}, status=400)
                return

            if data.get("type") in {"webtoon", "anime", "boardgame"}:
                try:
                    self._send_json(_recommend_boardgames(data) if data["type"] == "boardgame" else _recommend_anime(data) if data["type"] == "anime" else _recommend(data))
                except _RecommendationError as _error:
                    self._send_json({"success": False, "error": str(_error)}, status=_error.status)
                return

            # 1. 필수값 유효성 검증
            destination = data.get("destination", "").strip()
            if not destination:
                self._send_json({
                    "success": False,
                    "error": "여행 목적지(destination)는 필수 입력 항목입니다."
                }, status=400)
                return

            # 2. 목적지 1차 기본 유효성 검사 (명백한 비정상/테스트 단어 차단)
            is_valid_dest, dest_err_msg = validate_destination_precheck(destination)
            if not is_valid_dest:
                self._send_json({
                    "success": False,
                    "error": dest_err_msg
                }, status=400)
                return

            duration = data.get("duration", "1박 2일").strip()
            travelers = data.get("travelers", "친구와 함께").strip()
            theme = data.get("theme", ["힐링/자연", "맛집 투어"])
            budget = data.get("budget", "1인 20만원대").strip()
            notes = data.get("notes", "").strip()

            # API 키 확인 (OpenAI 우선, 다음 Gemini, 없으면 Mock 시뮬레이션)
            openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
            gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
            force_mock = os.environ.get("ENABLE_MOCK", "false").lower() == "true"

            if openai_key and not force_mock:
                try:
                    result = call_openai_api(openai_key, destination, duration, travelers, theme, budget, notes)
                    status_code = 200 if result.get("success") else 400
                    self._send_json(result, status=status_code)
                    return
                except urllib.error.HTTPError as e:
                    error_body = e.read().decode("utf-8")
                    print(f"OpenAI API error: {e.code} - {error_body}")
                    # 키 에러 또는 쿼터 제한인 경우
                    if e.code == 401:
                        self._send_json({
                            "success": False,
                            "error": "등록된 OpenAI API 키가 유효하지 않습니다. Vercel 환경 변수를 확인해주세요."
                        }, status=500)
                        return
                    elif e.code == 429:
                        self._send_json({
                            "success": False,
                            "error": "AI API 호출 한도(Quota)를 초과했습니다. 잠시 후 다시 시도해주세요."
                        }, status=500)
                        return
                    else:
                        self._send_json({
                            "success": False,
                            "error": f"AI 서비스 응답 오류가 발생했습니다. (코드: {e.code})"
                        }, status=502)
                        return
                except Exception as ex:
                    print(f"OpenAI general error: {str(ex)}")
                    self._send_json({
                        "success": False,
                        "error": f"AI 처리 중 예기치 않은 오류가 발생했습니다: {str(ex)}"
                    }, status=500)
                    return

            elif gemini_key and not force_mock:
                try:
                    result = call_gemini_api(gemini_key, destination, duration, travelers, theme, budget, notes)
                    status_code = 200 if result.get("success") else 400
                    self._send_json(result, status=status_code)
                    return
                except Exception as ex:
                    print(f"Gemini error: {str(ex)}")
                    self._send_json({
                        "success": False,
                        "error": f"Gemini API 호출 중 오류가 발생했습니다: {str(ex)}"
                    }, status=500)
                    return

            else:
                # API 키가 등록되지 않았을 때 안전하고 즉각적인 스마트 시뮬레이션 응답 제공
                result = generate_mock_plan(destination, duration, travelers, theme, budget, notes)
                status_code = 200 if result.get("success") else 400
                self._send_json(result, status=status_code)

        except Exception as e:
            self._send_json({
                "success": False,
                "error": f"서버 내부 처리 오류: {str(e)}"
            }, status=500)
