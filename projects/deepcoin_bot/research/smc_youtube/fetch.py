import json, sys
from youtube_transcript_api import YouTubeTranscriptApi
IDS = ["jwjjWHzEaJc","4_33Wsc9fcg","46wLDbl2_d0","qEMhYlT6gwk","zCj2SWbpmOk","A1LOTQ0R8ww","ZGRXswei3kI","omZpI1DbYRI","4vRHblHQWvA","CK5jXz_io38","0zmD8iYhvpc"]
api = YouTubeTranscriptApi()
for n, vid in enumerate(IDS, 1):
    try:
        tl = api.list(vid)
        langs = [(t.language_code, t.is_generated) for t in tl]
        t = api.fetch(vid, languages=["ko", "en", "en-US", "en-GB", "hi", "bn"])
        text = " ".join(s.text for s in t)
        open(f"{n:02d}_{vid}.txt", "w", encoding="utf-8").write(text)
        print(n, vid, "langs", langs, "chars", len(text))
    except Exception as e:
        print(n, vid, "ERR", type(e).__name__, str(e)[:200])
