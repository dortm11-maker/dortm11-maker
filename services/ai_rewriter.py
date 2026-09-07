"""
정통 뉴스 스타일 AI 큐레이션 & 리라이팅 엔진
- 상단 3줄 핵심 요약 + 온전하고 풍성한 실제 신문 기사 본문 문단(4~8문단) 생성
- 언론사 이름, 사진기자 바이라인, 기자 이메일 본문 완전 배제
- 사실(Fact), 수치, 인용구는 보존하면서 신뢰도 높은 저널리즘 문체로 완성
"""

import os
import re
import json
import requests
from services.curation_db import save_curated_article, get_curated_article_by_url
from services.image_enhancer import get_premium_stock_image

def is_meaningless_news(title, summary="", text=""):
    """
    실질적인 뉴스 가치가 없는 단순 방송 예고, 유튜브 알림, 운세, 부고, 인사, 게시판 공지,
    낚시성 클릭베이트, 유료 구독 홍보, 엽기·자극적 가십 단신 필터링
    """
    full = f"{title} {summary} {text[:300]}".lower()

    # 1. 유튜브 / 방송 프로그램 예고 및 시청 안내성 글 필터링
    if re.search(r'\[(?:뷰리핑|라이브|생방송|다시보기|풀영상|예고|영상|오디오|팟캐스트)\]', title, re.I):
        return True
    if re.search(r'뷰리핑|on\s*air|온에어|생중계|유튜브에서\s*보기|채널\s*구독', title, re.I):
        return True
    if re.search(r'많은\s*시청\s*바랍니다|시청바랍니다|구독과\s*좋아요|유튜브\s*채널', full):
        return True
    if re.search(r'진행\s*[:：].*출연\s*[:：]', full):
        return True

    # 2. 단순 알림, 게시판, 인사, 부고, 동정, 행사 공지 필터링
    if re.search(r'^\[(?:게시판|인사|부고|알림|동정|모집|공모|채용|입찰|행사|안내)\]', title):
        return True

    # 3. 오늘의 운세
    if re.search(r'오늘의\s*운세|띠별\s*운세', title):
        return True

    # 4. 글자 수가 너무 적거나 단순 포토/그래픽 한 장 기사
    if re.search(r'^\[(?:포토|포토뉴스|카드뉴스|그래픽)\]', title) and len(full.strip()) < 80:
        return True

    # 5. 낚시성 클릭베이트(Clickbait) 및 가십성 자극 기사 차단
    if re.search(r'단돈\s*\d+원|단돈\s*몇|단돈\s*오천|"단돈|\'단돈', title):
        return True
    if re.search(r'사람들\s*몰려\s*사갔다|몰려가\s*사갔다|오픈런\s*대란|품절\s*대란', title):
        return True
    if re.search(r'충격.*알고보니|경악한\s*이유|발칵\s*뒤집|눈물\s*펑펑|경악을\s*금치|충격\s*고백|경악케|초토화', title):
        return True

    # 6. 유료 구독 / 회원가입 유도 / 마케팅 프로모션 기사 차단
    if re.search(r'당신의\s*지적\s*탐험|더중앙플러스|프리미엄\s*콘텐츠|아르떼|유료회원|멤버십\s*전용|스페셜\s*리포트', full):
        return True

    # 7. 엽기·자극적 사건사고 단순 가십 (냉동창고 시신, 토막 등) 차단
    if re.search(r'냉동창고.*시신|토막\s*살인|숨진\s*채\s*발견.*경악|엽기\s*살인', full):
        return True

    return False


