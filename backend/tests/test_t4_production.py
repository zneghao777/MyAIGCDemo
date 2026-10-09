"""T4 contracts use isolated projects and real short media, never the user's film."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
import subprocess
import pytest
from sqlalchemy import select
from app.core.config import get_settings
from app.core.db import Session
from app.models import Scene, Project, Asset
from app.providers import providers
from app.services.video import payload, organized_prompt, is_stale
from app.services.story_pacing import assess
from app.schemas.creative import Shot
from app.tasks.execute import execute_job
from test_creative import setup, fetch, confirm


def test_original_sound_compiles_saved_lines_without_tts_and_excludes_internal_ids():
    shot = Shot(title="转折", location_id="room", cast={"char-id":"rev"}, offscreen_cast={"off-id":"rev"},
                shot_type="特写", composition="左侧留白", sound_notes="杯沿轻响，禁止背景音乐",
                action="放低茶杯后开口", action_steps=[{"id":"look-up","start_sec":0,"end_sec":1,"description":"抬眼"}],
                lines=[{"id":"line-a","speaker_id":"char-id","text":"原来你一直在。"},
                       {"id":"line-b","speaker_id":"off-id","text":"我从未离开。","delivery":"off_screen"}],
                narration=[{"id":"n","text":"天光渐亮。"}]).model_dump()
    scene=SimpleNamespace(creative={"shot":shot},duration_sec=10,camera_move="缓推",image_prompt="茶馆",video_prompt="")
    prompt=organized_prompt(scene,[{"role":"reference_image","kind":"image","purpose":"阿茶的形象"}],{"sound_strategy":"model_audio"},{"char-id":"阿茶","off-id":"月神"})
    for text in ["原来你一直在。","我从未离开。","天光渐亮。","阿茶","月神","特写","左侧留白","杯沿轻响","画外音","预计，非精确对齐","<Picture 1>","放低茶杯后开口","抬眼"]:
        assert text in prompt
    assert "char-id" not in prompt and "line-a" not in prompt
    # H3's dialogue marker distinguishes spoken words from directing prose.
    assert '<d>[Chinese] 原来你一直在。</d>' in prompt
    assert prompt.count('<d>') == 3


def test_pacing_is_advice_and_offscreen_does_not_force_cast():
    shot=Shot(title="开端",location_id="room",offscreen_cast={"speaker":""},lines=[{"id":"a","speaker_id":"speaker","text":"这是一句明显超出三秒容量的长长长长长对白","delivery":"off_screen"}],duration=3)
    assert not shot.cast
    scene=SimpleNamespace(title="开端",duration_sec=3,creative={"shot":shot.model_dump()})
    result=assess({"duration":30,"beats":["开端","发展","转折","结局"]},[scene])
    assert any("预计" in x for x in result["warnings"])
    assert any("结局" in x for x in result["warnings"])
    assert result["measured_seconds"]==0


def test_subtitles_can_follow_measured_adoption_without_changing_design_duration():
    value={"title":"结尾","location_id":"room","duration":6,"subtitle_cues":[{"id":"s","text":"天亮了。","start_sec":5.9,"end_sec":6.5}]}
    with pytest.raises(ValueError):
        Shot.model_validate(value)
    actual=Shot.model_validate(value,context={"subtitle_duration":6.58})
    assert actual.duration==6 and actual.subtitle_cues[0].end_sec==6.5
    with pytest.raises(ValueError):
        Shot.model_validate(value,context={"subtitle_duration":6.4})


@pytest.mark.parametrize("mode", ["references", "text"])
async def test_no_storyboard_image_native_reference_quote_and_segment_export(client,monkeypatch,tmp_path,mode):
    p=await setup(client,monkeypatch);pid=p["id"];sc=p["scenes"][0]
    monkeypatch.setattr(get_settings(),"feature_video_generation",True)
    monkeypatch.setattr(get_settings(),"minimax_video_poll_interval_ms",1)
    provider=SimpleNamespace(balance=AsyncMock(return_value={"available_points":1000}),create=AsyncMock(return_value="paid-t4"),query=AsyncMock(return_value={"status":"succeeded","fileUrl":"https://example.com/film.mp4"}))
    monkeypatch.setattr(providers(),"video",provider)
    async with Session() as db:
        asset=await db.scalar(select(Asset).where(Asset.project_id==pid,Asset.content_type.like("image/%")))
        aid=asset.id
    data={"mode":mode,"sound_strategy":"model_audio","references":[{"asset_id":aid,"kind":"image","purpose":"林夏的形象"}] if mode=="references" else []}
    r=await client.post(f"/api/creative/scenes/{sc['id']}/production-settings",json={"expected":sc["creative"]["version"],"data":data});assert r.status_code==200,r.text
    f=await fetch(client,pid);assert f["scenes"][0]["video_ready"]
    q=await client.get(f"/api/scenes/{sc['id']}/video-quote");assert q.status_code==200,q.text
    assert "第1句" in q.json()["prompt"] and "林夏" in q.json()["prompt"]
    assert not f["project"]["scenes"][0]["image"]
    # Add an adjacent shot through the public product route; grouping is one paid request.
    add=await client.post(f"/api/creative/projects/{pid}/add-shot",json={"expected":f["project"]["creative"]["version"],"data":{}});assert add.status_code==200
    sid2=add.json()["scene_id"]
    f=await fetch(client,pid)
    group=await client.post(f"/api/creative/projects/{pid}/segments",json={"expected":f["project"]["creative"]["version"],"data":{"scene_ids":[sc['id'],sid2]}});assert group.status_code==200,group.text
    await confirm(client,pid,"shots")
    batch=(await client.post(f"/api/creative/projects/{pid}/batch/estimate")).json()
    assert batch['calls']==0 and batch['targets']==[]
    q=(await client.get(f"/api/scenes/{sc['id']}/video-quote")).json();assert q["duration"]==10 and "第 2 镜" in q["prompt"]
    raw_path=tmp_path/'real.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=160x288:r=24:d=10','-f','lavfi','-i','sine=frequency=500:duration=10','-c:v','libx264','-preset','ultrafast','-c:a','aac','-shortest','-y',str(raw_path)],check=True)
    monkeypatch.setattr('app.tasks.execute.fetch_bytes',AsyncMock(return_value=raw_path.read_bytes()))
    jobs=(await client.post('/api/tasks',json={'projectId':pid,'sceneIds':[sc['id']],'kind':'video'})).json()
    tid=jobs['queued'][0]['id'];await execute_job(tid)
    task=(await client.get(f'/api/tasks/{tid}')).json();assert task['status']=='done',task
    f=await fetch(client,pid);leader=f['project']['scenes'][0]
    assert not leader['videoUrl']  # Paid result requires an explicit selection.
    takes=(await client.get(f"/api/creative/scenes/{sc['id']}/production")).json()['takes'];assert len(takes)==1
    # Captions checked against an earlier performance cannot stay accepted
    # after choosing a new native-sound take, even with identical written lines.
    captions=deepcopy(leader['creative']['shot'])
    captions['subtitle_cues']=[{'id':'old-cue','text':'原字幕','start_sec':1,'end_sec':2}]
    captions['subtitles_calibrated']=True
    edited=await client.patch(f"/api/creative/scenes/{sc['id']}",json={'expected':leader['creative']['version'],'data':captions})
    assert edited.status_code==200,edited.text
    await confirm(client,pid,"shots")
    f=await fetch(client,pid);leader=f['project']['scenes'][0]
    selected=await client.post(f"/api/creative/scenes/{sc['id']}/select-video",json={'expected':leader['creative']['version'],'data':{'take':takes[0]['take']}});assert selected.status_code==200,selected.text
    f=await fetch(client,pid);rows=f['project']['scenes'];assert rows[0]['videoUrl']==rows[1]['videoUrl']
    assert rows[0]['creative']['shot']['subtitles_calibrated'] is False
    assert rows[0]['creative']['shot']['subtitle_cues'][0]['text']=='原字幕'
    assert rows[0]['creative']['edit']['out_sec']==rows[1]['creative']['edit']['in_sec']==5
    assert not f['issues'],f['issues']
    # The modification quote carries the actual original video and the complete
    # multi-shot script. It does not create another paid task or change the edit.
    modification=await client.post(f"/api/scenes/{sc['id']}/video-retake-quote",json={"expected":rows[0]['creative']['version'],"nonce":"preview-edit","reason":"减弱茶杯反光","preserve":"保留两镜切换与全部台词","modify":True,"source_asset_id":takes[0]['asset_id']})
    assert modification.status_code==200,modification.text
    result=modification.json()
    assert '第 2 镜' in result['prompt'] and '减弱茶杯反光' in result['prompt']
    assert any(m['asset_id']==takes[0]['asset_id'] and m['role']=='reference_video' for m in result['materials'])
    assert provider.create.await_count==1
    # Local sound cleanup is a separate candidate. It neither replaces the
    # selected paid version nor alters video frames, duration or speed.
    before_cleanup = await fetch(client,pid)
    cleanup_body={'expected':before_cleanup['project']['scenes'][0]['creative']['version'],'data':{'take':takes[0]['take'],'ranges':[{'start':0,'end':2}]}}
    cleaned=await client.post(f"/api/creative/scenes/{sc['id']}/clean-video-audio",json=cleanup_body)
    assert cleaned.status_code==200,cleaned.text
    after_cleanup=await fetch(client,pid)
    assert after_cleanup['project']['scenes'][0]['creative']['video']['take']==takes[0]['take']
    candidates=(await client.get(f"/api/creative/scenes/{sc['id']}/production")).json()['takes']
    assert len(candidates)==2
    clean_path=tmp_path/'clean.mp4'
    clean_path.write_bytes(await providers().storage.get(candidates[-1]['key']))
    def frames(path):
        return subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-map','0:v','-f','framemd5','-']).split(b'#tb')[-1]
    assert frames(raw_path)==frames(clean_path)
    import array
    samples=array.array('f',subprocess.check_output(['ffmpeg','-v','error','-i',str(clean_path),'-ss','0.3','-t','1','-f','f32le','-ac','1','-ar','16000','-']))
    assert max(abs(x) for x in samples)<.001
    assert abs(candidates[-1]['duration']-10)<.1
    assert provider.create.await_count==1
    # An audio-only excerpt from a video is available as a genuine sound ref.
    excerpt=await client.post(f'/api/creative/projects/{pid}/reference-excerpt',json={'expected':after_cleanup['project']['creative']['version'],'data':{'asset_id':takes[0]['asset_id'],'start_sec':2,'end_sec':5,'audio_only':True,'purpose':'角色声音'}})
    assert excerpt.status_code==200,excerpt.text
    assert excerpt.json()['kind']=='audio' and excerpt.json()['duration']==3
    out=await client.post(f'/api/projects/{pid}/exports',json={'resolution':'source','subtitles':False});assert out.status_code==202,out.text
    await execute_job(out.json()['taskId'])
    exported=(await client.get('/api/exports/'+out.json()['exportJobId'])).json()
    assert exported['status']=='done',exported
    assert abs(exported['durationSec']-10)<.1  # Not 20 seconds of duplicated whole clips.
    assert provider.create.await_count==1
    # Shortening an adoption can leave old captions out of bounds. The workbench
    # must remain readable and editable instead of failing its entire GET.
    current=await fetch(client,pid);first=current['project']['scenes'][0]
    resized=await client.post(f"/api/creative/scenes/{first['id']}/edit-range",json={'expected':first['creative']['version'],'data':{'in_sec':0,'out_sec':1.5}})
    assert resized.status_code==200,resized.text
    repairable=await fetch(client,pid)
    assert any('字幕时间' in issue for issue in repairable['issues'])
    # A design change invalidates the group but keeps the paid candidate and original.
    second=rows[1];shot=deepcopy(second['creative']['shot']);shot['action']='转身'
    edited=await client.patch(f"/api/creative/scenes/{second['id']}",json={'expected':second['creative']['version'],'data':shot});assert edited.status_code==200
    f=await fetch(client,pid);assert any('视频与当前设计' in x for x in f['issues'])
    assert f['scenes'][1]['video_stale'] is True
    assert len((await client.get(f"/api/creative/scenes/{sc['id']}/production")).json()['takes'])==2


def test_recovery_keeps_offscreen_speaker_out_of_visible_cast():
    from app.services.storyboard_recovery import normalize
    value={"scenes":[{"cast":{"a":"revision-a"},"offscreen_cast":{"b":"revision-b"},"lines":[{"id":"line","speaker_id":"b","text":"放下吧。","delivery":"off_screen"}],"narration":[]}]}
    inp={"cast":{"a":{"confirmed":True,"revision":"revision-a","persona":{"name":"阿茶"}},"b":{"confirmed":True,"revision":"revision-b","persona":{"name":"月神"}}},"plan":{"locations":[]}}
    repaired,_=normalize(value,inp)
    assert repaired['scenes'][0]['cast']=={'a':'revision-a'}
    assert repaired['scenes'][0]['offscreen_cast']=={'b':'revision-b'}
