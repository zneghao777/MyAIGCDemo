from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class Schema(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class StageObject(Schema):
    character_id: str | None = None
    id: str
    name: str = Field(max_length=100)
    kind: Literal["actor", "prop", "camera"]
    position: tuple[float, float, float]
    rotation: tuple[float, float, float]
    scale: float = Field(gt=0, le=100)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    action: str = Field(default="", max_length=500)


class Keyframe(Schema):
    id: str
    object_id: str
    t: float = Field(ge=0, le=600)
    position: tuple[float, float, float]


class DirectorData(Schema):
    template: str
    objects: list[StageObject] = Field(max_length=50)
    keyframes: list[Keyframe] = Field(max_length=1000)
    fov: float = Field(ge=10, le=120)

    @model_validator(mode="after")
    def references(self):
        ids = {o.id for o in self.objects}
        if len(ids) != len(self.objects) or any(k.object_id not in ids for k in self.keyframes):
            raise ValueError("摆位对象与关键帧引用不合法")
        return self


class SceneInput(Schema):
    id: str | None = Field(default=None, max_length=36)
    title: str = Field(default="新的分镜", min_length=1, max_length=100)
    shot_type: Literal["远景", "全景", "中景", "近景", "特写"] = "中景"
    camera_move: Literal["固定", "缓推", "拉远", "摇镜", "缓慢横移", "跟随"] = "固定"
    duration_sec: float = Field(default=5, ge=3, le=10)
    image_prompt: str = Field(default="", max_length=2000)
    video_prompt: str = Field(default="", max_length=2000)
    dialogue: str = Field(default="", max_length=1000)
    narration: str = Field(default="", max_length=1000)
    director_data: DirectorData | None = None
    model: str = Field(default="turbo", max_length=100)
    seed: str = Field(default="", max_length=32)


class CharacterInput(Schema):
    id: str | None = Field(default=None, max_length=36)
    name: str = Field(min_length=1, max_length=50)
    age: str = Field(default="", max_length=8)
    description: str = Field(default="", max_length=1000)
    clothing: str = Field(default="", max_length=500)
    voice: str = Field(default="女声 · 冷静", max_length=32)
    voice_id: str | None = Field(default=None, max_length=100)
    image: str = Field(default="", max_length=8000000)
    consistency: Literal["参考图模式"] = "参考图模式"


class ExportSettings(Schema):
    source_mode: Literal["auto", "storyboard"] = "auto"
    bgm_asset_id: str | None = None
    resolution: Literal["source", "480P", "768P", "1080P", "2K", "4K", "720p", "1080p"] = "source"
    fit_mode: Literal["pad", "crop"] = "pad"
    timing_mode: Literal["source", "planned"] = "source"
    fps: Literal[24, 30] = 24
    format: Literal["MP4", "WebM"] = "MP4"
    subtitles: bool = True
    music: bool = False
    mood: Literal["悬疑", "温情", "热血", "轻快"] = "悬疑"
    watermark: bool = False
    intro: bool = False
    transition: Literal["cut", "fade"] = "cut"


class ProjectInput(Schema):
    id: str | None = Field(default=None, max_length=36)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    style: str = Field(default="电影写实", max_length=2000)
    ratio: Literal["9:16", "16:9", "1:1"] = "9:16"
    export_settings: ExportSettings | None = None
    scenes: list[SceneInput] = Field(default_factory=list, max_length=24)
    characters: list[CharacterInput] = Field(default_factory=list, max_length=20)


class ScriptInput(Schema):
    idea: str = Field(min_length=1, max_length=2000)
    scene_count: int = Field(default=12, ge=8, le=24)
    duration_sec: float = Field(default=60, ge=24, le=240)

    @model_validator(mode="after")
    def duration(self):
        if not 3 <= self.duration_sec / self.scene_count <= 10:
            raise ValueError("每镜时长必须在 3–10 秒")
        return self


class OutlineCharacter(Schema):
    name: str
    age: str = ""
    persona: str = ""
    clothing: str = ""


class OutlineScene(Schema):
    title: str
    summary: str


class Outline(Schema):
    logline: str
    synopsis: str
    themes: list[str]
    characters: list[OutlineCharacter]
    scenes: list[OutlineScene] = Field(min_length=1, max_length=24)


class GeneratedScript(Schema):
    scenes: list[SceneInput] = Field(min_length=1, max_length=24)


class Batch(Schema):
    project_id: str
    scene_ids: list[str] = Field(min_length=1, max_length=24)
    kind: Literal["image", "video", "tts"]


class VideoRetake(Schema):
    source_asset_id: str | None = None
    preserve: str = Field(default="", max_length=1000)
    modify: bool = False
    expected: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=1000)
    nonce: str = Field(pattern=r"^[A-Za-z0-9_-]{8,128}$")

    @model_validator(mode="after")
    def reason_required(self):
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("单镜重做必须填写具体问题和修正原因")
        return self


class Order(Schema):
    ids: list[str] = Field(max_length=24)


class Pause(Schema):
    paused: bool


class TTSInput(Schema):
    project_id: str
    text: str = Field(default="总有人，在等一封信。", min_length=1, max_length=10000)
    voice_id: str = Field(default="female-shaonv", max_length=100)


class AIInput(Schema):
    project_id: str
    scene_id: str
    director_data: DirectorData | None = None


class TextResult(Schema):
    text: str = Field(min_length=1, max_length=2000)


class UploadData(Schema):
    project_id: str
    data_url: str = Field(max_length=8000000)
    kind: Literal["reference", "cover"] = "reference"