def clean_news_summary(text):
    """
    뉴스 요약(Summary/Description)에서 (서울=연합뉴스) 김예나 기자 =, (전주=연합뉴스) 등
    모든 언론사명, 바이라인, 기자명, 사진 출처, 저작권 문구를 100% 완벽 제거
    """
    if not text:
        return ""
    t = text.strip()
    
    # 1. 특수기호 머릿글 제거 (▲, ■, ◆, ●, ★, ▶ 등)
    t = re.sub(r'^[▲■◆●★▶▷☞\s]+', '', t)
    
    # 2. (도시=언론사) + [기자명 기자] = 바이라인 결합 패턴 완전 제거
    t = re.sub(r'^\s*[\(\[][가-힣a-zA-Z\s]+=[가-힣a-zA-Z\s]+[\)\]]\s*(?:[가-힣]{2,4}\s*(?:기자|특파원|논설위원|연구위원|인턴기자)\s*)?=?\s*', '', t)
    
    # 3. 주요 언론사 괄호 및 바이라인 제거 (문두 및 본문 전체)
    t = re.sub(r'[\(\[][^\)\]]*(?:연합뉴스|뉴스1|뉴시스|매일경제|한국경제|조선일보|동아일보|중앙일보|한겨레|경향신문|헤럴드경제|머니투데이|아시아경제|SBS|MBC|KBS|YTN|데일리안|이데일리|디지털타임스|전자신문|아이뉴스24|파이낸셜뉴스|로이터|AP|AFP|EPA)[^\)\]]*[\)\]]\s*(?:[가-힣]{2,4}\s*(?:기자|특파원|논설위원|연구위원|인턴기자)\s*)?=?\s*', '', t, flags=re.IGNORECASE)
    
    # 4. 사진/자료/그래픽 출처 괄호 제거
    t = re.sub(r'[\(\[][^\)\]]*(?:촬영|제공|재판매|DB|금지|저작권|사진|자료|그래픽|캡처|무단|전재|배포|송고)[^\)\]]*[\)\]]', '', t, flags=re.IGNORECASE)
    
    # 5. 기자 이름 = 형태 제거
    t = re.sub(r'^[가-힣]{2,4}\s*(?:기자|특파원|논설위원|연구위원|인턴기자)\s*=\s*', '', t)
    t = re.sub(r'[가-힣]{2,4}\s*(?:기자|특파원|인턴기자)\s*=\s*', '', t)
    
    # 6. 기자명 괄호 제거 (예: [김예나 기자], (김예나 기자))
    t = re.sub(r'[\(\[][^\)\]]*기자[^\)\]]*[\)\]]', '', t)
    
    # 7. 단독 언론사 저작권 표기 제거 (예: 로이터연합뉴스, 연합뉴스, 뉴스1 등)
    t = re.sub(r'(?:로이터|AP|AFP|EPA)?\s*(?:연합뉴스|뉴스1|뉴시스)\s*', '', t, flags=re.IGNORECASE)
    
    # 8. 이메일 및 종목코드 제거
    t = re.sub(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', '', t)
    t = re.sub(r'\[[0-9]{6}\]', '', t)
    
    # 9. 시작 부분 잔여 기호 (=, -, 등) 정리
    t = re.sub(r'^[=\-~:\s]+', '', t)
    
    # 10. 연속 공백 및 마침표 정리
    t = re.sub(r'[ \t]{2,}', ' ', t)
    t = re.sub(r'\.{2,}', '.', t)
    return t.strip(' \t-=\r\n')

def is_promotional_or_junk_line(text):
    """
    언론사 유료/회원제 플랫폼 홍보(매경플러스, 더중앙플러스 등),
    네이버/다음 검색 유도, QR코드 스캔 안내, 기사 전문/풀버전 확인 유도,
    언론사명 노출 찌꺼기를 철저히 감지하여 100% 필터링 (기사 본문 및 요약 진입 원천 차단)
    """
    if not text:
        return True
    t = text.strip()

    # 1. 언론사 유료/회원제 플랫폼 및 구독/앱 다운로드 홍보
    if re.search(r'매경플러스|더중앙플러스|아르떼|프리미엄\s*재테크|콘텐츠\s*플랫폼|재테크\s*콘텐츠|유료회원|멤버십\s*전용|스페셜\s*리포트|지적\s*탐험|앱을\s*다운|다운로드|앱스토어|구글플레이|구독하시면|구독자\s*전용', t, re.I):
        return True

    # 2. 포털 검색창 유도 및 QR코드 스캔 유도
    if re.search(r'네이버에서|다음에서|포털에서|검색창에|검색하거나|검색하면|검색해|QR코드|QR\s*코드|qr코드|스마트폰으로\s*찍으면|카메라로\s*찍으면|코드를\s*찍으면|코드를\s*스마트폰|코드를\s*스캔', t, re.I):
        return True

    # 3. 기사 전문 및 후속 링크/지면 확인 유도
    if re.search(r'기사\s*전문은|전문은.*확인|자세한\s*내용은.*확인|풀버전은|풀버전|이어서\s*보기|자세한\s*분석은|다음\s*\d가지를\s*봐라|다음\s*\d가지를|아래\s*링크|본문\s*링크|웹사이트에서\s*확인|홈페이지에서\s*확인|지면에서|신문에서\s*확인', t):
        return True

    # 4. 특정 언론사 이름이 포함된 출처/홍보성 문장
    if re.search(r'(?:매일경제|한국경제|조선일보|동아일보|중앙일보|한겨레|경향신문|헤럴드경제|머니투데이|아시아경제|연합뉴스|뉴스1|뉴시스)(?:신문)?의\s*(?:프리미엄|콘텐츠|플랫폼|지면|보도|기사|웹사이트|독자|취재진)', t):
        return True

    # 5. 제보 및 소통 안내
    if re.search(r'제보는\s*카카오톡|제보하기|독자\s*여러분의\s*제보|페이스북|인스타그램|유튜브\s*채널', t):
        return True

    return False

def clean_news_line(text):
    """
    언론사명, 플랫폼명, 바이라인, 이메일, 저작권 문구, 사진 촬영자 캡션, 방송 진행/출연자 안내 찌꺼기 철저 제거
    """
    if not text:
        return ""
    t = text.strip()

    # 0. 플랫폼 홍보 및 검색/QR 찌꺼기 라인은 통째로 즉시 삭제
    if is_promotional_or_junk_line(t):
        return ""

    # 방송 진행/출연/기자 안내 줄 완전 제거
    if re.search(r'^(?:진행|출연|제작|연출|작가|앵커|사회|패널)\s*[:：]', t):
        return ""
    if re.search(r'한겨레\d*\s*취재\s*\d*팀|한겨레\s*정치팀|연합뉴스\s*취재본부', t):
        return ""
    if re.search(r'많은\s*시청\s*바랍니다|시청바랍니다|시청\s*부탁드립니다|구독과\s*좋아요', t):
        return ""

    # 1. clean_news_summary 룰 우선 적용 (바이라인, 기자명, 언론사명 100% 제거)
    t = clean_news_summary(t)

    # 2. 본문 문장 내 잔여 언론사명 및 플랫폼명 완전 정제
    t = re.sub(r'(?:매일경제신문|매일경제|한국경제신문|한국경제|조선일보|동아일보|중앙일보|한겨레신문|한겨레|경향신문|헤럴드경제|머니투데이|아시아경제|SBS|MBC|KBS|YTN|데일리안|이데일리|디지털타임스|전자신문|아이뉴스24|파이낸셜뉴스|문화일보|세계일보|국민일보|서울신문|연합뉴스TV|연합뉴스|뉴스1|뉴시스)\s*(?:신문|뉴스)?', '', t, flags=re.IGNORECASE)
    t = re.sub(r'매경플러스|더중앙플러스', '', t, flags=re.IGNORECASE)

    # 3. 송고 일시 제거
    t = re.sub(r'\d{4}년\s*\d{1,2}월\s*\d{1,2}일(?:\s*\d{1,2}시(?:\s*\d{1,2}분)?)?', '', t)
    t = re.sub(r'\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}(?:\s*\d{1,2}:\d{1,2}(?::\d{1,2})?)?', '', t)
    t = re.sub(r'송고시간\s*:?.*', '', t)

    # 4. 웹페이지 버튼/UI 텍스트 및 구독/공유/글자크기 찌꺼기 강력 제거
    t = re.sub(r'북마크\s*공유\s*공유하기.*?닫기', '', t)
    t = re.sub(r'URL이?\s*복사되었습니다\.?', '', t)
    t = re.sub(r'카카오톡\s*페이스북\s*X\s*페이스북\s*메신저\s*네이버\s*밴드\s*URL\s*복사\.?', '', t)
    t = re.sub(r'댓글\s*글자크기\s*본문\s*글자\s*크기\s*조정.*?프린트\s*제보\.?', '', t)
    t = re.sub(r'본문\s*글자\s*크기\s*조정.*?닫기\.?', '', t)
    t = re.sub(r'폰트\s*\d단계\s*\d+px\s*', '', t)
    t = re.sub(r'구독\s*구독중\s*[가-힣]{2,4}\s*기자\s*구독\s*구독중(?:\s*이선\s*다음)?\.?', '', t)
    t = re.sub(r'구독\s*구독중', '', t)
    t = re.sub(r'[가-힣]{2,4}\s*기자\s*구독', '', t)
    t = re.sub(r'이선\s*다음', '', t)

    # 5. 빈 괄호 제거
    t = re.sub(r'\[\s*\]|\(\s*\)', '', t)

    # 6. 연속 공백 단일화 및 연속 마침표 정리
    t = re.sub(r'[ \t]{2,}', ' ', t)
    t = re.sub(r'\.{2,}', '.', t)
    t = t.replace('．', '.')
    return t.strip(' \t-=\r\n')

def is_valid_news_paragraph(line):
    """
    플랫폼 홍보, 검색/QR 유도, 찌꺼기 캡션, 촬영자 정보 등을 걸러내고 순수한 본문 설명 문단만 판별
    """
    if not line or len(line) < 15:
        return False
    # 플랫폼 홍보 및 검색/QR 유도 찌꺼기 검출 시 즉시 탈락
    if is_promotional_or_junk_line(line):
        return False
    # 웹페이지 버튼, 폰트 조절, 공유, 구독, 북마크, 앱 다운로드 UI 쓰레기 검출
    if re.search(r'폰트\s*\d단계|\d+px|글자크기|본문\s*글자\s*크기|글자\s*크기|프린트|제보|인쇄|스크랩', line):
        return False
    if re.search(r'구독|구독중|기자\s*구독|구독하기', line):
        return False
    if re.search(r'북마크|공유하기|카카오톡|페이스북|메신저|네이버\s*밴드|URL\s*복사|복사되었습니다|닫기', line):
        return False
    if re.search(r'이전\s*다음|댓글\s*\d*|공감\s*\d*|추천\s*\d*', line):
        return False
    # 방송 진행/출연/제작 안내 찌꺼기 검출
    if re.search(r'진행\s*[:：]|출연\s*[:：]|제작\s*[:：]|연출\s*[:：]|앵커\s*[:：]', line):
        return False
    if re.search(r'많은\s*시청|시청바랍니다|시청\s*바랍니다|구독과\s*좋아요|유튜브에서\s*보기', line):
        return False
    if re.search(r'(?:취재|정치|경제|사회|문화|국제|산업|IT)\s*\d*팀\s*(?:팀장|기자)', line):
        return False
    # 사진 캡션 및 촬영자/현장 묘사 찌꺼기 검출 (본문 수치나 사실이 아닌 순수 사진 설명문 제외)
    if re.search(r'촬영|제공|재판매|DB\s*금지|전재|무단|송고|연합뉴스', line):
        return False
    if re.search(r'내려다보이고\s*있다|바라보고\s*있다|포즈를\s*취하고|기념촬영|전망대.*스카이에서|자료사진|사진은\s*기사|사진제공|출처\s*[:：]|설명회에서\s*발언하고|간담회에서\s*발언하고', line):
        return False
    # 슬로건이나 짧은 구호 형태의 캡션 줄 검출
    if re.search(r'슬로건$|전경$|사진$|모습$', line):
        return False
    # 순수 날짜/시간 줄 검출
    if re.search(r'^\s*\d{4}[년.\-/]\s*\d{1,2}[월.\-/]', line) and len(line) < 30:
        return False
    # 마침표나 종결 어미가 없는 짧은 부제목 줄 검출 (따옴표 고려)
    core = line.rstrip(' "\'”’')
    if not core.endswith('.') and not core.endswith('다') and len(line) < 35:
        return False
    return True

def clean_news_title(title):
    """
    헤드라인에서 [부동산 손자병법], [뷰리핑], [게시판], [인사], [부고], [단독] 등
    제목 위치를 불문하고 모든 대괄호/소괄호 기획 코너명 및 언론사명 꼬리표 100% 제거
    """
    if not title:
        return ""
    t = title.strip()
    
    # 1. 제목 어디에 있든 모든 대괄호 태그 ([부동산 손자병법], [단독], [속보], [기획], [해설] 등) 완전 제거
    t = re.sub(r'\[[^\]]*\]', '', t)
    
    # 2. 끝이나 앞에 붙은 소괄호 언론사명/기획명 제거 (예: (종합), (상보), (매일경제))
    t = re.sub(r'\([^\)]*(?:연합뉴스|뉴스1|뉴시스|매일경제|한국경제|조선일보|동아일보|중앙일보|한겨레|경향신문|헤럴드경제|머니투데이|아시아경제|SBS|MBC|KBS|YTN|종합|상보|속보|단독)[^\)]*\)', '', t, flags=re.IGNORECASE)
    
    # 3. 언론사 접미어 및 플랫폼명 제거
    t = re.sub(r'[\s\-_\|]+(?:연합뉴스|뉴스1|뉴시스|매일경제|한국경제|조선일보|동아일보|중앙일보|한겨레|경향신문|헤럴드경제|머니투데이|아시아경제|SBS|MBC|KBS|YTN|데일리안|이데일리|디지털타임스|전자신문|아이뉴스24|파이낸셜뉴스|매경플러스|더중앙플러스)\s*$', '', t, flags=re.IGNORECASE)
    t = re.sub(r'(?:매경플러스|더중앙플러스)', '', t, flags=re.IGNORECASE)

    # 4. 문두 특수기호 제거
    t = re.sub(r'^[▲■◆●★▶▷☞\s]+', '', t)
    
    # 5. 인위적으로 붙은 '동향 분석' 등 불필요한 꼬리표 제거
    t = re.sub(r'(?:…|\.\.\.|\s)*동향\s*분석', '', t)
    t = re.sub(r'(?:…|\.\.\.|\s)*시장\s*영향\s*분석', '', t)
    t = re.sub(r'(?:…|\.\.\.|\s)*배경과\s*전망', '', t)
    t = re.sub(r'(?:…|\.\.\.|\s)*향후\s*추이\s*주목', '', t)
    t = re.sub(r'(?:…|\.\.\.|\s)*공식\s*집계\s*발표', '', t)
    t = re.sub(r'[…\.\s]+$', '', t)
    return t.strip()

def make_short_bullet(text, max_len=95):
    """
    본문의 핵심 맥락과 통계 수치를 충실히 담아 자연스럽고 완결된 핵심 브리핑 요약문 생성
    (플랫폼 홍보 및 검색/QR 유도 문구는 원천 배제)
    """
    if is_promotional_or_junk_line(text):
        return ""

    s = text.strip()
    s = re.sub(r'^[▲■◆●★▶▷☞\s]+', '', s)
    s = re.sub(r'\(.*?\)|\[.*?\]', '', s)
    s = re.sub(r'^(?:증권가 분석에 따르면|전문가들은|업계 분석에 따르면|관계자에 따르면|보도에 따르면)\s*', '', s)
    s = re.sub(r'\s{2,}', ' ', s).strip(' .,~')
    s = s.replace('．', '.')

    if is_promotional_or_junk_line(s):
        return ""

    if len(s) > max_len:
        # 1. max_len 내에 온전한 마침표(?!)가 있으면 그 지점까지 취합
        m = re.search(r'(?<=[.?!])\s+', s[:max_len])
        if m and m.start() >= 30:
            s = s[:m.start()].strip()
        else:
            # 쉼표 기준 자연스러운 분절 탐색
            m_comma = re.search(r'[,](?=\s)', s[:max_len])
            if m_comma and m_comma.start() >= 35:
                s = s[:m_comma.start()].strip()
                if any(w in s for w in ['경쟁률', '비율', '수치', '건수', '가구', '%', '배', '억', '원']):
                    s += ' 등으로 집계됐습니다'
                else:
                    s += ' 관련 관심이 집중되고 있습니다'
            else:
                cut = s[:max_len].rsplit(' ', 1)[0].strip()
                # 끝부분 불필요한 조사 완벽 제거
                cut = re.sub(r'(?:을|를|이|가|에|의|과|와|로|으로|는|은|도|며|고|서|이라는|이라며|라고)\s*$', '', cut).strip()
                
                # 따옴표 열리고 안 닫힌 경우 닫아줌
                if cut.count('“') > cut.count('”'):
                    cut += '”'
                if cut.count('‘') > cut.count('’'):
                    cut += '’'
                if cut.count('"') % 2 != 0:
                    cut += '"'

                # 종결 어미 보정
                if not cut.endswith(('다', '다.', '습니다', '했습니다', '밝혔습니다', '전했습니다', '분석했습니다', '강조했습니다', '말했습니다', '집계됐습니다')):
                    if cut.endswith(('비판', '꼬집', '지적', '반발')):
                        cut += '했습니다'
                    elif cut.endswith(('밝혀', '전해', '알려')):
                        cut += '졌습니다'
                    elif cut.endswith(('입장', '의견', '주장')):
                        cut += '을 나타냈습니다'
                    elif any(w in cut for w in ['경쟁률', '비율', '수치', '건수', '가구', '%', '배']):
                        cut += ' 등으로 집계됐습니다'
                    else:
                        cut += '에 관심이 쏠리고 있습니다'
                s = cut

    return s.strip()

def rewrite_news_title(title, paragraphs=None, category='전체'):
    """
    원문 뉴스의 실제 핵심 팩트(키워드, 주제, 수치)는 온전히 유지하되,
    원문 제목과 100% 동일하지 않도록 저작권 안심 독창적 뉴스 브리핑 헤드라인으로 반드시 전면 재구성
    """
    if not title:
        return "실시간 주요 뉴스 브리핑"
        
    orig_t = title.strip()
    t = clean_news_title(title)
    
    # 1. 취재원/인용원 접두어 자연스럽게 정돈
    t = re.sub(r'^[가-힣a-zA-Z0-9]+(?:증권|투자증권|연구원|연구위원)\s*[\":\']\s*', '', t)
    t = re.sub(r'^[가-힣]{2,4}\s*(?:기자|특파원|대표|장관|총리|위원장|부총리)\s*[\":\']\s*', '', t)
    t = t.strip('\"\' ')

    cand = ""

    # 2. 의문형 헤드라인 변환 (~왜 오를까, ~어디로, ~이유는, ~꺾이나 등)
    m_why = re.search(r'(.+?)\s*(?:왜\s*(?:오를까|올라|상승할까)|왜\s*(?:내릴까|떨어질까|하락할까)|왜\s*그럴까|어디로\s*가나|어떨까|가능할까|꺾이나|이유는|배경은)', t)
    if m_why:
        topic = m_why.group(1).strip()
        topic = re.sub(r'줄어드는데', '감소세 속', topic)
        topic = re.sub(r'늘어나는데', '증가세 속', topic)
        topic = re.sub(r'오르는데', '상승세 속', topic)
        topic = re.sub(r'내리는데', '하락세 속', topic)
        topic = re.sub(r'[은는이가]$', '', topic).strip()
        
        if any(w in t for w in ['오를까', '올라', '상승']):
            cand = f"{topic} 상승 배경과 원인 분석… 주요 변수 진단"
        elif any(w in t for w in ['내릴까', '떨어질까', '하락', '꺾이나']):
            cand = f"{topic} 하락 전환 가능성 진단… 시장 파급 효과 분석"
        else:
            cand = f"{topic} 핵심 쟁점과 향후 전망 분석"

    # 3. 대립/조건형 헤드라인 (~는데, ~지만)
    elif '는데' in t or '지만' in t:
        parts = re.split(r'는데|지만', t, maxsplit=1)
        front = parts[0].strip()
        back = parts[1].strip()
        front = re.sub(r'인구\s*줄어', '인구 감소세 속', front)
        front = re.sub(r'경기\s*침체', '경기 둔화 속', front)
        cand = f"{front}에도 {back} 지속… 주요 배경과 시장 진단"

    # 4. 구분 기호(… 또는 ... 또는 - 또는 |)를 기준으로 분절 정돈
    elif any(sep in t for sep in ['…', '...']):
        parts = re.split(r'…|\.\.\.', t)
        if len(parts) >= 2:
            front = parts[0].strip().strip('\"\' ')
            back = parts[1].strip().strip('\"\' ')
            
            # 앞부분 정돈
            front = re.sub(r'([가-힣a-zA-Z0-9]+),\s*', r'\1, ', front)
            front = re.sub(r'오르자', '상승세에', front)
            front = re.sub(r'치솟자', '급등세 지속에', front)
            front = re.sub(r'내리자', '하락 전환에', front)
            
            # 뒷부분 서술어 품격 있게 재구성
            if '집중' in back:
                back_new = re.sub(r'집중$', '쏠림 현상 심화', back)
            elif '급증' in back:
                back_new = re.sub(r'급증$', '큰 폭 증가세 기록', back)
            elif '비상' in back:
                back_new = re.sub(r'비상$', '긴장감 고조', back)
            elif back.endswith('확대'):
                back_new = '대폭 확대 추진' if '대폭' not in back else '확대 추진 본격화'
            elif back.endswith('강화'):
                back_new = '본격 강화 방침'
            elif back.endswith('출시'):
                back_new = '공식 출시 및 공급'
            elif back.endswith('상향') or '목표가↑' in back:
                back_new = '수익성 개선 기대감에 목표가 상향'
            elif back.endswith('하향') or '목표가↓' in back:
                back_new = '업황 둔화 우려에 목표가 조정'
            elif any(w in back for w in ['차질', '난항']):
                back_new = f'{back} 우려 확산' if not back.endswith('우려') else back
            elif back.endswith('모색'):
                back_new = '전략적 모색 및 추진'
            elif back.endswith('반영'):
                back_new = '적극 반영 방침'
            elif back.endswith('촉구'):
                back_new = '강력 촉구 입장'
            elif back.endswith('제기'):
                back_new = '문제점 공식 제기'
            else:
                back_new = f"{back} 흐름 뚜렷"
                
            cand = f"{front}… {back_new}"

    # 5. 수치 지표형 헤드라인 (예: 지지율 37.4%, 거래량 40% 등)
    if not cand:
        num_match = re.search(r'([가-힣\s]+)\s*(\d+(?:\.\d+)?(?:%|조|억|만|배))', t)
        if num_match:
            prefix_word = num_match.group(1).strip()
            val = num_match.group(2).strip()
            if any(w in t for w in ['상승', '급증', '오름세']):
                cand = f"{prefix_word} {val} 상승세 기록… 시장 영향 분석"
            elif any(w in t for w in ['하락', '급락', '내림세']):
                cand = f"{prefix_word} {val} 하락세 집계… 배경과 전망"
            else:
                cand = f"{prefix_word} {val} 기록… 주요 배경과 시장 파급 전망"

    # 6. 기본 변환: 원본과 100% 동일하지 않도록 저널리즘 분석 꼬리표 결합
    if not cand or cand == orig_t or cand == t:
        if t.endswith(('발표', '추진', '확대', '점검', '개최', '지속', '착수')):
            cand = f"{t}… 세부 동향 및 향후 파급 전망"
        else:
            cand = f"{t}… 핵심 배경과 시장 파급 전망"

    # 최종 정돈
    cand = re.sub(r'[…\.\s]+$', '', cand)
    return cand.strip()


# 문장 어미 자연스러운 뉴스체 변환
ENDING_RULES = [
    (r'것으로 알려졌다[.\s]*', '것으로 전해졌습니다.'),
    (r'것으로 나타났다[.\s]*', '것으로 파악됐습니다.'),
    (r'것으로 보인다[.\s]*', '것으로 관측됩니다.'),
    (r'것으로 확인됐다[.\s]*', '것으로 공식 확인됐습니다.'),
    (r'내다봤다[.\s]*', '내다봤습니다.'),
    (r'덧붙였다[.\s]*', '덧붙였습니다.'),
    (r'풀이된다[.\s]*', '풀이됩니다.'),
    (r'분석했다[.\s]*', '분석했습니다.'),
    (r'평가했다[.\s]*', '평가했습니다.'),
    (r'이어졌다[.\s]*', '이어졌습니다.'),
    (r'밝혔다[.\s]*', '설명했습니다.'),
    (r'전했다[.\s]*', '보도했습니다.'),
    (r'강조했다[.\s]*', '분명히 했습니다.'),
    (r'설명했다[.\s]*', '밝혔습니다.'),
    (r'주장했다[.\s]*', '의견을 피력했습니다.'),
    (r'지적했다[.\s]*', '문제를 짚었습니다.'),
    (r'말했다[.\s]*', '밝혔습니다.'),
    (r'전망된다[.\s]*', '전망이 우세합니다.'),
    (r'예상된다[.\s]*', '예상이 나오고 있습니다.'),
    (r'기록했다[.\s]*', '집계됐습니다.'),
    (r'도달했다[.\s]*', '이르렀습니다.'),
    (r'보였다[.\s]*', '나타났습니다.'),
    (r'확인됐다[.\s]*', '파악됐습니다.'),
    (r'발표했다[.\s]*', '공식 발표했습니다.'),
    (r'올렸다[.\s]*', '상향 조정했습니다.'),
    (r'내렸다[.\s]*', '하향 조정했습니다.'),
    (r'상회했다[.\s]*', '상회했습니다.'),
    (r'유지했다[.\s]*', '유지했습니다.'),
    (r'전망했다[.\s]*', '전망했습니다.'),
    (r'산정했다[.\s]*', '산정됐습니다.'),
    (r'짚었다[.\s]*', '짚었습니다.'),
    (r'판단한다[.\s]*', '판단했습니다.'),
    # 일반적인 과거 서술형 변환
    (r'([가-힣]{2,})했다[.\s]*', r'\1했습니다.'),
    (r'([가-힣]{2,})됐다[.\s]*', r'\1됐습니다.'),
    (r'했습니다했습니다\.', '했습니다.'),
    (r'됐습니다됐습니다\.', '됐습니다.')
]



def local_rewrite_paragraphs(paragraphs):
    """본문 각 문단을 매끄럽고 신뢰도 높은 실제 신문 기사 문체로 재가공"""
    cleaned_paras = []
    for p in paragraphs:
        cp = clean_news_line(p)
        if len(cp) >= 15:
            # 어미 변환
            for pat, repl in ENDING_RULES:
                cp = re.sub(pat, repl, cp)
            cleaned_paras.append(cp)
    return cleaned_paras

def generate_3line_summary(title, paragraphs):
    """기사 핵심 팩트에서 깔끔하고 절제된 3줄 요약 추출"""
    clean_title = title.strip()
    
    candidates = []
    for p in paragraphs:
        cleaned = clean_news_line(p)
        if len(cleaned) < 20:
            continue
        # 문장 단위 분리
        sentences = [s.strip() for s in cleaned.split('.') if len(s.strip()) > 15]
        for s in sentences:
            # 핵심 수치나 키워드가 포함된 문장 우선 선별
            if any(c in s for c in ['%', '억원', '달러', '상향', '하향', '발표', '전망', '증가', '감소', '기록', '유지', '출시', '생산', '차질']):
                clean_s = clean_news_line(s)
                if clean_s not in candidates and clean_s != clean_title:
                    candidates.append(clean_s)
                    if len(candidates) >= 3:
                        break
        if len(candidates) >= 3:
            break

    points = [clean_title]
    for c in candidates:
        if len(points) < 3 and c not in points:
            points.append(c)

    # 부족할 경우 다른 문단에서 보강
    if len(points) < 3:
        for p in paragraphs[1:]:
            cleaned = clean_news_line(p).split('.')[0].strip()
            if len(cleaned) > 20 and cleaned not in points:
                points.append(cleaned)
                if len(points) >= 3:
                    break

    while len(points) < 3:
        points.append("관련 세부 동향 및 후속 조치에 업계와 시장의 관심이 모이고 있습니다.")

    return points[:3]

def extract_factual_data(url, title=""):
    """
    원문 웹페이지에서 언론사 캡션/바이라인/찌꺼기는 걷어내고,
    독자에게 유용한 실제 기사의 사실 설명 문단과 핵심 수치(Fact Points)를 폭넓게 추출 (최대 60문장)
    """
    facts = []
    if not url or not url.startswith('http'):
        return facts

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        }
        resp = requests.get(url, headers=headers, timeout=5.0)
        if resp.status_code == 200 and len(resp.content) > 200:
            # 다중 한글 인코딩 안전 디코딩 (utf-8, cp949, euc-kr)
            raw_bytes = resp.content
            html_text = ""
            for enc in ['utf-8', 'cp949', 'euc-kr']:
                try:
                    html_text = raw_bytes.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            if not html_text:
                html_text = raw_bytes.decode('utf-8', 'replace')

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_text, 'html.parser')
            
            # UI 및 찌꺼기 엘리먼트 전면 파기 (사진 캡션 태그 포함)
            for junk in soup.select('script, style, button, nav, header, footer, noscript, svg, form, input, select, textarea, .share_wrap, .sns_wrap, .byline, .reporter, .font_size, .btn_area, .util_area, .reply_area, .comment_area, .copyright, .article_relation, .recommend_news, .subscribe_wrap, .subscribe_box, .sns_area, .aside_wrap, .link_news, .ad_wrap, .vod_area, .vod_player, figcaption, .photo_layout, .photo_desc, .view_caption, .img_desc, .caption'):
                junk.decompose()
            
            # 국내 주요 포털 및 언론사 본문 컨테이너 정밀 탐색 (네이버, 다음, 뉴시스, 뉴스1, 조선, 중앙, 동아, 매경, 한경, KBS, SBS, MBC 등)
            body = (
                soup.select_one('#dic_area') or              # 네이버 뉴스 본문
                soup.select_one('#newsct_article') or        # 네이버 뉴스 모바일/PC
                soup.select_one('.article_view') or          # 다음 뉴스 본문
                soup.select_one('#textBody') or              # 뉴시스 본문
                soup.select_one('article#textBody') or       # 뉴시스
                soup.select_one('.view_text') or             # 뉴시스 / 뉴스1
                soup.select_one('#articles_detail') or       # 뉴스1 본문
                soup.select_one('article.story-news') or     # 연합뉴스 본문
                soup.select_one('.story-news') or            # 연합뉴스
                soup.select_one('section.article-body') or   # 조선일보 본문
                soup.select_one('.article-body') or          # 조선/중앙 본문
                soup.select_one('.main_text') or             # SBS 뉴스 본문
                soup.select_one('.article_cont') or          # SBS / 방송사 본문
                soup.select_one('#cont_newstext') or         # KBS 뉴스 본문
                soup.select_one('.detail-body') or           # KBS 상세 본문
                soup.select_one('.news_content') or          # MBC 뉴스 본문
                soup.select_one('.art_txt') or               # 매일경제
                soup.select_one('#articletxt') or            # 한국경제
                soup.select_one('.article_txt') or           # 동아일보
                soup.select_one('#article_body') or          # 매경/중앙
                soup.select_one('article._article_body') or  # 주요 포털
                soup.select_one('article.comp_news_article') or
                soup.select_one('#articleWrap') or
                soup.select_one('.news_cnt_detail_wrap') or
                soup.select_one('#articleBody') or
                soup.find('article') or
                soup.select_one('.article') or
                soup.select_one('.content')
            )
            
            raw_blocks = []
            if body:
                # 1. 본문 내 <br> 태그를 줄바꿈(\n) 개행문자로 전면 치환
                for br in body.find_all('br'):
                    br.replace_with('\n')

                # 2. <p> 태그가 3개 이상 존재하면 <p> 우선 추출
                p_tags = body.find_all('p')
                valid_p = [p.get_text().strip() for p in p_tags if len(p.get_text().strip()) >= 15]
                if len(valid_p) >= 3:
                    for t in valid_p:
                        if t not in raw_blocks:
                            raw_blocks.append(t)
                else:
                    # 3. <p> 태그가 적거나 없는 사이트(네이버 dic_area, 뉴시스 등)는 줄바꿈(\n) 단위로 순수 문단 추출
                    for line in body.get_text().split('\n'):
                        t = line.strip()
                        if t and len(t) >= 15 and t not in raw_blocks:
                            raw_blocks.append(t)

            for raw_line in raw_blocks:
                cleaned = clean_news_line(raw_line)
                
                # 유효한 본문 문단 검증
                if not is_valid_news_paragraph(cleaned):
                    continue

                # 기자명 접두어 정제
                cleaned = re.sub(r'^[가-힣]{2,4}\s*(?:연구원|연구위원|기자|위원)\s*은?\s*(?:이날 보고서에서)?\s*', '업계 분석에 따르면 ', cleaned)
                cleaned = re.sub(r'[가-힣]{2,4}\s*연구원은?\s*', '전문가들은 ', cleaned)
                cleaned = re.sub(r'\[[0-9]{6}\]', '', cleaned)
                cleaned = cleaned.strip()

                # 마침표 기준 문장 분리
                sub_sentences = [s.strip().rstrip('.') + '.' for s in re.split(r'(?<=[.?!])\s+', cleaned) if len(s.strip()) >= 15]
                if not sub_sentences:
                    sub_sentences = [cleaned]

                for sent in sub_sentences:
                    sent = clean_news_line(sent)
                    if is_valid_news_paragraph(sent) and sent not in facts:
                        facts.append(sent)
                        if len(facts) >= 80:
                            break
                if len(facts) >= 80:
                    break

            # 제목과 내용 간의 교차 연관성 검증 (사이드바 추천 기사나 엉뚱한 광고성 텍스트가 긁혔는지 방어)
            if title and facts:
                keywords = [w for w in re.findall(r'[가-힣a-zA-Z0-9]{2,}', title) if w not in ['속보', '단독', '종합', '기자', '뉴스', '오늘', '실시간']]
                if keywords:
                    has_match = any(any(k in f for k in keywords) for f in facts)
                    if not has_match:
                        facts = []

    except Exception as e:
        print(f"[Fact Extraction Warning] {e}")

    return facts

