"""Run a resumable, three-shot real image/TTS demo. Never submits video jobs."""

import asyncio
import json
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / ".runtime" / "consistency-demo.json"
BASE = "http://127.0.0.1:8001/api"


async def main():
    saved = json.loads(STATE.read_text()) if STATE.exists() else {"jobs": {}, "steps": []}

    def persist():
        STATE.parent.mkdir(exist_ok=True)
        STATE.write_text(json.dumps(saved, ensure_ascii=False, indent=2))

    async with httpx.AsyncClient(timeout=60, trust_env=False) as client:

        async def api(path, method="GET", data=None):
            r = await client.request(method, BASE + path, json=data)
            r.raise_for_status()
            return r.json()

        if not saved.get("project_id"):
            p = await api(
                "/projects",
                "POST",
                {
                    "name": "雨停之前 · 一致性演示",
                    "description": "生成一个中文温情微短剧《雨停之前》。严格只有两名角色：林夏，26岁女修伞匠，黑色齐下巴短发，左侧银色发夹，米白衬衫配深绿色工装围裙；老周，58岁男车站值班员，灰白短发、方框眼镜，深蓝色工作夹克。两人穿着和外貌全片不变，不设计造型变体。傍晚雨中的老车站修伞柜台，林夏修好老周保留多年的黄色旧伞，发现伞柄刻着母亲名字；老周告诉她这是母亲当年留下的伞，两人一起撑伞走向雨后站台。仅3个镜头，约24秒，总台词及旁白控制在90个汉字内。每镜至多两句简短对白、一句简短旁白。至少一镜两人同框，两个人全程保持同一形象。结尾温暖克制。风格：精致日系手绘动画电影，柔和琥珀灯光与雨夜蓝色对比，无文字无水印。16:9。",
                    "style": "精致手绘动画电影，柔和琥珀灯光与雨夜蓝色对比",
                    "ratio": "16:9",
                },
            )
            saved["project_id"] = p["id"]
            persist()
            print("PROJECT", p["id"], flush=True)
        pid = saved["project_id"]
        path = f"/creative/projects/{pid}"

        async def flow():
            return await api(path)

        async def step(name, action):
            if name in saved["steps"]:
                return
            print("STEP", name, flush=True)
            await action()
            saved["steps"].append(name)
            persist()

        async def generate(key, operation, **kwargs):
            if key not in saved["jobs"]:
                r = await api(path + "/generate", "POST", {"operation": operation, **kwargs})
                saved["jobs"][key] = r["taskId"]
                persist()
            tid = saved["jobs"][key]
            last = None
            for _ in range(1200):
                task = await api("/tasks/" + tid)
                status = (task["status"], task["progress"])
                if status != last:
                    print("TASK", key, *status, flush=True)
                    last = status
                if task["status"] == "done":
                    return task["result"]["candidateId"]
                if task["status"] in ("failed", "cancelled"):
                    raise RuntimeError(f"{key}: {task.get('error')}")
                await asyncio.sleep(2)
            raise TimeoutError(key)

        async def select(cid):
            f = await flow()
            candidate = next(x for x in f["candidates"] if x["id"] == cid)
            if candidate.get("selected"):
                return
            p = f["project"]
            target = next((x for x in p["characters"] + p["scenes"] if x["id"] == candidate["entityId"]), p)
            await api(
                path + "/select", "POST", {"candidate_id": cid, "expected": target["creative"]["version"]}
            )

        async def gen_select(key, operation, **kwargs):
            await select(await generate(key, operation, **kwargs))

        async def confirm(stage):
            f = await flow()
            await api(
                path + "/confirm/" + stage,
                "POST",
                {"expected": f["project"]["creative"]["version"], "data": {}},
            )

        await step("start", lambda: api(path + "/start", "POST"))
        await step("plan", lambda: gen_select("plan", "plan"))

        async def plan_limits():
            f = await flow()
            st = f["project"]["creative"]
            plan = st["plan"]
            assert len(plan["characters"]) == 2, "Demo scope is exactly two characters"
            plan["scene_count"] = 3
            plan["duration"] = 24
            plan["ratio"] = "16:9"
            for c in plan["characters"]:
                c["variants"] = {}
            await api(path + "/plan", "PATCH", {"expected": st["version"], "data": plan})

        await step("scope", plan_limits)
        await step("confirm-plan", lambda: confirm("plan"))
        f = await flow()
        for c in f["project"]["characters"]:
            cid = c["id"]
            voice = "female-shaonv" if c["name"] == "林夏" else "male-qn-qingse"
            await step(
                "image-" + cid, lambda cid=cid: gen_select("image-" + cid, "character_image", target=cid)
            )
            await step(
                "voice-" + cid,
                lambda cid=cid, voice=voice: gen_select(
                    "voice-" + cid,
                    "voice_preview",
                    target=cid,
                    voice_id=voice,
                    text="雨会停的，我们一起回家。",
                ),
            )

            async def confirm_char(cid=cid):
                ch = next(x for x in (await flow())["project"]["characters"] if x["id"] == cid)
                await api(
                    "/creative/characters/" + cid + "/confirm",
                    "POST",
                    {"expected": ch["creative"]["version"], "data": {}},
                )

            await step("confirm-" + cid, confirm_char)
        await step("confirm-cast", lambda: confirm("cast"))
        await step("storyboard", lambda: gen_select("storyboard", "storyboard"))

        async def arrange():
            f = await flow()
            for sc in f["project"]["scenes"]:
                shot = sc["creative"]["shot"]
                shot["audio_order"] = [x["id"] for x in shot["narration"] + shot["lines"]]
                await api(
                    "/creative/scenes/" + sc["id"],
                    "PATCH",
                    {"expected": sc["creative"]["version"], "data": shot},
                )

        await step("arrange-audio", arrange)
        await step("confirm-shots", lambda: confirm("shots"))
        f = await flow()
        for i, sc in enumerate(f["project"]["scenes"]):
            sid = sc["id"]
            await step(
                "shot-image-" + sid, lambda sid=sid: gen_select("shot-image-" + sid, "shot_image", target=sid)
            )
            await step(
                "shot-audio-" + sid, lambda sid=sid: gen_select("shot-audio-" + sid, "shot_audio", target=sid)
            )
        f = await flow()
        print(
            "READY",
            json.dumps(
                {"project": pid, "issues": f["issues"], "shots": len(f["scenes"])}, ensure_ascii=False
            ),
            flush=True,
        )
        print("STATE", STATE, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
