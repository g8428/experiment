import json
import time

import pytest

import ig_publish as ig

OWNER = "U_OWNER"


class FakeResp:
    def __init__(self, body, status=200):
        self._b, self.status_code = body, status

    def json(self):
        return self._b


class FakeRequests:
    """requests.get/post 목: 호출 순서를 calls에 기록."""

    def __init__(self, handler):
        self.handler, self.calls = handler, []

    def get(self, url, **kw):
        self.calls.append(("GET", url, kw))
        return self.handler("GET", url, kw)

    def post(self, url, **kw):
        self.calls.append(("POST", url, kw))
        return self.handler("POST", url, kw)


# ---- 승인 판정
def test_find_latest_run_message_picks_newest_bot_msg():
    msgs = [
        {"ts": "100", "bot_id": "B", "text": "x ig-run:111"},
        {"ts": "300", "bot_id": "B", "text": "x ig-run:333"},
        {"ts": "400", "text": "사람이 쓴 ig-run:999"},
        {"ts": "200", "bot_id": "B", "text": "표식 없음"},
    ]
    m, rid = ig.find_latest_run_message(msgs)
    assert rid == "333"
    assert ig.find_latest_run_message([{"ts": "1", "text": "hi"}]) is None


def test_is_approved():
    ok = [{"name": "white_check_mark", "users": ["U1", OWNER]}]
    assert ig.is_approved(ok, OWNER)
    assert not ig.is_approved([{"name": "white_check_mark", "users": ["U1"]}], OWNER)
    assert not ig.is_approved([{"name": "thumbsup", "users": [OWNER]}], OWNER)
    assert not ig.is_approved(None, OWNER)


def test_already_published():
    assert ig.already_published([{"text": "✅ 인스타 게시 완료: https://instagram.com/p/x"}])
    assert not ig.already_published([{"text": "✅ 반응을 달면 인스타에 게시합니다"}, {"text": "❌ 인스타 게시 실패: x"}])


def slack_handler(reactions, replies):
    def h(method, url, kw):
        name = url.rsplit("/", 1)[1]
        if name == "conversations.history":
            return FakeResp({"ok": True, "messages": [{"ts": str(time.time()), "bot_id": "B", "text": "ig-run:42"}]})
        if name == "reactions.get":
            return FakeResp({"ok": True, "message": {"reactions": reactions}})
        if name == "conversations.replies":
            return FakeResp({"ok": True, "messages": replies})
        raise AssertionError(name)

    return h


@pytest.mark.parametrize("reactions,replies,status", [
    ([{"name": "white_check_mark", "users": [OWNER]}], [{"text": "root"}], "approved"),
    ([{"name": "white_check_mark", "users": ["U_OTHER"]}], [], "not_approved"),
    ([], [], "not_approved"),
    ([{"name": "white_check_mark", "users": [OWNER]}], [{"text": "✅ 인스타 게시 완료: https://x"}], "published"),
])
def test_check_approval(monkeypatch, reactions, replies, status):
    monkeypatch.setattr(ig, "requests", FakeRequests(slack_handler(reactions, replies)))
    st = ig.check_approval("xoxb-test", "C1", OWNER)
    assert st["status"] == status
    assert st["run_id"] == "42"


def test_check_approval_none(monkeypatch):
    monkeypatch.setattr(ig, "requests", FakeRequests(lambda m, u, k: FakeResp({"ok": True, "messages": []})))
    assert ig.check_approval("t", "C", OWNER)["status"] == "none"


# ---- Graph 호출 순서
def graph_handler(fail_on=None):
    state = {"n": 0}

    def h(method, url, kw):
        path = url.split("/v21.0/", 1)[1]
        if fail_on and path == fail_on:
            return FakeResp({"error": {"message": "Invalid token EAAsecretsecretsecret", "code": 190}}, 400)
        if method == "POST" and path == "IGU/media":
            cid = f"c{state['n']}"
            state["n"] += 1
            return FakeResp({"id": cid})
        if method == "GET" and path in ("c0", "c1", "c2"):
            assert "status_code" in kw["params"]["fields"]
            return FakeResp({"status_code": "FINISHED"})
        if path == "IGU/media_publish":
            return FakeResp({"id": "M1"})
        if path == "M1":
            return FakeResp({"permalink": "https://instagram.com/p/abc"})
        raise AssertionError(path)

    return h


