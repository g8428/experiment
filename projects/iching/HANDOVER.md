# 주역 앱 HANDOVER

## 앱 개요

`index.html` 단일 파일 앱. 서버 없음, 빌드 없음.  
브라우저에서 직접 열면 동작한다.

기능 두 가지:
- **프리뷰(buildLocalCards)**: 완전 정적. API 없이 GD/GD2 데이터만으로 카드 렌더링.
- **AI 해석(buildReadingHtmlV2 + generateReading)**: Claude API 호출. 유료 기능.

---

## 파일 구조

```
projects/iching/
├── index.html                        # 전체 앱 (3000줄+, 단일 파일)
├── HANDOVER.md                       # 이 파일
├── interpretation_methodology_guide.md  # AI 해석 방법론 (다산역+육효점)
├── local-server.js                   # 로컬 dev 서버 (api/ 핸들러를 동적 import)
├── api/                              # Vercel 서버리스 (reading, questions, auth, billing)
└── lib/prompt-reading-v2.js          # 구버전 프롬프트 빌더 — index.html에서 로드하지 않음(참고용 잔재)
```

스크립트는 `E:/Users/g8428/experiment/.env`에서 `ANTHROPIC_API_KEY` 읽음.

---

## 데이터 구조 (index.html 내부)

### GD 객체 (~line 350)
64괘 기본 데이터. 키 = 괘 번호(1-64).
```javascript
GD[20] = {
  gs: '風地觀, ...',       // 괘상 원문
  k:  '괘사 한 줄',        // 괘사
  dt: '단전 요약',         // 단전
  dst:'대상전 한 줄',      // 대상전
  v:  '형세 한 줄',        // 점사 형세
  hy: ['초효사', '이효사', '삼효사', '사효사', '오효사', '상효사'],  // 6개
  p:  '본괘 해설 (존댓말)'  // 본괘 카드 해설
}
```

### GD2 객체 (~line 417)
GD 보강 데이터. 키 = 괘 번호(1-64). **64괘 전부 완성.**
```javascript
GD2[20] = {
  k2:        '괘사 재번역 (간결)',
  dst2:      '대상전 재번역',
  dt2:       '단전 재번역',
  hy2:       ['초효 간결 번역', ...6개],   // 효사 paraphrase
  hy_detail: ['초효 2-3문장 해설', ...6개], // 존댓말(-습니다)
  p_ji:      '지괘 관점 해석 (존댓말)'      // "이쪽으로 흘러가고 있습니다" 관점
}
```

`hy_detail`: 64×6 = 384개. 각 효의 위치 의미를 반영한 2-3문장.  
`p_ji`: 64개. 지괘가 됐을 때의 관점 해석.  
모두 존댓말(-습니다/-ㅂ니다). 빈 항목 없음.

---

## buildLocalCards 동작 (현재 확정)

함수 위치: ~line 980.  
헬퍼: `_bhy(i)` = hy2 or hy 폴백, `_bhd(i)` = hy_detail, `_jpj` = p_ji.

### 카드 순서

1. **형세 카드** — 뽑힌 괘 + ben.v
2. **본괘 카드** — k2(괘사) + ben.p(해설, 항상 표시) + dst2(대상전)
3. **변효 카드** — 변효 수에 따라 다름 (아래 표)
4. **지괘 카드** — 변효 1개 이상일 때. k2 + p_ji + dst2
5. **점사 카드** — 형세(ben.v) / 활로(ji.k) / 경계(ji.v) 3열 그리드

### 변효 수별 카드 #3 동작

| 변효 수 | 카드 제목 | 표시 내용 |
|--------|----------|----------|
| **0개** | 六位 · 육위 | 始(1-2효) / 中(3-4효) / 終(5-6효) 그룹. 각 효: hy2 + hy_detail |
| **1개** | 변효 · 變爻 (1개) | 해당 효: hy2 + hy_detail |
| **2개** | 변효 · 變爻 (2개) | 위효(중심): hy2 + hy_detail / 아래효(보조): hy2만 |
| **3개** | 변효 · 變爻 (3개) | 모든 변효: hy2 + hy_detail |
| **4개** | 변하지 않는 자리가 중심 | **불변효 2개**: hy2 + hy_detail (변효는 표시 안 함) |
| **5개** | 변하지 않는 자리가 중심 | **불변효 1개**: hy2 + hy_detail |
| **6개** | 완전한 전환 | 용구/용육 고정 메시지. hy_detail 없음. |

### hy2 vs hy_detail 역할

