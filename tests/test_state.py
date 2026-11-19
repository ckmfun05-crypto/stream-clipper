import json

from clipper.state import State


def test_save_and_reload(tmp_path):
    path = tmp_path / "processed.json"
    state = State(path)
    assert not state.has_vod("abc")

    state.add_vod("abc", "SomeStreamer", "https://twitch.tv/videos/123")
    state.add_clip("abc", {"file": "clips/a.mp4", "start": 0, "end": 30})
    state.save()

    loaded = State.load(path)
    assert loaded.has_vod("abc")
    assert loaded.data["vods"]["abc"]["clips"][0]["file"] == "clips/a.mp4"
    assert not (path.with_suffix(".json.tmp")).exists()


def test_mark_uploaded(tmp_path):
    path = tmp_path / "state.json"
    state = State(path)
    state.add_vod("v1", "Streamer", "url")
    state.add_clip("v1", {"file": "clips/one.mp4"})
    state.add_clip("v1", {"file": "clips/two.mp4"})

    state.mark_uploaded("v1", "clips/one.mp4", "yt111")
    assert state.data["vods"]["v1"]["status"] == "clipped"
    state.mark_uploaded("v1", "clips/two.mp4", "yt222")
    assert state.data["vods"]["v1"]["status"] == "uploaded"
    assert state.data["vods"]["v1"]["clips"][1]["youtube_id"] == "yt222"


def test_corrupt_state_starts_fresh(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("not json", encoding="utf-8")
    state = State.load(path)
    assert state.data == {"vods": {}}
