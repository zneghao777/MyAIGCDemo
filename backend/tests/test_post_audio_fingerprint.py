from copy import deepcopy
from types import SimpleNamespace

from app.services.video import is_stale, source


def test_post_audio_corrections_reuse_video_but_model_audio_remains_sensitive():
    shot = {"title": "按灯", "sound_notes": "开关声", "sound_effects": [{"asset_id": "click", "start_sec": 3}], "video_input": {"sound_strategy": "post_audio"}}
    scene = SimpleNamespace(creative={"shot": shot}, first_frame_key="first.png", video_key="video.mp4", duration_sec=6, video_prompt="按灯后亮", image_prompt="", camera_move="固定")
    stored = source(scene, "16:9")
    # Normalize traces created before editorial sound fields were separated.
    stored["shot"]["sound_notes"] = "旧音效说明"
    stored["shot"]["sound_effects"] = deepcopy(shot["sound_effects"])
    scene.creative["video"] = {"source": stored}
    shot["sound_effects"][0]["start_sec"] = 2.8
    shot["sound_notes"] = "按实际视频校准按钮声"
    assert not is_stale(scene, "16:9")
    shot["video_input"]["prompt"] = "改变可见动作"
    assert is_stale(scene, "16:9")
    shot["video_input"] = {"sound_strategy": "model_audio"}
    scene.creative["video"] = {"source": source(scene, "16:9")}
    shot["sound_effects"][0]["start_sec"] = 2.5
    assert is_stale(scene, "16:9")
