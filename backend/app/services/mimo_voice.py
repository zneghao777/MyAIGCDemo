"""Create reviewable voice candidates and pin immutable local reference assets."""

import hashlib

from app.core.config import get_settings
from app.providers import providers
from app.providers.mimo import reference_voice_id, resolve_voice

from . import tts
from .resources import save_asset


def reference_for(asset, raw, origin):
    return {
        "key": asset.object_key,
        "asset_id": asset.id,
        "duration_ms": asset.duration_ms,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "format": "mp3",
        "origin": origin,
    }


async def generate(db, task, inp, operation, checkpoint):
    s = get_settings()
    reference = inp.get("reference")
    performance = {
        "model": inp["model"],
        "speed": inp["voice"].get("base_speed", 1),
        "pitch": inp["voice"].get("base_pitch", 0),
        "emotion": "calm" if inp["voice"].get("voice_mode") == "stable" else "neutral",
    }
    await checkpoint()
    if operation == "voice_design":
        prompt = inp["voice"].get("voice_prompt") or inp["voice"].get("voice_description") or ""
        _, raw = await providers().tts.design(prompt, inp["text"], "")
        raw, duration = await tts.normalize_sample(raw, checkpoint)
        voice = reference_voice_id(raw)
        mode, synthesis_model = "design", s.mimo_tts_clone_model
    else:
        if operation == "voice_clone":
            raw, duration = await tts.normalize_sample(
                await providers().storage.get(reference["key"]), checkpoint
            )
            asset = await save_asset(
                db, task.project_id, "voice-reference-locked", raw, "audio/mpeg", "mp3", duration_ms=duration
            )
            reference = {**reference_for(asset, raw, "upload"), "source_asset_id": reference["asset_id"]}
            voice = reference_voice_id(raw)
            mode = "clone"
        elif inp["model"] == s.mimo_tts_clone_model:
            voice, mode = inp["voice_id"], inp.get("voice_mode", "clone")
        else:
            voice, mode = resolve_voice(inp["voice_id"]), "preset"
        performance["reference"] = reference
        raw, duration = await tts.synthesize(inp["text"], voice, checkpoint, performance)
        synthesis_model = inp["model"]
    await checkpoint()
    asset = await save_asset(
        db, task.project_id, "voice-preview", raw, "audio/mpeg", "mp3", duration_ms=duration
    )
    if operation == "voice_design":
        reference = reference_for(asset, raw, "design")
    return {
        "key": asset.object_key,
        "asset_id": asset.id,
        "voice_id": voice,
        "provider": "mimo",
        "mode": mode,
        "model": synthesis_model,
        "generation_model": inp["model"],
        "duration_ms": duration,
        **({"reference": reference} if reference else {}),
    }
