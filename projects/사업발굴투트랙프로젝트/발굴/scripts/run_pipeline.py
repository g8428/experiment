#!/usr/bin/env python3
"""
사업발굴 자동화 통합 실행기
- wtp_miner + sourcing_1688을 한 번에 실행
- Track B 기회 카드의 "미확인 사항" 검증용

사용법:
    python run_pipeline.py "미니 속옷세탁기" "迷你洗衣机 内衣"
    python run_pipeline.py --help
"""

import sys
import argparse
from pathlib import Path

# 같은 디렉터리의 스크립트 임포트
sys.path.insert(0, str(Path(__file__).parent))
import wtp_miner
import sourcing_1688


def run_full_pipeline(
    kr_keyword: str,
    cn_keyword: str = None,
    max_wtp: int = 15,
    max_sourcing: int = 10,
):
    print(f"\n{'='*60}")
    print(f"🚀 사업발굴 자동화 파이프라인 시작")
    print(f"   한국어 키워드: {kr_keyword}")
    print(f"   중국어 키워드: {cn_keyword or '(자동 추정)'}")
    print(f"{'='*60}")

    # 1단계: WTP 마이닝
    print(f"\n📌 [1/2] Track A WTP 마이닝...")
    wtp_result = wtp_miner.run(kr_keyword, max_results=max_wtp)

    # 2단계: 1688 소싱 확인
    print(f"\n📌 [2/2] 1688 소싱 확인...")
    if not cn_keyword:
        cn_keyword = sourcing_1688.suggest_chinese_keyword(kr_keyword)
    sourcing_result = sourcing_1688.run(cn_keyword, kr_keyword=kr_keyword, max_results=max_sourcing)

    # 최종 요약
    print(f"\n{'='*60}")
    print(f"✅ 파이프라인 완료: {kr_keyword}")
    print(f"{'='*60}")
    print(f"WTP 신호: {wtp_result.get('wtp_count', 0)}개 (금액 언급: {wtp_result.get('price_count', 0)}개)")

    p = sourcing_result.get("price_range_krw", {})
    if p.get("min"):
        print(f"소싱 단가: ₩{p['min']:,} ~ ₩{p['max']:,} (1688 기준)")
    else:
        print(f"소싱 단가: 직접 확인 필요")

    moq = sourcing_result.get("moq_samples", [])
    leads = sourcing_result.get("lead_time_samples", [])
    print(f"MOQ: {', '.join(moq) if moq else '미확인'}")
    print(f"리드타임: {', '.join(leads) if leads else '미확인'}")

    # Go/Stop 1차 판정
    wtp_ok = wtp_result.get("wtp_count", 0) >= 5
    price_ok = wtp_result.get("price_count", 0) >= 2
    sourcing_ok = p.get("max") is not None and p["max"] < 30000  # 3만원 미만 단가

    print(f"\n📊 1차 자동 판정:")
    print(f"  WTP 원문 5개 이상: {'✅' if wtp_ok else '❌'} ({wtp_result.get('wtp_count',0)}개)")
    print(f"  금액 언급 2개 이상: {'✅' if price_ok else '❌'} ({wtp_result.get('price_count',0)}개)")
    print(f"  단가 3만원 미만: {'✅' if sourcing_ok else '❌/미확인'}")

    if wtp_ok and price_ok:
        print(f"\n  → 🟢 GO 검토 — WTP 충분, 소싱 단가 확인 후 결정")
    elif wtp_result.get("wtp_count", 0) >= 2:
        print(f"\n  → 🟡 PIVOT 검토 — WTP 약하거나 소싱 불확실")
    else:
        print(f"\n  → 🔴 STOP 또는 추가 조사 — WTP 신호 부족")

    print(f"\n📁 결과 파일:")
    if wtp_result.get("card_path"):
        print(f"  Track A 기회 카드: {wtp_result['card_path']}")
    if sourcing_result.get("saved_to"):
        print(f"  소싱 데이터: {sourcing_result['saved_to']}")

    return {"wtp": wtp_result, "sourcing": sourcing_result}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="사업발굴 자동화 통합 파이프라인")
    parser.add_argument("kr_keyword", help="한국어 키워드 (예: '미니 속옷세탁기')")
    parser.add_argument("cn_keyword", nargs="?", default=None, help="중국어 키워드 (옵션, 없으면 자동 추정)")
    parser.add_argument("--max-wtp", type=int, default=15, help="WTP 검색 결과 수")
    parser.add_argument("--max-sourcing", type=int, default=10, help="소싱 검색 결과 수")
    args = parser.parse_args()

    run_full_pipeline(args.kr_keyword, args.cn_keyword, args.max_wtp, args.max_sourcing)
