import json, os, time
from youtube_transcript_api import YouTubeTranscriptApi
TODO = {2: "4_33Wsc9fcg", 5: "zCj2SWbpmOk", 6: "A1LOTQ0R8ww", 7: "ZGRXswei3kI", 8: "omZpI1DbYRI", 9: "4vRHblHQWvA"}
api = YouTubeTranscriptApi()
for attempt in range(8):
    try:
        api.list("4_33Wsc9fcg").find_transcript(["hi"]).fetch(); print("차단 해제 확인", flush=True); break
    except Exception as e:
        print(f"시도 {attempt+1}: {type(e).__name__} — 10분 대기", flush=True); time.sleep(600)
else:
    print("최종: 여전히 차단", flush=True); raise SystemExit(1)
for n, vid in TODO.items():
    fn = f"{n:02d}_{vid}_hi.txt"
    if os.path.exists(fn): continue
    try:
        segs = api.list(vid).find_transcript(["hi", "en-US"]).fetch()
        t = " ".join(s.text.replace("\n", " ") for s in segs)
        open(fn, "w", encoding="utf-8").write(t)
        open(f"{n:02d}_{vid}_lines.txt", "w", encoding="utf-8").write("\n".join(t[i:i+1000] for i in range(0, len(t), 1000)))
        print("저장", fn, len(t), flush=True)
    except Exception as e:
        print("실패", vid, type(e).__name__, flush=True)
    time.sleep(60)
print("완료", flush=True)
