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
└── server.js                         # 로컬 dev 서버 (필요 시 node server.js)
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

## 다음으로 남은 작업

### generateReading 프롬프트 업데이트
현재 프롬프트는 구 방식. `interpretation_methodology_guide.md`의 구조로 재작성 필요:
- 다산역 4원리 (추이·호체·물상·효변) 계산 결과를 프롬프트에 주입
- 육효점 계산 로직 구현 (납갑·세효·응효·육친·육수·생극·형충·공망)
- 7단계 리포트 구조 적용

### 다산역 자동 계산
- 추이: 12벽괘 매핑 테이블
- 호체: 2·3·4효, 3·4·5효 → GUA 룩업 재사용 가능
- 물상: TRIG_MAP의 nat 필드 활용
- 효변: 변효 위치(0-5) → 고정 의미 텍스트 매핑

### 육효점 계산 로직 (신규 구현)
- 60갑자 날짜 변환
- 64괘 8궁 배속표
- 각 효 납갑 간지 배당 (64×6)
- 세효·응효 위치표, 육친·육수 배당, 생극·형충파해합·공망 함수

---

## 데이터 재생성 시

`E:/Users/g8428/AppData/Local/Temp/claude/e--Users-g8428-experiment/d16902d1-cc46-4306-bb1a-753a6f03992e/scratchpad/`에 생성 스크립트 있음:
- `gen_detail.mjs` — hy_detail + p_ji 생성 (Haiku API, 8괘/배치, max_tokens=12000)
- `gd2_detail.js` — 최종 병합본
- `inject_polite2.mjs` — 존댓말 변환본 주입 (라인 기반)

API 키: `ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY "E:/Users/g8428/experiment/.env" | cut -d= -f2) node script.mjs`