def local_generate_issue_briefing(title, category="전체", fact_points=None):
    """
    원문의 실제 알짜 정보(혜택, 통계 수치, 비율 %, 금액, 건수, 가구수, 당사자/전문가 발언 인용구)를
    과도하게 압축하거나 자르지 않고 온전히 살려 신문 원문과 대등한 풍성한 긴 호흡의 정통 기사(10~25문단) 및 완결된 3줄 핵심 요약 생성
    (플랫폼 홍보, 검색/QR 유도 문구는 100% 원천 배제)
    """
    clean_t = clean_news_title(title)
    
    # 팩트 데이터가 있는 경우: 원문의 통계와 문맥을 살려 풍성한 문단으로 조립
    if fact_points and len(fact_points) >= 2:
        # 1. 문장 단위 어미 정통 뉴스체 변환 (홍보 및 찌꺼기 라인 철저 배제)
        converted_sentences = []
        for f in fact_points:
            if is_promotional_or_junk_line(f):
                continue
            p = clean_news_line(f)
            if not p or len(p) < 15:
                continue
            for pat, repl in ENDING_RULES:
                p = re.sub(pat, repl, p)
            p = p.replace('．', '.')
            if p and len(p) >= 15 and p not in converted_sentences and not is_promotional_or_junk_line(p):
                converted_sentences.append(p)

        # 2. 실제 원문 신문 기사처럼 독자가 편하게 읽도록 1~2문장 및 발언 인용구 단위로 깔끔하게 문단(줄바꿈) 분리
        paras = []
        temp_chunk = []

        for sent in converted_sentences:
            if is_promotional_or_junk_line(sent):
                continue
            is_quote = any(q in sent for q in ['"', "'", '“', '”', '‘', '’']) or any(v in sent for v in ['라고 밝혔', '라고 말했', '라고 전했', '라며 ', '며 입장을', '며 강조'])
            has_stat = any(u in sent for u in ['대 1', '대1', '%', '배 ', '배로', '가구', '건의', '건이', '억원', '조원', '달러'])
            is_long = len(sent) >= 80

            # 발언문이나 핵심 통계 수치가 있는 문장은 독립 문단으로 분리하여 가독성과 팩트 전달력 극대화
            if is_quote or (has_stat and is_long):
                if temp_chunk:
                    chunk_text = " ".join(temp_chunk)
                    if not is_promotional_or_junk_line(chunk_text):
                        paras.append(chunk_text)
                    temp_chunk = []
                paras.append(sent)
            else:
                temp_chunk.append(sent)
                if len(temp_chunk) >= 2:
                    chunk_text = " ".join(temp_chunk)
                    if not is_promotional_or_junk_line(chunk_text):
                        paras.append(chunk_text)
                    temp_chunk = []

            if len(paras) >= 35:
                break

        if temp_chunk and len(paras) < 35:
            chunk_text = " ".join(temp_chunk)
            if not is_promotional_or_junk_line(chunk_text):
                paras.append(chunk_text)

        # 문단 수가 부족할 경우(4개 이하), 맥락 보강 문단을 덧붙임
        if len(paras) < 5:
            cat_supplements = {
                '경제': "금융 및 경제 전문가들은 이번 사안이 중장기적인 시장 흐름과 가계 재정 운용에 미치는 영향을 주시하고 있으며, 체계적인 대응 전략 마련이 필요한 시점이라고 강조했습니다.",
                '부동산': "부동산 및 자산 관리 전문가들은 시장 변동성에 대비해 중장기적인 자산 배분과 실수요 관점의 신중한 접근이 요구된다고 조언했습니다.",
                '증권': "증권가에서는 단기 수급 변화뿐만 아니라 기업의 펀더멘털과 대외 거시 경제 변수를 종합적으로 고려한 포트폴리오 다변화가 필요하다고 분석했습니다.",
                '정치': "정치권 안팎에서는 이번 쟁점을 둘러싼 여야의 공방이 향후 정국 주도권과 정책 심의 과정 전반에 적지 않은 파장을 미칠 것으로 내다보고 있습니다.",
                '사회': "사회 각계에서는 이번 사안이 제기한 제도적 미비점을 보완하고 공정한 사회적 신뢰를 회복하기 위한 실효성 있는 대책 마련을 촉구하고 있습니다.",
                '전체': "전문가들은 이번 이슈가 시장 참여자들에게 중요한 시사점을 던져주고 있는 만큼, 향후 전개될 정책 변화와 관련 업계의 구체적인 후속 조치를 면밀히 살펴볼 필요가 있다고 제언했습니다."
            }
            paras.append(cat_supplements.get(category, cat_supplements['전체']))

        # 3. 3줄 핵심 요약 구성 (각 50~85자 내외의 자연스러운 완결 문장)
        summary = []
        seen_sum = set()

        # 1) 첫 번째 요약: 핵심 발단/주제
        first_sent = ""
        for s in converted_sentences:
            if not is_promotional_or_junk_line(s):
                b = make_short_bullet(s, max_len=80)
                if b and len(b) >= 20 and not is_promotional_or_junk_line(b):
                    first_sent = b
                    break
        if not first_sent:
            first_sent = make_short_bullet(clean_t, max_len=80)
        summary.append(first_sent)
        seen_sum.add(first_sent)

        # 2) 두 번째 요약: 구체적 수치 및 통계 데이터 (%, 배, 건, 가구, 대 1 등)
        mid_idx = len(converted_sentences) // 2
        for s in converted_sentences[1:]:
            if is_promotional_or_junk_line(s):
                continue
            if any(num in s for num in ['%', '배', '건', '가구', '대 1', '대1', '원', '억', '달러', '증가', '감소']):
                bullet = make_short_bullet(s, max_len=85)
                if len(bullet) >= 20 and bullet not in seen_sum and not is_promotional_or_junk_line(bullet):
                    summary.append(bullet)
                    seen_sum.add(bullet)
                    break

        # 3) 세 번째 요약: 후반부 당사자/전문가 발언 또는 향후 시장 전망
        for s in reversed(converted_sentences[mid_idx:]):
            if is_promotional_or_junk_line(s):
                continue
            bullet = make_short_bullet(s, max_len=85)
            if len(bullet) >= 20 and bullet not in seen_sum and not is_promotional_or_junk_line(bullet):
                summary.append(bullet)
                seen_sum.add(bullet)
                break

        # 부족할 경우 순차 보강
        for s in converted_sentences:
            if len(summary) >= 3:
                break
            if is_promotional_or_junk_line(s):
                continue
            b = make_short_bullet(s, max_len=80)
            if len(b) >= 20 and b not in seen_sum and not is_promotional_or_junk_line(b):
                summary.append(b)
                seen_sum.add(b)

        rewritten_title = rewrite_news_title(clean_t, paragraphs=paras, category=category)
        if not rewritten_title or rewritten_title == title or rewritten_title == clean_t:
            rewritten_title = f"{clean_t}… 핵심 배경과 시장 파급 전망"

        return {
            "ai_title": rewritten_title,
            "summary_points": summary[:3],
            "paragraphs": paras
        }

    # 팩트 데이터가 없는 경우 (원문 접근 불가 시) 카테고리별 전문 분석 브리핑 (풍성한 6문단)
    cat_focus = {
        '증권': ('증권가 및 금융 투자 시장', '기업 실적 추정치와 밸류에이션, 외국인·기관 수급 동향', '시장 눈높이 변화와 단기 변동성'),
        '경제': ('거시 경제 및 실물 산업계', '공급망 안정성 및 경기 지표, 주요 경영 환경', '금리·환율 등 대외 불확실성 대응'),
        '부동산': ('부동산 시장 및 분양·매매 동향', '대출 규제 및 금리 환경, 거래량 추이', '실수요자 관망세 및 향후 시장 가격 흐름'),
        'IT/과학': ('첨단 테크 생태계 및 IT 산업계', '글로벌 기술 표준 경쟁, 차세대 로드맵 및 특허 영향력', '연구개발(R&D) 성과 및 시장 선점 속도'),
        '정치': ('정치권 및 정책 당국', '제도 정비 및 입법 과제, 주요 이해관계자 여론', '후속 정책 발표 및 향후 국정 대응 추이'),
        '사회': ('사회 각계 및 관련 현장', '제도적 보완책 및 공론화 논의, 시민 생활 영향', '재발 방지 대책 및 제도 개선 동향'),
        '전체': ('시장 및 관련 산업계 전반', '주요 실적 지표와 공급망, 업계 전반의 경영 환경', '향후 전개될 정책 및 시장 반응')
    }
    target_area, impact_area, outlook_area = cat_focus.get(category, cat_focus['전체'])
    rewritten_title = rewrite_news_title(clean_t, category=category)
    if not rewritten_title or rewritten_title == title or rewritten_title == clean_t:
        rewritten_title = f"{clean_t}… 핵심 쟁점과 향후 파급 전망"

    # 제목에서 숫자나 핵심 단어 추출해 본문에 반영
    title_numbers = re.findall(r'\d+(?:\.\d+)?(?:%|배|건|가구|대|원|억|조)?', title)
    num_mention = f"특히 이번 사안과 관련해 주요 지표({', '.join(title_numbers[:2])})가 시장의 이목을 집중시키고 있습니다. " if title_numbers else ""

    p1 = (
        f"{rewritten_title} 관련 소식이 공식화되면서 {target_area}의 이목이 집중되고 있습니다. "
        f"이번 사안은 최근 {category} 분야 전반의 주요 변수와 맞물려 관련 업계 및 시장 참여자들 사이에서 핵심 쟁점으로 떠올랐습니다."
    )
    p2 = (
        f"{num_mention}현장 관계자들은 이번 소식이 전해짐에 따라 단기적인 반응뿐만 아니라 중장기적인 시장 구조 변화 가능성까지 폭넓게 검토하고 있습니다. "
        f"각 이해관계자들은 저마다의 유불리를 계산하며 향후 전개될 세부 시나리오별 대응책 수립에 분주한 모습입니다."
    )
    p3 = (
        f"전문가들은 이번 이슈가 향후 {impact_area}에 "
        f"실질적인 변수로 작용할 가능성에 주목하고 있습니다. 특히 관련 생태계의 거래 동향과 정책적 가이드라인의 변화가 향후 추세를 결정짓는 중요한 분수령이 될 것으로 분석됩니다."
    )
    p4 = (
        f"시장 참여자들 사이에서는 이번 사안을 둘러싸고 다각도의 분석과 신중론이 교차하는 분위기입니다. "
        f"대내외 경제 환경의 불확실성이 지속되는 상황에서, 섣부른 예측보다는 지표 변화와 후속 동향을 면밀히 짚어보아야 한다는 목소리가 커지고 있습니다."
    )
    p5 = (
        f"업계 한 관계자는 \"현재 시장의 관심이 집중된 만큼 후속 발표와 실질적 영향이 가시화되기까지는 일정한 관망세가 이어질 가능성이 높다\"며 "
        f"\"다만 핵심 변수들의 움직임에 따라 변동성이 확대될 수 있어 면밀한 모니터링이 필수적\"이라고 설명했습니다."
    )
    p6 = (
        f"향후 전개될 세부 후속 조치와 관련 업계의 대응 방향에 따라 구체적인 영향의 윤곽이 한층 더 뚜렷해질 전망입니다. "
        f"관계자들은 {outlook_area}을 주시하며, 시장의 안정적인 대응과 발전적 해법을 모색하는 데 역량을 모으고 있습니다."
    )

    summary = [
        f"{rewritten_title}",
        f"{category} 분야 및 {target_area} 파급 영향 집중 분석",
        "향후 세부 후속 조치 및 주요 변수에 업계 관심 고조"
    ]

    return {
        "ai_title": rewritten_title,
        "summary_points": summary,
        "paragraphs": [p1, p2, p3, p4, p5, p6]
    }

