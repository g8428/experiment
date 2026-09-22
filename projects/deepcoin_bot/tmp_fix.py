import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
with open('daily_review.py', encoding='utf-8') as f:
    content = f.read()

# fix 1: add sys.stdout.reconfigure at top
old_top = '"""'
new_top = '''import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
"""'''

# fix 2: replace emoji chars in print statements
fixes = [
    ('\U0001f4cb', '[*]'),
    ('\U0001f4a1', '[!]'),
    ('\U0001f527', '[fix]'),
    ('✅', '[OK]'),
    ('\U0001f6e0', '[set]'),
    ('\U0001f4cb', '[log]'),
]

for old, new in fixes:
    content = content.replace(old, new)

# fix 3: move save_tuning before print loop
# find the section
old_section = '''    # 4. 결과 출력
    print("\\n[*] 진단:")
    for i, d in enumerate(result.get("diagnosis", []), 1):
        print(f"  {i}. {d}")

    print(f"\\n[!] 패턴 인사이트:\\n  {result.get('pattern_insights', '-')}")

    # 5. 파라미터 저장
    new_tuning = save_tuning(result, current_tuning.get("version", 0))'''

new_section = '''    # 4. 파라미터 먼저 저장 (출력 오류와 무관하게)
    new_tuning = save_tuning(result, current_tuning.get("version", 0))

    # 5. 결과 출력
    print("\\n[결과] 진단:")
    for i, d in enumerate(result.get("diagnosis", []), 1):
        print(f"  {i}. {d}")

    print(f"\\n[인사이트] {result.get('pattern_insights', '-')}")'''

if old_section in content:
    content = content.replace(old_section, new_section)
    print("fix 3 applied: save_tuning moved before prints")
else:
    print("fix 3 skipped: section not found - applying emoji fix only")

with open('daily_review.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("daily_review.py 수정 완료")