def test_carousel_order(monkeypatch):
    fake = FakeRequests(graph_handler())
    monkeypatch.setattr(ig, "requests", fake)
    monkeypatch.setattr(ig.time, "sleep", lambda s: None)
    link = ig.Graph("TOKEN123", "IGU").publish(["https://u/01.jpg", "https://u/02.jpg"], "cap")
    assert link == "https://instagram.com/p/abc"
    seq = [(m, u.split("/v21.0/")[1]) for m, u, _ in fake.calls]
    assert seq == [
        ("POST", "IGU/media"), ("POST", "IGU/media"),  # 자식 컨테이너 2개
        ("GET", "c0"), ("GET", "c1"),                  # 각각 FINISHED 폴링
        ("POST", "IGU/media"),                         # CAROUSEL
        ("GET", "c2"),
        ("POST", "IGU/media_publish"),
        ("GET", "M1"),
    ]
    posts = [kw["data"] for m, u, kw in fake.calls if m == "POST" and u.endswith("IGU/media")]
    assert posts[0]["is_carousel_item"] == "true" and posts[0]["image_url"] == "https://u/01.jpg"
    assert posts[2]["media_type"] == "CAROUSEL" and posts[2]["children"] == "c0,c1" and posts[2]["caption"] == "cap"
    assert all(kw.get("data", kw.get("params"))["access_token"] == "TOKEN123" for _, _, kw in fake.calls)


def test_single_image_not_carousel(monkeypatch):
    fake = FakeRequests(graph_handler())
    monkeypatch.setattr(ig, "requests", fake)
    monkeypatch.setattr(ig.time, "sleep", lambda s: None)
    ig.Graph("T", "IGU").publish(["https://u/01.jpg"], "cap")
    first = fake.calls[0][2]["data"]
    assert "media_type" not in first and first["caption"] == "cap" and "is_carousel_item" not in first


def test_graph_version_env(monkeypatch):
    monkeypatch.setenv("IG_GRAPH_VERSION", "v99.0")
    assert ig.Graph("T", "U").base.endswith("/v99.0")


# ---- 토큰 마스킹
def test_token_masked_in_error(monkeypatch):
    monkeypatch.setenv("IG_ACCESS_TOKEN", "EAAsecretsecretsecret")
    fake = FakeRequests(graph_handler(fail_on="IGU/media"))
    monkeypatch.setattr(ig, "requests", fake)
    with pytest.raises(ig.GraphError) as ei:
        ig.Graph("EAAsecretsecretsecret", "IGU").publish(["https://u/1.jpg"], "c")
    assert "EAAsecret" not in str(ei.value) and "***" in str(ei.value)
    assert ei.value.code == 190


def test_mask_patterns():
    assert "abc123" not in ig.mask("GET ...?access_token=abc123&x=1")
    assert "xoxb-1234567890-abcdef" not in ig.mask("token xoxb-1234567890-abcdef")


# ---- CLI
def test_missing_env_exits_nonzero(monkeypatch, capsys):
    for k in ("SLACK_BOT_TOKEN", "SLACK_CHANNEL_ID", "SLACK_OWNER_USER_ID", "IG_ACCESS_TOKEN", "IG_USER_ID", "GITHUB_REPOSITORY"):
        monkeypatch.delenv(k, raising=False)
    assert ig.main(["--dry-run"]) == 2
    out = capsys.readouterr().out
    assert "SLACK_BOT_TOKEN" in out and "IG_ACCESS_TOKEN" in out


def test_dry_run_prints_plan_and_publishes_nothing(monkeypatch, tmp_path, capsys):
    env = dict(SLACK_BOT_TOKEN="xoxb-t", SLACK_CHANNEL_ID="C", SLACK_OWNER_USER_ID=OWNER,
               IG_ACCESS_TOKEN="T", IG_USER_ID="IGU", GITHUB_REPOSITORY="o/r")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    ok = [{"name": "white_check_mark", "users": [OWNER]}]
    fake = FakeRequests(slack_handler(ok, [{"text": "root"}]))
    monkeypatch.setattr(ig, "requests", fake)
    (tmp_path / "01.png").write_bytes(b"x")
    (tmp_path / "02.png").write_bytes(b"x")
    (tmp_path / "card.json").write_text(json.dumps({"caption": "c", "hashtags": ["#a"]}), encoding="utf-8")
    assert ig.main(["--dry-run", "--cards-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "[dry-run]" in out and "raw.githubusercontent.com/o/r/ig-media/" in out
    assert not any("graph.facebook.com" in u or "chat.postMessage" in u for _, u, _ in fake.calls)


def test_not_approved_exits_quietly(monkeypatch):
    for k, v in dict(SLACK_BOT_TOKEN="xoxb-t", SLACK_CHANNEL_ID="C", SLACK_OWNER_USER_ID=OWNER).items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(ig, "requests", FakeRequests(slack_handler([], [])))
    assert ig.main(["--check"]) == 0
