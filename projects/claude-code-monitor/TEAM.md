# 3팀 콘텐츠 — TEAM.md

> 팀장 세션이 가장 먼저 읽는 문서. 다음으로 `CLAUDE.md`를 읽는다.

## 팀 구성

| 자리 | 누가 | 모델 |
|---|---|---|
| 팀장 | `team-lead` 세션 | Sonnet 5.5 |
| 블로그 작성 | `content-blog-writer` (팀 전용) | Sonnet 5.5 |
| 인스타 작성 | `content-instagram-writer` (팀 전용) | Sonnet 5.5 |
| 조사 | `researcher` | Sonnet 5.5 |
| 구현 (수집·발송 스크립트) | `engineer` | Sonnet 5.5 |
| 리뷰 | `reviewer` | Opus 5.5 |
| 작은 일 | `quick-worker` | Haiku 5.5 |

## 담당 범위

- 폴더: `projects/claude-code-monitor/`, `content/`, `research/`
- 수집: `monitor.py`(Claude Code 트렌드), `news_collect.py`(AI 뉴스 RSS), 카드 렌더 `cards/`, 게시 `ig_publish.py`
- 워크플로: `.github/workflows/claude-code-monitor.yml`, `.github/workflows/claude-code-ig-publish.yml`
  - 이 파일들은 공용 폴더에 있다. 수정할 때는 메인 코디네이터에게 알린다.

## 검증

```bash
python projects/claude-code-monitor/monitor.py           # research/claude-code-trends-YYYY-MM-DD.md 생성 확인
```

- 원고는 출처 링크가 있는지, 지난 주 원고와 겹치지 않는지 본다 (`history.json`).

## 출시

- 매주 월요일 09:00 KST에 GitHub Actions가 자동 실행한다. 실행되면 #성과보고에 요약이 올라가고, 원고는 그 스레드에 달린다.
- 블로그는 재영이 직접 올린다 (자동 게시 없음).
- 인스타: Slack 미리보기에 오너가 ✅를 달면 자동 게시. ✅ 없으면 게시하지 않는다. (`claude-code-ig-publish.yml`이 월·화 매시 확인)
- 인스타 카드는 AI 뉴스 전반(`research/ai-news-*.md`)이 주제, 블로그는 Claude Code 트렌드 리서치가 입력이다.

## 팀 고유 금지 사항

- 원고 본문을 GitHub에 공개 커밋하는 것. 본문은 Slack 스레드로만 보낸다.
- 승인 전 이미지 커밋 금지 (`ig-media` 브랜치는 승인 후에만).
- 언론사 기사 사진 사용 금지 (공식 발표 og:image, CC/퍼블릭 도메인 위키미디어, AI 생성만).
- 출처 없는 수치나 단정적 표현

## 현재 상태

- 2026-11-26: 팀 체계 도입. 주간 자동 실행 중.
