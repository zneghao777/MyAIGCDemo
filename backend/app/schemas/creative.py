"""Validated contracts for the three-confirmation creative workflow."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Persona(Contract):
    name: str = Field(min_length=1, max_length=50)
    identity: str = ""
    age: str = ""
    personality: str = ""
    background: str = ""
    motivation: str = ""
    relationships: str = ""
    arc: str = ""
    speech: str = ""
    appearance: str = ""
    build: str = ""
    hair: str = ""
    features: str = ""
    clothing: str = ""
    accessories: str = ""
    image_prompt: str = ""
    voice_description: str = ""
    voice_prompt: str = ""
    base_speed: float = Field(default=1, ge=0.5, le=2)
    voice_mode: Literal["stable", "expressive"] = "stable"
    base_pitch: int = Field(default=0, ge=-12, le=12)
    variants: dict[str, str] = Field(default_factory=dict)
    identity_traits: str = ""
    role_kind: Literal["speaking", "background"] = "speaking"


class Location(Contract):
    id: str
    name: str
    description: str
    landmarks: str = ""
    lighting: str = ""
    palette: str = ""
    spatial_notes: str = ""
    states: dict[str, str] = Field(default_factory=dict)


class ActionStep(Contract):
    id: str = Field(min_length=1, max_length=36)
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)
    description: str = Field(min_length=1, max_length=2000)
    trigger_line_id: str | None = None
    trigger_sec: float | None = Field(default=None, ge=0)


class SubtitleCue(Contract):
    id: str = Field(min_length=1, max_length=36)
    line_id: str | None = None
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)
    text: str = Field(min_length=1, max_length=1000)


class VideoReference(Contract):
    kind: Literal["image", "video", "audio"] = "image"
    asset_id: str = Field(min_length=1, max_length=36)
    purpose: str = Field(min_length=1, max_length=1000)


class VideoInput(Contract):
    mode: Literal["first_frame", "first_last_frame", "references", "text"] = "first_frame"
    first_frame_asset_id: str | None = None
    last_frame_asset_id: str | None = None
    references: list[VideoReference] = Field(default_factory=list, max_length=12)
    sound_strategy: Literal["post_audio", "model_audio"] = "post_audio"
    resolution: Literal["480P", "768P", "1080P", "2K", "4K"] | None = None
    use_context_ir: bool = False
    prompt: str = Field(default="", max_length=10000)

    @model_validator(mode="after")
    def modes(self):
        if self.mode != "references" and self.references:
            raise ValueError("首帧/首尾帧模式不能混用多素材参考")
        if self.mode == "references" and (self.first_frame_asset_id or self.last_frame_asset_id):
            raise ValueError("多素材模式不能混用首尾帧")
        if self.mode == "text" and (self.first_frame_asset_id or self.last_frame_asset_id):
            raise ValueError("纯文字预演不能混入首尾帧")
        if self.mode == "first_frame" and self.last_frame_asset_id:
            raise ValueError("首帧模式不能设置尾帧")
        return self


class Plan(Contract):
    title: str = Field(min_length=1, max_length=100)
    synopsis: str
    theme: str
    beats: list[str] = Field(min_length=4, max_length=8)
    ending: str
    duration: int = Field(default=30, ge=6, le=240)
    fixed_scene_count: bool = False
    scene_count: int = Field(default=3, ge=1, le=24)
    ratio: Literal["9:16", "16:9", "1:1"] = "16:9"
    style: str = Field(default="电影写实", max_length=2000)
    characters: list[Persona] = Field(min_length=1, max_length=10)
    locations: list[Location] = Field(min_length=1, max_length=12)


class Line(Contract):
    id: str = Field(min_length=1, max_length=36)
    speaker_id: str | None = None
    delivery: Literal["on_screen", "off_screen"] = "on_screen"
    continues_from: str | None = None
    text: str = Field(min_length=1, max_length=1000)
    emotion: Literal["neutral", "happy", "sad", "angry", "fearful", "disgusted", "surprised", "calm"] = (
        "neutral"
    )
    speed: float = Field(default=1, ge=0.5, le=2)
    pause_after: float = Field(default=0.15, ge=0, le=5)


class SoundEffect(Contract):
    asset_id: str
    start_sec: float = Field(default=0, ge=0, le=120)
    volume: float = Field(default=0.35, ge=0, le=1)


class Shot(Contract):
    title: str
    beat_indices: list[int] = Field(default_factory=list, max_length=8)
    offscreen_cast: dict[str, str] = Field(default_factory=dict)
    cast: dict[str, str] = Field(
        default_factory=dict, description="character ID -> exact confirmed revision ID"
    )
    variants: dict[str, str] = Field(default_factory=dict)
    location_id: str
    location_description: str = ""
    action: str = ""
    expression: str = ""
    composition: str = ""
    shot_type: Literal["远景", "全景", "中景", "近景", "特写"] = "中景"
    camera_angle: str = "平视"
    camera_move: Literal["固定", "缓推", "拉远", "摇镜", "缓慢横移", "跟随"] = "固定"
    duration: float = Field(default=5, ge=3, le=120)
    image_prompt: str = ""
    lines: list[Line] = Field(default_factory=list, max_length=50)
    narration: list[Line] = Field(default_factory=list, max_length=20)
    sound_notes: str = ""
    audio_order: list[str] = Field(default_factory=list, max_length=70)
    sound_effects: list[SoundEffect] = Field(default_factory=list, max_length=8)
    purpose: str = ""
    start_state: str = ""
    end_state: str = ""
    action_steps: list[ActionStep] = Field(default_factory=list, max_length=40)
    spatial_relations: dict[str, str] = Field(default_factory=dict)
    continuity_from: str | None = None
    continuity_requirements: str = ""
    location_revision: str | None = None
    location_state: str = ""
    character_views: dict[str, str] = Field(default_factory=dict)
    first_frame_asset_id: str | None = None
    last_frame_asset_id: str | None = None
    subtitle_cues: list[SubtitleCue] = Field(default_factory=list, max_length=100)
    subtitles_calibrated: bool = False
    video_input: VideoInput | None = None

    @model_validator(mode="after")
    def speakers(self, info: ValidationInfo):
        all_lines = self.lines + self.narration
        if len({x.id for x in all_lines}) != len(all_lines):
            raise ValueError("台词 ID 不能重复")
        if any(not x.speaker_id or x.speaker_id not in (self.cast | self.offscreen_cast) for x in self.lines):
            raise ValueError("台词必须绑定画内或画外发言角色")
        if any(x.speaker_id is not None for x in self.narration):
            raise ValueError("旁白必须使用独立旁白配置")
        if self.audio_order and (
            len(self.audio_order) != len(all_lines) or set(self.audio_order) != {x.id for x in all_lines}
        ):
            raise ValueError("声音顺序必须恰好包含全部台词和旁白，不能重复或遗漏")
        line_ids = {x.id for x in all_lines}
        if set(self.character_views) - set(self.cast) or set(self.spatial_relations) - set(self.cast):
            raise ValueError("角色视图和空间关系必须引用本镜出场角色 ID")
        if set(self.variants) - set(self.cast):
            raise ValueError("造型必须引用本镜出场角色 ID")
        subtitle_duration = (info.context or {}).get("subtitle_duration", self.duration)
        for records, limit in ((self.action_steps, self.duration), (self.subtitle_cues, subtitle_duration)):
            if len({x.id for x in records}) != len(records):
                raise ValueError("动作或字幕 ID 不能重复")
            for record in records:
                if not record.start_sec < record.end_sec <= limit:
                    raise ValueError("动作和字幕时间必须在本镜时长范围内")
        for step in self.action_steps:
            if step.trigger_line_id and step.trigger_line_id not in line_ids:
                raise ValueError("动作触发台词必须引用本镜稳定台词 ID")
            if step.trigger_sec is not None and not step.start_sec <= step.trigger_sec <= step.end_sec:
                raise ValueError("动作触发点必须在动作时间区间内")
        cues = sorted(self.subtitle_cues, key=lambda x: x.start_sec)
        if any(a.end_sec > b.start_sec for a, b in zip(cues, cues[1:])):
            raise ValueError("字幕区间不能重叠，请逐句校正时间")
        if any(x.line_id and x.line_id not in line_ids for x in cues):
            raise ValueError("字幕必须引用本镜台词 ID")
        if any(x.start_sec >= self.duration for x in self.sound_effects):
            raise ValueError("音效起点必须在镜头时长内")
        return self


class GeneratedShot(Shot):
    # A model may describe effects, but cannot invent uploaded asset identities.
    sound_effects: list[SoundEffect] = Field(default_factory=list, max_length=0)


class Storyboard(Contract):
    scenes: list[GeneratedShot] = Field(min_length=1, max_length=24)


class VoiceMatches(Contract):
    voice_ids: list[str] = Field(min_length=1, max_length=3)
    reason: str


class Edit(Contract):
    expected: int
    data: dict


class Generate(Contract):
    operation: Literal[
        "plan",
        "character",
        "character_image",
        "location_image",
        "voice_match",
        "voice_preview",
        "voice_design",
        "voice_clone",
        "storyboard",
        "shot_image",
        "shot_audio",
        "role_audio",
    ]
    target: str = ""
    variant: str = ""
    view: Literal["", "full_body", "front", "side", "back", "half_body", "face", "state", "turnaround"] = ""
    use_reference: bool = False
    auto_apply: bool = False
    frame: Literal["first", "last"] = "first"
    voice_id: str = ""
    text: str = "你好，我们终于见面了。这件事，我已经等了很久。别担心，我们一起把它做好。走吧，我们回家。"
    nonce: str = ""
    regenerate_line_ids: list[str] = Field(default_factory=list, max_length=70)

    @model_validator(mode="after")
    def retake(self):
        if self.regenerate_line_ids and (self.operation != "shot_audio" or not self.nonce):
            raise ValueError("单句重录需要配音操作和独立的重录标识")
        return self


class Selection(Contract):
    candidate_id: str
    expected: int
    data: dict | None = None