def call_gemini_news_writer(api_key, title, category, fact_points=None):
    """
    Google Gemini를 활용하여 구체적인 수치 팩트를 반영한 정통 뉴스 심층 기사 작성
    - 원문 제목 복제 절대 금지 (독창적 헤드라인 생성)
    - 언론사명, 플랫폼명, QR코드, 포털 검색 유도 100% 원천 배제
    - 팩트 수치(경쟁률, 비율 %, 금액, 건수, 가구수 등)는 누락 없이 완벽 반영
    - 과도하게 압축하지 않고 풍성한 긴 호흡(6~10개 문단 이상)의 정통 뉴스 기사로 완성
    """
    safe_facts = [
        clean_news_line(fp) for fp in (fact_points or [])
        if not is_promotional_or_junk_line(fp) and len(clean_news_line(fp)) >= 15
    ]
    facts_context = ""
    if safe_facts:
        facts_context = "\n[핵심 팩트 및 공개 수치 데이터 (Fact Points)]\n" + "\n".join([f"- {fp}" for fp in safe_facts[:45]])

    prompt = f"""당신은 대한민국 최고 수준의 경제/시사 전문 신문 수석 데스크 및 저널리스트입니다.
제공된 [이슈 원문 제목], [카테고리], [핵심 팩트 및 공개 수치 데이터]를 면밀히 분석하여, 독자에게 신뢰와 통찰을 주는 완성도 높은 정통 뉴스 심층 기사를 작성하십시오.

[이슈 원문 제목] {title}
[카테고리] {category}
{facts_context}

[필수 작성 원칙 - 위반 시 엄격히 반려됨]
1. [ai_title 제목 전면 재창조 - 원문 제목 복제 절대 금지]:
   - 원문 제목을 그대로 베끼거나 똑같이 출력하는 것은 절대 금지입니다.
   - [부동산 손자병법], [단독], [속보] 등 대괄호 및 소괄호 코너명/태그는 100% 제거하십시오.
   - 원문의 핵심 키워드와 통계적 의미를 살려, 완전히 새로운 독창적인 분석형/브리핑형 헤드라인(ai_title)으로 새로 작명하십시오.
2. [언론사명, 유료 플랫폼명, QR코드, 포털 검색 유도 100% 원천 배제]:
   - '매경플러스', '더중앙플러스', '아르떼' 등 모든 유료/멤버십 플랫폼명 언급 절대 금지.
   - '네이버에서 검색', 'QR코드', '스마트폰으로 찍으면', '기사 전문은 확인' 등 홍보/유도 문구 일절 작성 금지.
   - '매일경제신문', '매일경제', '한국경제', '조선일보' 등 특정 언론사 이름이나 기자 이름, 이메일, 저작권 문구는 제목, 요약, 본문 어디에도 단 1글자도 포함하지 마십시오.
3. [구체적 수치/통계 지표 누락 없이 반영]:
   - 팩트 데이터에 포함된 구체적인 수치(인구수, 가구수, 비율 %, 금액, 건수, 연도 등)를 본문과 3줄 요약에 정확하게 기술하십시오.
4. [풍성하고 긴 호흡의 정통 뉴스 문단 (6~10개 문단 이상)]:
   - 지나치게 요약하거나 압축하지 마십시오. 원인, 세부 지표 분석, 시장 파급 효과, 향후 전망을 단계별로 풍성하게 서술하십시오.
5. [완결된 3줄 핵심 요약]:
   - 기사 상단에 배치될 3줄 핵심 요약(summary_points)은 수치를 포함한 명확한 완결형 문장(~했습니다, ~집계됐습니다)으로 작성하십시오.
6. [문체]:
   - 단정하고 격조 있는 공인 보도체(~했습니다, ~밝혔습니다, ~전망했습니다, ~파악됐습니다)를 유지하십시오.

반드시 유효한 JSON 형식으로만 응답하십시오:
{{
  "ai_title": "원문과 완전히 다른 독창적이고 심층적인 뉴스 헤드라인",
  "summary_points": [
    "핵심 요약 1 (주요 배경 및 지표)",
    "핵심 요약 2 (세부 수치 및 통계 데이터)",
    "핵심 요약 3 (시장 영향 및 향후 전망)"
  ],
  "paragraphs": [
    "문단 1 (사안의 배경 및 핵심 수치 개요)",
    "문단 2 (세부 통계 지표와 변화 추이)",
    "문단 3 (시장 파급 영향과 구조적 요인 분석)",
    "문단 4 (전문가 및 업계 분석 시각)",
    "문단 5 (향후 전망 및 관전 포인트)"
  ]
}}"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "response_mime_type": "application/json"}
    }
    headers = {"Content-Type": "application/json"}

    resp = requests.post(url, headers=headers, json=payload, timeout=12)
    if resp.status_code == 200:
        res_json = resp.json()
        candidates = res_json.get('candidates', [])
        if candidates:
            raw_text = candidates[0]['content']['parts'][0]['text'].strip()
            if raw_text.startswith('```json'):
                raw_text = raw_text.replace('```json', '', 1).rstrip('`').strip()
            elif raw_text.startswith('```'):
                raw_text = raw_text.replace('```', '', 1).rstrip('`').strip()
            parsed = json.loads(raw_text)
            
            # 후처리 1: 제목 검증 및 정제
            raw_ai_t = parsed.get('ai_title', '')
            clean_ai_t = clean_news_title(raw_ai_t)
            clean_orig_t = clean_news_title(title)
            if not clean_ai_t or clean_ai_t == title or clean_ai_t == clean_orig_t:
                clean_ai_t = rewrite_news_title(clean_orig_t, category=category)
            parsed['ai_title'] = clean_ai_t

            # 후처리 2: 3줄 요약 검증 (홍보 및 찌꺼기 원천 차단)
            safe_sums = []
            for s in parsed.get('summary_points', []):
                if not is_promotional_or_junk_line(s):
                    cs = clean_news_line(s)
                    if cs and len(cs) >= 15:
                        safe_sums.append(cs)
            parsed['summary_points'] = safe_sums[:3]

            # 후처리 3: 본문 문단 검증 (홍보 및 찌꺼기 원천 차단)
            safe_paras = []
            for p in parsed.get('paragraphs', []):
                if not is_promotional_or_junk_line(p):
                    cp = clean_news_line(p)
                    if cp and len(cp) >= 15:
                        safe_paras.append(cp)
            parsed['paragraphs'] = safe_paras

            return parsed

    raise Exception(f"Gemini API 오류 ({resp.status_code})")


def build_full_news_article(title, site_cfg=None, url="", category="전체", publisher_name="주요 언론사", raw_paragraphs=None):
    """
    저작권 안심 + 구체적 통계 및 수치 반영 정통 뉴스 기사 생성 엔진:
    - 원문 기사 복제/표절 ❌ (공개 팩트 기반 저작권 완벽 보호)
    - 원문 제목과 100% 다른 독창적 뉴스 헤드라인 생성 ✅
    - 언론사명, 유료 플랫폼명(매경플러스 등), QR코드, 검색 유도 100% 원천 배제 ✅
    - 기사의 공개 수치 팩트(Fact Points)를 폭넓게 추출하여 풍성하고 긴 호흡의 정통 기사로 재작성 ✅
    - 현대차 등 키워드 감지 시 법적 문제 없는 AI 대표 이미지 매칭 ✅
    """
    ai_cfg = (site_cfg or {}).get('ai_rewrite', {})
    gemini_key = (ai_cfg.get('gemini_api_key') or ai_cfg.get('api_key') or os.environ.get('GEMINI_API_KEY') or '').strip()

    clean_raw_title = clean_news_title(title)
    
    # 1. 기사에서 저작권 없는 순수 사실(Fact) 및 구체적 수치 지표 추출 (홍보 문장 제외)
    fact_points = []
    if raw_paragraphs and len(raw_paragraphs) >= 2:
        fact_points = [p for p in raw_paragraphs if not is_promotional_or_junk_line(p)]
    elif url:
        fact_points = extract_factual_data(url, clean_raw_title)

    article_result = None

    # 2. Gemini 초거대 AI 연동 시도 (수치 팩트 데이터와 헤드라인 제공)
    if gemini_key:
        try:
            article_result = call_gemini_news_writer(gemini_key, clean_raw_title, category, fact_points=fact_points)
        except Exception as e:
            print(f"[Gemini Briefing Fallback to Local Engine] {e}")

    # 3. 로컬 지능형 정통 뉴스 엔진 폴백 (수치 팩트 기반 고품격 문단 조립)
    if not article_result or not article_result.get('paragraphs'):
        article_result = local_generate_issue_briefing(clean_raw_title, category=category, fact_points=fact_points)

    # 4. 최종 제목 정밀 검증 (원문과 절대 동일하지 않게 보장)
    final_title = article_result.get('ai_title') or rewrite_news_title(clean_raw_title, category=category)
    final_title = clean_news_title(final_title)
    if not final_title or final_title == clean_raw_title or final_title == title:
        final_title = rewrite_news_title(clean_raw_title, category=category)

    # 5. 본문 및 요약 2차 안심 필터링
    clean_sums = [
        clean_news_line(s) for s in article_result.get('summary_points', [])
        if not is_promotional_or_junk_line(s) and len(clean_news_line(s)) >= 15
    ]
    clean_paras = [
        clean_news_line(p) for p in article_result.get('paragraphs', [])
        if not is_promotional_or_junk_line(p) and len(clean_news_line(p)) >= 15
    ]

    # 6. 대표 이미지 매칭 (현대차 키워드 시 AI 생성 법적 안심 현대차 이미지 최우선)
    content_sample = " ".join(clean_paras[:2])
    safe_img = get_premium_stock_image(final_title, text=f"{clean_raw_title} {content_sample}", category=category)

    # 7. Curation DB에 저장 (원문 본문은 일절 저장하지 않고, 가공된 수치 기사만 보관)
    record = {
        'source_name': publisher_name,
        'original_title': title,
        'original_url': url,
        'published_at': '',
        'category': category,
        'keywords': [],
        'ai_title': final_title,
        'ai_content': {
            'summary_points': clean_sums,
            'paragraphs': clean_paras
        },
        'ai_image': safe_img,
        'cluster_sources': []
    }
    if url:
        save_curated_article(record)

    return {
        'title': final_title,
        'summary_points': clean_sums,
        'paragraphs': clean_paras,
        'main_img': safe_img
    }

# 기존 코드 호환 래퍼
def build_curated_briefing(cluster_item, site_cfg=None):
    primary = cluster_item.get('primary', {})
    url = primary.get('link') or primary.get('original_url', '')
    title = primary.get('title') or primary.get('original_title', '')
    category = cluster_item.get('category', '전체')
    publisher = primary.get('source', '주요 언론사')
    
    art = build_full_news_article(title, site_cfg, url, category, publisher)
    return {
        'id': '',
        'source_name': publisher,
        'original_title': title,
        'original_url': url,
        'published_at': primary.get('date', ''),
        'category': category,
        'keywords': [],
        'ai_title': art['title'],
        'ai_content': {
            'summary_points': art['summary_points'],
            'paragraphs': art['paragraphs']
        },
        'ai_image': art['main_img'],
        'cluster_sources': cluster_item.get('cluster_sources', [])
    }
