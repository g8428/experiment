# Claude Code 트렌드 모니터

## 목적

GitHub에서 Claude Code 관련 인기 오픈소스 리포를 매주 자동 추적하고,
그 결과를 기반으로 블로그/인스타 컨텐츠를 자동 생성하는 파이프라인.

## 파이프라인

```
monitor.py 실행 (주 1회)
  → research/claude-code-trends-YYYY-MM-DD.md 저장
  → content-blog-writer 서브에이전트 호출
      → content/blog/YYYY-MM-DD-*.md 저장
  → content-instagram-writer 서브에이전트 호출
      → content/instagram/YYYY-MM-DD-*.md 저장
  → Slack #성과보고 보고
```

## 실행

```bash
# 수동 실행
python projects/claude-code-monitor/monitor.py

# 환경변수 (선택 — 없어도 동작, rate limit 낮아짐)
GITHUB_TOKEN=ghp_xxx python projects/claude-code-monitor/monitor.py
```

## 파일 구조

```
projects/claude-code-monitor/
  monitor.py          # GitHub API 트렌드 수집
  history.json        # 이전 실행 스타 수 (자동 생성)
  CLAUDE.md           # 이 파일

research/
  claude-code-ecosystem-2026-09-27.md  # 초기 심층 조사
  claude-code-trends-YYYY-MM-DD.md     # 주간 모니터 결과

content/
  blog/
    YYYY-MM-DD-*.md   # 블로그 포스트 초안
  instagram/
    YYYY-MM-DD-*.md   # 인스타 캡션 + 슬라이드 구성
```

## Cowork 스케줄

- 주기: 매주 월요일 오전 9시 (KST)
- 태스크: `python projects/claude-code-monitor/monitor.py` 실행 후
  content-blog-writer, content-instagram-writer 서브에이전트 순차 호출
- 결과: #성과보고 채널에 링크 보고

## 서브에이전트

| 에이전트 | 파일 | 역할 |
|---------|------|------|
| content-blog-writer | `.claude/agents/content-blog-writer.md` | 벨로그/티스토리 블로그 포스트 |
| content-instagram-writer | `.claude/agents/content-instagram-writer.md` | 인스타 카드뉴스 캡션+구성 |

## 참고

- 초기 심층 조사: `research/claude-code-ecosystem-2026-09-27.md`
- GitHub API rate limit: 인증 없이 60 req/h, GITHUB_TOKEN 있으면 5,000 req/h
- 검색 쿼리 수정: `monitor.py`의 `SEARCH_QUERIES` 리스트
