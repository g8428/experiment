"""IG_USER_ID 찾기 도우미: 토큰에 연결된 인스타 프로페셔널 계정의 id·username만 출력한다.

실행: IG_ACCESS_TOKEN=... python projects/claude-code-monitor/ig_whoami.py
(토큰은 출력하지 않는다. IG_GRAPH_VERSION 으로 버전 변경 가능, 기본 v21.0)
"""
from __future__ import annotations

import os
import re
import sys

import requests


def main() -> int:
    token = os.environ.get("IG_ACCESS_TOKEN")
    if not token:
        print("환경변수 IG_ACCESS_TOKEN 이 필요합니다")
        return 2
    ver = os.environ.get("IG_GRAPH_VERSION") or "v21.0"
    r = requests.get(
        f"https://graph.facebook.com/{ver}/me/accounts",
        params={"fields": "name,instagram_business_account{id,username}", "access_token": token},
        timeout=30,
    )
    body = r.json()
    if r.status_code >= 400 or "error" in body:
        msg = body.get("error", {}).get("message", f"HTTP {r.status_code}")
        print("Graph 오류: " + msg.replace(token, "***"))
        return 1
    found = [
        (p.get("name"), p["instagram_business_account"])
        for p in body.get("data", [])
        if p.get("instagram_business_account")
    ]
    if not found:
        print("페이스북 페이지에 인스타 프로페셔널 계정이 연결돼 있어야 함 (연결된 계정을 찾지 못했습니다)")
        return 1
    for page, ig in found:
        print(f"페이지: {page} / IG_USER_ID={ig.get('id')} / username=@{ig.get('username')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