- `hy2` (gray, --muted): 효사 원문의 간결한 번역. 고어체 유지.
- `hy_detail` (white, --text): 그 효의 위치 의미를 녹인 2-3문장 해설. 존댓말.

---

## 효 위치별 의미 (hy_detail 생성 기준)

| 효 | 의미 |
|----|------|
| 초효 | 씨앗·시작 — 아직 드러나지 않은 가능성 |
| 이효 | 내부 안정·판단 — 내면의 중심 |
| 삼효 | 경계·전환 — 내외 접점, 진퇴 기로 |
| 사효 | 외부 진입 — 더 큰 무대로 나아가는 관문 |
| 오효 | 군위·중심 — 절정, 안정적 권위 |
| 상효 | 완성·마무리 — 극에 달해 내려오기 시작 |

---

## 주요 함수 위치 (index.html)

| 함수 | 위치 | 역할 |
|------|------|------|
| `buildLocalCards` | ~980 | 프리뷰 카드 렌더링 (정적) |
| `buildReadingHtmlV2` | ~820 | AI 해석 결과 렌더링 |
| `generateReading` | ~730 | Claude API 호출 및 스트리밍 |
| `lookupGua` | ~514 | 음양 배열 → 괘 객체 반환 |
| `calcGuas` | ~517 | 본괘/지괘/변효 계산 |
| `GD` | ~350 | 64괘 기본 데이터 |
| `GD2` | ~417 | 64괘 보강 데이터 (hy_detail/p_ji 포함) |

---

## AI 해석 호출 구조 (2026-09-28 재설계)

다산역(`calcDasanYeok`)·육효점(`buildLiuYaoData`) 계산과 7섹션 리포트는 이미 구현돼 있다(위 "남은 작업"은 완료됨). 2026-09-28에 **출력 일관성** 문제(존댓말/반말 오락가락, 섹션 누락, JSON이 코드블록에 감싸짐, 변효 4개 오독)를 고치며 호출 구조를 바꿨다.

### 왜 바꿨나 — 예전 방식의 문제
- 규칙·데이터·JSON 스키마를 전부 **user 메시지 하나**에 넣고 "JSON만 출력해"라고 부탁 → `system` 미사용, `temperature` 미지정(기본 1.0), 출력 강제 장치 없음.
- `max_tokens=5000`에 `stop_reason`을 안 봐서 잘린 응답은 JSON 파싱 실패 → 재시도 → 운에 따라 결과가 달라짐.
- 변효 개수별 원칙(`readingFocus`)이 3개와 4개를 한 분기로 묶은 채, 섹션4 지침은 개수와 무관하게 "변효 효사를 인용하라" → 변효 4개일 때 모순. 무료판(`buildLocalCards`)은 4~5개면 **불변효** 중심인데 유료판엔 그 규칙이 없었음.

### 노드 그래프로 전환 (2026-10-05)
**왜**: 7섹션을 한 번의 호출로 쓰면 괘 데이터·고민·문답·전 섹션 규칙을 한 맥락에 다 들고 가서 놓치는 게 많았고, 어느 단계에서 틀렸는지 볼 수 없었다. → 노드마다 역할과 JSON 출력 스키마를 정하고, **각 노드는 앞 노드 JSON 중 필요한 필드만** 받는다. Langfuse에 노드별 generation이 남는다.

```
analyze_hexagram ─▶ plan_reading ─┬▶ write_open  물으신 것에 대한 답 · 지금의 형세(본괘)
(괘 데이터만)        (편집장 구성안)  ├▶ write_core  이 점의 심장(중심 효) · 흘러가는 곳(지괘) · 할 것/피할 것
                                   └▶ write_tail  때(타임라인) · 남겨 주신 답에(질문별) · 마무리
                                            ▼ assemble(코드) → 리포트 객체(version 2) → index.html buildReport()
```

| 위치 | 역할 |
|---|---|
| `index.html` `window.buildReadingInput(ben,ji,state)` | 재료만 만든다: `hexagram`(괘사/대상전/변효·불변효 효사/다산역/육효 응기 텍스트 — 고민·문답 없음), `heartRule`, `name`, `today`, `question`, `qa[]`, `meta` |
| `index.html` `generateReading` / `parseReadingResponse` / `buildReport` | 재료를 `/api/reading`에 POST, 응답 `reading`(version 2 객체)을 `buildReport`가 리포트 화면으로 그린다 |
| `api/_lib/reading-graph.js` | 노드 정의(프롬프트·`tool_use` 스키마·temperature·timeout)와 실행기. **프롬프트 규칙은 이제 여기서 고친다** |
| `api/reading.js` | 그래프 실행 + Langfuse 루트(`agent` 타입 `iching-reading`) |
| `lib/langfuse.js` | NodeSDK + LangfuseSpanProcessor 초기화(`ensureTracing`/`flushTraces`), 단일 호출용 `traceAnthropicCall`(questions.js) |

