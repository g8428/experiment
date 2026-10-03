import time
from youtube_transcript_api import YouTubeTranscriptApi
IDS = ["jwjjWHzEaJc","4_33Wsc9fcg","46wLDbl2_d0","qEMhYlT6gwk","zCj2SWbpmOk","A1LOTQ0R8ww","ZGRXswei3kI","omZpI1DbYRI","4vRHblHQWvA","CK5jXz_io38","0zmD8iYhvpc"]
api = YouTubeTranscriptApi()
for n, vid in enumerate(IDS, 1):
    for attempt in range(3):
        try:
            tl = api.list(vid)
            try:
                tr = tl.find_transcript(["en-US", "en"])
            except Exception:
                tr = tl.find_transcript(["hi"]).translate("en")
            segs = tr.fetch()
            lines = [f"[{int(s.start//60):02d}:{int(s.start%60):02d}] {s.text}" for s in segs]
            open(f"{n:02d}_{vid}_en.txt", "w", encoding="utf-8").write("\n".join(lines))
            print(n, vid, "ok", len(lines), "segs", sum(len(l) for l in lines), "chars", flush=True)
            break
        except Exception as e:
            print(n, vid, "retry", type(e).__name__, str(e)[:120], flush=True); time.sleep(5)
