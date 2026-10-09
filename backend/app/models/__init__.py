from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import String, ForeignKey, JSON, DateTime, UniqueConstraint, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def uid():
    return uuid4().hex


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


J = JSON().with_variant(JSONB, "postgresql")


class Project(Base):
    __tablename__ = "project"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(default="local-user")
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(default="")
    style: Mapped[str] = mapped_column(default="电影写实")
    ratio: Mapped[str] = mapped_column(default="9:16")
    status: Mapped[str] = mapped_column(default="草稿")
    cover_key: Mapped[str | None]
    outline: Mapped[dict | None] = mapped_column(J)
    export_settings: Mapped[dict | None] = mapped_column(J)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    creative: Mapped[dict | None] = mapped_column(J)


class Scene(Base):
    __tablename__ = "scene"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), index=True)
    order_index: Mapped[int]
    title: Mapped[str] = mapped_column(default="新的分镜")
    shot_type: Mapped[str] = mapped_column(default="中景")
    camera_move: Mapped[str] = mapped_column(default="固定")
    duration_sec: Mapped[float] = mapped_column(default=5.0)
    image_prompt: Mapped[str] = mapped_column(default="")
    video_prompt: Mapped[str] = mapped_column(default="")
    dialogue: Mapped[str] = mapped_column(default="")
    narration: Mapped[str] = mapped_column(default="")
    status: Mapped[str] = mapped_column(default="draft")
    model: Mapped[str] = mapped_column(default="turbo")
    seed: Mapped[str] = mapped_column(default="")
    director_data: Mapped[dict | None] = mapped_column(J)
    first_frame_key: Mapped[str | None]
    video_key: Mapped[str | None]
    audio_key: Mapped[str | None]
    narration_key: Mapped[str | None]
    audio_duration_ms: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None]
    __table_args__ = (UniqueConstraint("project_id", "order_index", name="uq_scene_order"),)

    creative: Mapped[dict | None] = mapped_column(J)


class Character(Base):
    __tablename__ = "character"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), index=True)
    name: Mapped[str]
    age: Mapped[str] = mapped_column(default="")
    description: Mapped[str] = mapped_column(default="")
    clothing: Mapped[str] = mapped_column(default="")
    voice: Mapped[str] = mapped_column(default="女声 · 冷静")
    voice_id: Mapped[str] = mapped_column(default="female-shaonv")
    image_key: Mapped[str | None]
    consistency: Mapped[str] = mapped_column(default="参考图模式")

    creative: Mapped[dict | None] = mapped_column(J)


class Task(Base):
    __tablename__ = "task"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), index=True)
    scene_id: Mapped[str | None] = mapped_column(ForeignKey("scene.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str]
    status: Mapped[str] = mapped_column(default="queued", index=True)
    progress: Mapped[int] = mapped_column(default=0)
    provider: Mapped[str | None]
    provider_task_id: Mapped[str | None]
    dedupe_key: Mapped[str] = mapped_column(index=True)
    payload: Mapped[dict] = mapped_column(J, default=dict)
    result: Mapped[dict | None] = mapped_column(J)
    logs: Mapped[list] = mapped_column(J, default=list)
    attempts: Mapped[int] = mapped_column(default=0)
    cost_cents: Mapped[int] = mapped_column(default=0)
    estimated_cost_cents: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index(
            "uq_active_scene_kind",
            "scene_id",
            "kind",
            unique=True,
            postgresql_where=text("status IN ('queued','running')"),
            sqlite_where=text("status IN ('queued','running')"),
        ),
    )


class Asset(Base):
    __tablename__ = "asset"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str]
    object_key: Mapped[str] = mapped_column(unique=True)
    content_type: Mapped[str]
    size_bytes: Mapped[int]
    duration_ms: Mapped[int | None]
    width: Mapped[int | None]
    height: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ExportJob(Base):
    __tablename__ = "export_job"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(default="queued")
    progress: Mapped[int] = mapped_column(default=0)
    settings: Mapped[dict] = mapped_column(J)
    output_key: Mapped[str | None]
    cover_key: Mapped[str | None]
    subtitle_key: Mapped[str | None]
    duration_sec: Mapped[float | None]
    cost_cents: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None]
    logs: Mapped[list] = mapped_column(J, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Cleanup(Base):
    __tablename__ = "storage_cleanup"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    keys: Mapped[list] = mapped_column(J)


class Revision(Base):
    __tablename__ = "creative_revision"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), index=True)
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str]
    data: Mapped[dict] = mapped_column(J)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Candidate(Base):
    __tablename__ = "creative_candidate"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), index=True)
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str]
    fingerprint: Mapped[str]
    task_id: Mapped[str | None] = mapped_column(ForeignKey("task.id", ondelete="SET NULL"))
    data: Mapped[dict] = mapped_column(J)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class LibraryCharacter(Base):
    __tablename__ = "library_character"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str]
    data: Mapped[dict] = mapped_column(J)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