- 쓰기 노드 3개는 병렬. `api/reading.js`만 `vercel.json` maxDuration 120초(Hobby + Fluid compute 한도 300초), 그래프 전체 예산 100초. 노드별 시도 timeout으로 끊고 재시도한다 — 한 호출만 30초 넘게 멈춘 사례가 트레이스로 확인됨.
- **비용·시간 측정(2026-10-06, 같은 괘 2종 × 2회)**: 예전 단일 호출 20.6초·$0.0165·본문 1,741자 / 첫 그래프(쓰기 노드 5개) 27.5초·$0.042 / 현재(쓰기 3개) 21.3초·$0.028·본문 1,275자. 쓰기 노드마다 붙는 고정 규칙·도구 안내(노드당 ~1,700토큰)가 입력의 절반이었다 → 노드 수 줄이고 공통 규칙(STYLE) 압축, 분석·연결 메모는 필드당 한 문장, JSON 들여쓰기 제거. **STYLE은 쓰기 노드마다 반복되니 늘리지 말 것.**
- **품질 회귀와 복구(2026-10-06)**: 쓰기 노드에 분석 메모만 넘겼더니 괘 이름·효 위치가 풀이에서 사라졌다(같은 괘 비교: 괘 이름 언급 단일 호출 4.3회 → 메모만 0회). 지금은 클라이언트가 `src`(본괘·지괘 원문 블록 — 상괘/하괘 상징, 괘사·대상전 한자 원문 포함, 중심 효 효사·자리 풀이, 해석 원칙, 호체, 추이, 응기)를 따로 보내고, 쓰기 노드마다 자기 섹션에 필요한 조각을 직접 받는다. 측정: 31초·$0.042, 본문 2,176자, 괘 이름 7.3회·자연 상징 19회(단일 호출 20.6초·$0.0165·1,747자·4.3회·10회). **메모만으로 쓰게 되돌리지 말 것.**
- **한자 금지(2026-10-13)**: 작가 출력에 한자·지지(酉月 등)·없는 효사 원문 조작이 다시 섞였다. 원인은 ① 심장 노드가 받는 `heartRule`에 "효사의 한자 원문을 인용"이 남아 있었고 ② 작가용 원문 조각에 한자(괘사·대상전 원문, 감(坎), 지지)를 넣었기 때문. 지금은 클라이언트 `ko()`가 작가용 조각에서 한자를 걷어내고(자연 상징은 NAT_KO로 한글화), STYLE이 한자·지지 한글 읽기(술월·자일)까지 금지하며, 쓰기 노드 결과에 한자가 있으면 한글로 다시 쓰게 한다(`HANJA` 검사, 끝까지 남으면 `stripHanja`). 분석 노드만 응기 블록의 지지 한자를 본다. **원문 한자를 보여 주고 싶으면 작가에게 넘기지 말고 화면 카드에서 따로 붙일 것.**
- 노드 실패 시 그 노드만 최대 3회 재시도(429/5xx/timeout/필드 누락/max_tokens). 시도마다 generation이 하나씩, 실패는 `ERROR`로 남는다.
- **효사 한자 원문은 데이터에 없다**(GD.hy·GD2.hy2 모두 국문 의역). 예전 단일 호출은 "한자 원문 인용" 규칙 때문에 원문을 지어냈다 → 노드 프롬프트에 "주어진 문구 그대로, 한자를 만들지 않음"이 `heartRule`의 "한자 원문" 표현보다 우선한다고 명시. 진짜 원문을 넣으려면 GD에 효사 원문 필드를 추가해야 한다.
- 화면의 효사 표시(1단계 `buildLocalCards`, 2단계 원전 카드·심장 의미, 괘 아래 요약)는 `focusYao(chg)` 하나로 정한다: 변효 1~3개 → 변효, 4~5개 → 불변효, 0·6개 → 개별 효 없음. 예전엔 원전 카드가 개수와 무관하게 변효를 보여줘서 4~5개일 때 풀이(불변효)와 어긋났다.
- 리포트 객체의 필드(`headline, summary, verdict, empathy, answer, shape, heart, flow, dos, donts, season, timeline, qa, closing, bubbles`)는 서버 `assemble()`과 클라이언트 `buildReport()`가 함께 바뀌어야 한다. `version`을 올리면 `parseReadingResponse`도.
- Langfuse 키: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL`. 없으면 트레이싱만 꺼지고 점사는 동작한다. 트레이스 조회는 `npx langfuse-cli api observations list --trace-id <id>` (v4에서 legacy traces API는 막힘).
- `.vercelignore`에서 `package.json`을 뺐다 — 들어 있으면 Vercel이 npm 패키지를 설치하지 않아 `@langfuse/*` import가 실패한다.

### 리포트 재구성 — 화자 연서 (2026-10-17)
**왜**: 유료 사주 리포트(청월당·포스텔러·헬로우봇·크몽 PDF·Co–Star·The Pattern)를 조사해 보니 공통점이 ① 결론 먼저 ② 분명한 판정 ③ 섹션마다 다른 역할, 반복·모순 없음 ④ 훑어볼 구조(요약 카드·목록·타임라인) ⑤ 질문별 답 ⑥ 용어 풀이 ⑦ 공감 한 문장. 이전 풀이는 같은 효사 인용이 5개 섹션에 반복되고, 결론이 없고, 상담자가 말하지 않은 사정을 지어내고, 섹션끼리 계절이 어긋났다. 원인은 작가들이 같은 원문을 받아 서로 모른 채 병렬로 썼기 때문.
- **구성안 노드(plan_reading)**: 판정(go/wait/conditional/no/general)·한 줄·이유·키워드·국면(season)·상담자 사실(facts)·섹션별 메시지(point_*)·인용 배정(quote_*)·말풍선(bubble_*)·표정(mood)을 한 번 정하고, 작가는 이 기준과 자기 섹션 원문만 받는다. 출력은 **평평한 필드**로 받고 `nestPlan()`이 묶는다 — 중첩 객체로 받으면 Haiku가 객체째 빼먹었다.
- **화자 연서**: 30대 초반 역술가, 해요체 기본·무게 있는 판단만 하십시오체, "이름+님". 화면은 `narratorSay()` 말풍선. **일러스트**는 `assets/narrator/{default,smile,serious,warm}.webp`(투명 배경 512×512 + 128 아바타, 금색·먹색 화면에 맞는 차분한 동양풍)를 넣고 `index.html`의 `NARRATOR.art`를 `'assets/narrator/'`로 바꾸면 된다. 그 전에는 이름 인장.
- **문체 검사**(`checkStyle` 노드): 기계적으로 고칠 수 있는 건 바로 고친다 — "당신"→"이름+님", 명령형 "~세요/~십시오/~해야 합니다"→"~는 쪽이 좋아요", 흔한 해라체 끝("~한다/된다/있다/이다…")→해요체, 인용이 배정되지 않은 필드의 따옴표 제거. 고칠 수 없는 것(한자·남은 반말·지지 읽기·육효 용어)만 **노드당 한 번** 다시 쓰게 한다. 재시도를 늘렸을 때 시간만 늘고(평균 51초) 잘 안 고쳐졌다.
- **필드 안정화**: 중첩 필드가 JSON 문자열로 오면 `coerce()`가 풀고, `missingFields()`가 중첩까지 필수 필드를 본다. 분석 노드는 fortune·why만 필수(나머지는 빠져도 리포트가 된다) — 필드 누락 재시도가 시간의 주범이었다.
- **측정(괘 3종 × 2회)**: 6편 모두 완료, 한자·지지 읽기·"당신"·반말·명령형 0, 평균 37.7초·$0.050. 같은 인용 반복은 핵심 효사 한 줄 정도만 남음.
- 화면 순서: 한눈에 카드(한 줄·키워드·길흉 5단계) → 연서 공감 → 물으신 것에 대한 답(판정·이유) → 본괘 · 지금의 형세 → 변효/불변효 · 이 점의 심장(중심 효 강조 작은 괘) → 지괘 · 흘러가는 곳 → 할 것·피할 것 → 때(타임라인) → 남겨 주신 답에(접기) → 마무리 → 처음 보는 말 풀이(접기).

### 이전 구조 (2026-09-28 ~ 10-05, 단일 호출)
`buildReadingSystem`(고정 규칙) + `buildReadingUser`(데이터) + `READING_TOOL`(7섹션 스키마)로 한 번에 생성. 위 그래프로 대체되어 삭제됨. 아래 규칙들은 그래프 노드 프롬프트로 옮겨졌다.

변효 개수별 규칙은 `buildReadingInput` 안의 `readingFocus`/`heartRule`이 **0 / 1 / 2 / 3 / 4~5 / 6** 으로 분기한다(무료판과 동일). 4~5개는 변효 효사를 프롬프트에 아예 넣지 않고 불변효 효사만 준다. `_autoMeaning('이 점괘의 심장')`도 4~5개면 불변효를 원전으로 표시.

### 시기(時期) 계산 (2026-09-28 수정)

**문제였던 것**: 예전 `lyStr`은 "오늘 일진 지지의 충·합·공망 지지 = 발동 달"로 시기를 줬다. 괘가 무엇이든 그날 점친 사람 전원이 같은 달을 받았고(壬寅일이면 누구나 "충=申월=내년 8월"), 시스템 규칙 "앞으로 3~4개월을 달별로"가 겹쳐 "10~11월 대기, 내년 8월 완성" 식 고정 윈도우에 점괘를 맞춰 끼우게 됐다. 피드백으로 발견.

**지금 구조** (`index.html`, `buildLiuYaoData` 아래):
| 함수 | 역할 |
|---|---|
| `getWolGeon(date)` | 절기 기준 월건 지지 (`WOLGEON_START`) |
| `buildDasanTiming(...)` | 다산 추이: 본괘·지괘의 12벽괘 절기 위치(`BYEOK_MONTH`, 비벽괘는 양효 수 → `TUI_PARENT` 모괘 두 개, 61·62는 재윤괘) + 변효 방향(음→양=성장기, 양→음=수렴기) + 효변 단계(`YAO_STAGE`, 변효 ≤3개) |
| `detectYongsin(q)` | 질문 키워드 → 용신 육친 (관귀/부모/처재/자손/형제, 연애는 관귀·처재 둘 다) |
| `buildEunggi(lyData,chg,q,date)` | 육효 응기. 세효·응효·용신·동효(변효 4~5개면 불변효, 6개면 세·응·용신만)의 지지별로 상태(동/정, 왕상휴수, 공망, 월파, 일진 충·합)와 응기 후보(값·합·충·출공)를 실제 달 범위 + 60일 내 가까운 날로 준다 |

`buildReadingInput`의 hexagram 텍스트는 `[추이 — 계절 국면]`과 `[시기 판단 근거 — 육효 응기]` 두 블록을 넣고, analyze_hexagram·write_path 노드 규칙이 "이 두 블록에서만 시기를 가져오라, 근거 없는 달·어림 숫자·N개월 채우기 금지"로 바뀌었다.

원칙은 `interpretation_methodology_guide.md` "시기 판단" 절 참고. **검증 방법**: `buildReadingInput`을 node에서 서로 다른 괘·질문으로 호출해 두 블록이 괘마다 달라지는지 본다(같은 날 모든 괘가 같은 달을 받으면 퇴행).

### 서버 (`api/reading.js`, `api/questions.js`)
`api/reading.js`는 위 노드 그래프 실행기. `api/questions.js`는 Anthropic Messages API 프록시(클라이언트가 보낸 `system / messages / ...`를 그대로 전달, `traceAnthropicCall`로 1회 호출 트레이스). `local-server.js`가 같은 핸들러를 동적 import하므로 로컬/Vercel 동작이 같다(`.env` 값의 따옴표는 벗겨서 읽음).

### 유지 원칙
- 규칙을 바꿀 땐 고정 규칙은 `api/_lib/reading-graph.js`의 해당 노드에, 이번 점사 데이터는 `buildReadingInput`에 넣을 것. 노드를 다시 한 덩어리로 합치지 말 것.
- 섹션을 추가/삭제하면 그래프의 쓰기 노드·`assemble`·양쪽 `READING_TAGS`·`buildReadingHtmlV2`의 `TAG_LABELS`를 같이 바꿀 것.
- `temperature`를 올리면 톤이 다시 흔들린다. 0.3~0.4 유지.

---

## 데이터 재생성 시

`E:/Users/g8428/AppData/Local/Temp/claude/e--Users-g8428-experiment/d16902d1-cc46-4306-bb1a-753a6f03992e/scratchpad/`에 생성 스크립트 있음:
- `gen_detail.mjs` — hy_detail + p_ji 생성 (Haiku API, 8괘/배치, max_tokens=12000)
- `gd2_detail.js` — 최종 병합본
- `inject_polite2.mjs` — 존댓말 변환본 주입 (라인 기반)

API 키: `ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY "E:/Users/g8428/experiment/.env" | cut -d= -f2) node script.mjs`
