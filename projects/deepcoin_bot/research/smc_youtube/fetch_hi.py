import json, os, time, urllib.request, urllib.parse
from youtube_transcript_api import YouTubeTranscriptApi
IDS = ["jwjjWHzEaJc","4_33Wsc9fcg","46wLDbl2_d0","qEMhYlT6gwk","zCj2SWbpmOk","A1LOTQ0R8ww","ZGRXswei3kI","omZpI1DbYRI","4vRHblHQWvA","CK5jXz_io38","0zmD8iYhvpc"]
api = YouTubeTranscriptApi()
meta = json.load(open("meta.json", encoding="utf-8")) if os.path.exists("meta.json") else []
done = {m["id"] for m in meta}
for n, vid in enumerate(IDS, 1):
    if vid in done: continue
    for attempt in range(12):
        try:
            u = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(f"https://www.youtube.com/watch?v={vid}")
            try: title = json.loads(urllib.request.urlopen(u, timeout=10).read())["title"]
            except Exception: title = "(제목 조회 실패)"
            tr = api.list(vid).find_transcript(["en-US", "hi"])
            segs = tr.fetch()
            out, buf, t0 = [], [], 0
            for s in segs:
                if s.start - t0 >= 30 and buf:
                    out.append(f"[{int(t0//60):02d}:{int(t0%60):02d}] " + " ".join(buf)); buf, t0 = [], s.start
                buf.append(s.text.replace("\n", " "))
            if buf: out.append(f"[{int(t0//60):02d}:{int(t0%60):02d}] " + " ".join(buf))
            fn = f"{n:02d}_{vid}_{tr.language_code}.txt"
            open(fn, "w", encoding="utf-8").write(f"# {title}\n" + "\n".join(out))
            meta.append(dict(n=n, id=vid, title=title, lang=tr.language_code, minutes=round(segs[-1].start / 60), file=fn))
            json.dump(meta, open("meta.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(n, vid, tr.language_code, round(segs[-1].start / 60), "분", title, flush=True)
            time.sleep(20)
            break
        except Exception as e:
            print(n, vid, "대기 후 재시도", type(e).__name__, flush=True); time.sleep(150)
print("완료", len(meta), flush=True)
