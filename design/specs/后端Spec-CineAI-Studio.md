# CineAI Studio — 后端开发 Spec（Phase B1）

> 2026-09-22 更新：角色资产、三阶段确认、逐句配音和版本追溯以
> [创作流程改造与验收](./创作流程改造与验收.md) 为准。本文保留原型与 Phase B1 历史设计。

> 本文档面向后端开发与 AI 编码工具，描述「CineAI Studio」从纯前端 Demo 走向可运行后端的
> 第一阶段实现方案。**后端采用 Python 体系。**
>
> 关联文档：
> - [`AI短剧工作台-架构设计.md`](./AI短剧工作台-架构设计.md)（总体架构与五大模块）
> - [`前端Spec-CineAI-Studio.md`](./前端Spec-CineAI-Studio.md)（界面与交互规范）
> - [`../../DESIGN.md`](../../DESIGN.md)（设计规范与表述边界）
> - [`../../.env.example`](../../.env.example)（外部资源与密钥清单）
>
> 版本：v2.0（Python 技术栈） · 状态：待评审

---

## 0. 术语

| 术语 | 含义 |
| --- | --- |
| API 层 | FastAPI 应用，负责校验、编排、入队与查询 |
| Worker | Celery worker 进程，执行长耗时生成任务 |
| Provider | 外部能力的适配器（DeepSeek / gpt-image-2.5 / MiniMax / COS） |
| 分镜 / Scene | 最小生成单元，对应前端 `Scene` 类型 |
| 首帧图 | 分镜的第一帧画面，图生视频的输入 |
| 静帧运镜片段 | 由首帧图 + ffmpeg `zoompan` 合成的动态片段，**不是 AI 视频生成** |

---

## 1. 现状与目标

### 1.1 前端现状（已完成，作为契约依据）

单仓 Next.js 16 + React 19 应用，纯前端演示，无任何网络请求。

| 关注点 | 现状实现 | 后端需替换为 |
| --- | --- | --- |
| 数据持久化 | Zustand `persist` → `localStorage`，键 `cineai-studio-v1` | PostgreSQL + FastAPI REST |
| 任务队列 | `AppShell` 每 700ms 调 `store.tick()`，两并发，进度 +8% | Celery + Worker + SSE |
| 剧本生成 | `Wizard.tsx` 用 `makeScenes()` 模板拼装 | DeepSeek 两段式生成 |
| 生图 | `tick()` 直接写回 `assets[0]` 占位图 | **gpt-image-2.5**（中转 mfttai.cc） |
| 生视频 | `tick()` 置为 `done` | 预留适配器（MiniMax H3，本期关闭） |
| 语音试听 | 浏览器 `speechSynthesis` | MiniMax TTS |
| 导出 | 浏览器 `MediaRecorder` 录制 **720p 无声 WebM** | 服务端 ffmpeg 合成 **MP4** |
| 密钥 | 无 | 仅存 Python 后端，前端不接触任何第三方 Key |

涉及的核心文件：

```text
src/lib/types.ts     Project / Scene / Character / Task / DirectorData 类型定义
src/lib/store.ts     全部状态变更动作（后端接口即按这些动作设计）
src/lib/data.ts      示例数据与 makeScenes / defaultStage 模板
src/lib/export.ts    浏览器端录制与文件下载（后端需提供替代路径）
src/features/*.tsx   七个页面的数据读写点
```

### 1.2 本期（Phase B1）范围

依据前端现状与 `.env.example` 已配置的外部资源，本期交付：

1. **数据持久化**：项目 / 角色 / 分镜 / 任务 / 资产入库，前端刷新与换设备后数据不丢失。
2. **剧本生成（真实）**：`一句话创意 → 大纲 → 分镜 JSON`，DeepSeek 两段式生成，流式展示阶段文案。
3. **首帧图生成（真实）**：调用 **gpt-image-2.5**（OpenAI 兼容，经 `https://mfttai.cc` 中转）文生图；
   通过角色参考图（`/v1/images/edits`）+ 全局风格前缀保证角色与画面一致性。
4. **AI 文本辅助（真实）**：`AI 优化` 画面 Prompt、`生成运镜描述`、AI 自动摆位（`directorData` 初值）。
5. **配音合成（真实）**：分镜台词 / 旁白 → MiniMax TTS → mp3 落 COS。
6. **异步任务队列**：生图 / 生视频 / 配音 / 合成四类任务的排队、并发、暂停、取消、重试、进度推送。
7. **对象存储**：首帧图、音频、成片、封面、角色参考图全部落腾讯云 COS，对外返回可访问 URL。
8. **合成导出（真实 MP4）**：服务端 ffmpeg 输出真实 MP4（详见 §7.2），替换浏览器 WebM 预演。
9. **成本护栏与估算**：生成前预估、生成后累计，任务详情可查看。

### 1.3 本期明确不做

| 项 | 原因 | 处理方式 |
| --- | --- | --- |
| MiniMax H3 视频生成 | 成本高 | 适配器接口 + 实现骨架，`FEATURE_VIDEO_GENERATION=false` 关闭，配置开启即可用 |
| 角色 LoRA 训练 | 需要训练流水线与 GPU | 前端 `consistency` 保留 `参考图模式`，`专属 LoRA` 继续禁用 |
| 用户体系 / 多租户 / 计费 | 本期为单用户工作台 | 预留 `project.owner_id` 字段，暂固定为 `local-user` |
| 3D 导演台轨迹 → 深度图控制信号 | 依赖视频模型 | 仅做「轨迹 → 运镜自然语言」的 prompt 增强 |
| 模板市场、协作、多集管理 | 非 MVP | 不做 |

### 1.4 本期产物形态

生图已接真实模型，因此画面是真实的 AI 生成图；视频模型未接入，故动态片段来源分两种：

```text
分镜首帧图（gpt-image-2.5 真实生成，落 COS）
   ├─ [本期] ffmpeg zoompan：按运镜方向做平移/推拉，生成 5–8s 动态片段
   └─ [B3]   MiniMax H3 图生视频（开关启用后自动切换）

动态片段 ─▶ 真实 TTS 配音 + 字幕烧录 + BGM 混音 ─▶ 真实 MP4 成片
```

> **表述边界（遵循 DESIGN.md）**：未接入视频模型时，产物命名为「分镜动态预演成片」，
> 属于**静帧运镜合成**，不得标称为「AI 生成的视频」。接入 H3 后，同一管线只需把片段来源
> 从 `zoompan` 换成真实视频文件，其余步骤不变。

---

## 2. 总体架构

### 2.1 选型

后端采用 **Python 体系**，与架构设计文档「FastAPI 便于后续自托管与 ffmpeg 深度处理」的建议一致：

| 层 | 选型 | 理由 |
| --- | --- | --- |
| API 层 | **FastAPI**（uvicorn/gunicorn） | 原生 async、SSE 友好、pydantic 校验、OpenAPI 自动文档 |
| 任务队列 | **Celery** + Redis | Python 生态标准；支持路由、重试、限流、路由到独立队列 |
| 消息 / 结果 / 广播 | **Redis 7** | 同时充当 Celery broker、result backend 与 Pub/Sub 广播 |
| ORM / 迁移 | **SQLAlchemy 2.0** + **Alembic** | 类型化模型，迁移可版本化 |
| 数据库 | **PostgreSQL 15+** | JSONB 存 `director_data` / `outline` |
| 媒体处理 | **ffmpeg**（subprocess） | 拼接/转场/字幕/混音/静帧运镜 |
| 对象存储 | **cos-python-sdk-v5** | 腾讯云 COS |
| HTTP 客户端 | **httpx**（async） | 调 DeepSeek / gpt-image-2.5 / MiniMax |
| 配置 | **pydantic-settings** | 启动即校验环境变量，fail-fast |

> 前端（Next.js）保持不变，只是把数据源从 `localStorage` 换成 HTTP + SSE。
> 这样也避免引入第二个 Web 框架，职责边界清晰：Next.js 管界面，FastAPI 管数据与生成。

### 2.2 架构图

```text
┌──────────────────────── 浏览器（Next.js 前端，已实现）────────────────────────┐
│  /  /new  /studio  /director  /queue  /export  /characters                    │
└───────────────┬──────────────────────────────────────┬───────────────────────┘
                │ REST(JSON)                            │ SSE(进度事件)
                │  ① 生产：FastAPI 与前端同源，nginx 反代 /api → :8000          │
                │  ② 开发：Next rewrites 或直连 http://127.0.0.1:8000          │
┌───────────────▼──────────────────────────────────────▼───────────────────────┐
│                    FastAPI（Python 3.12）· app/api/routers/*                   │
│  /api/projects  /api/scenes  /api/characters  /api/tasks  /api/tts             │
│  /api/exports   /api/assets  /api/ai/*        /api/projects/{id}/events        │
│  职责：pydantic 校验 · 鉴权占位 · 入队(.delay) · 查询 · Pub/Sub 转发            │
└───────┬─────────────────────────┬───────────────────────────┬─────────────────┘
        │ SQLAlchemy(asyncpg)     │ Celery broker/result      │ Redis Pub/Sub
┌───────▼────────┐      ┌─────────▼──────────┐       ┌────────▼────────────────┐
│  PostgreSQL    │      │  Redis 7           │◀──────│  Celery Worker          │
│  project       │      │  queues:           │       │  -Q script,tts,image    │
│  scene         │      │   script tts image │       │  -Q video,compose        │
│  character     │      │   video compose    │       │  ↳ httpx · ffmpeg        │
│  task          │      │  pubsub:           │       │  ↳ 进度写 DB + PUBLISH   │
│  asset         │      │   project:{id}:evt │       └────────┬────────────────┘
│  export_job    │      └────────────────────┘                │
└────────────────┘                                              │
        ▲                                                       ▼
        │                             ┌──────────────────────────────────────┐
        └───── 元数据 ────────────────│ 外部 Provider                         │
                                      │  DeepSeek(LLM)                        │
                                      │  gpt-image-2.5(中转 mfttai.cc)        │
                                      │  MiniMax(TTS / 视频预留)              │
                                      │  Tencent COS(媒体)                    │
                                      └──────────────────────────────────────┘
```

### 2.3 目录结构

```text
MyAIGCDemo/
├── src/                          # 前端（保持现状）
├── .env.example                  # 外部资源清单（本期含真实密钥）
├── .env.local                    # 本地/部署实际配置（gitignore）
└── backend/
    ├── pyproject.toml            # uv / poetry 管理依赖
    ├── alembic.ini
    ├── Dockerfile
    ├── alembic/versions/
    ├── app/
    │   ├── main.py               # FastAPI 实例、路由挂载、CORS
    │   ├── worker.py             # Celery app（队列路由、超时、重试策略）
    │   ├── core/
    │   │   ├── config.py         # pydantic-settings：读取 .env
    │   │   ├── db.py             # async engine / session
    │   │   ├── redis.py          # Pub/Sub 与进度通道
    │   │   ├── logging.py        # 结构化日志 + 脱敏
    │   │   └── errors.py         # 统一错误码与异常处理器
    │   ├── models/               # SQLAlchemy 2.0 模型
    │   ├── schemas/              # pydantic 请求/响应模型
    │   ├── api/routers/          # projects / scenes / tasks / tts / ...
    │   ├── services/             # 编排层（不直接读 env，不直接碰 SDK 细节）
    │   │   ├── script.py         # LLM 两段式编排
    │   │   ├── image.py          # gpt-image-2.5 调用
    │   │   ├── tts.py            # MiniMax TTS
    │   │   ├── compose.py        # ffmpeg 管线
    │   │   └── storage.py        # COS 上传/签名
    │   ├── providers/            # 外部能力适配器
    │   │   ├── llm/deepseek.py
    │   │   ├── image/gpt_image.py
    │   │   ├── tts/minimax.py
    │   │   ├── video/__init__.py , mock.py , minimax_h3.py
    │   │   └── storage/cos.py
    │   ├── tasks/                # Celery 任务：script / image / tts / video / compose
    │   └── prompts/              # 导演知识、风格模板、负面词
    └── tests/
```

### 2.4 与前端集成方式

| 场景 | 方案 |
| --- | --- |
| 开发 | 前端直连 `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000`；FastAPI 开启 CORS 允许 `http://127.0.0.1:3000` |
| 生产 | nginx 反代：`/api/*` → FastAPI `:8000`，前端与 API 同源，天然无 CORS 问题 |
| SSE | **建议直连 API 域名**，或确保 nginx 对该路径关闭 `proxy_buffering`，否则事件会被缓冲延迟 |
| 路径兼容 | 后端路由统一以 `/api` 为前缀，与前端现有 `src/lib/store.ts` 的调用路径对齐，前端无需改路径 |

### 2.5 后端实现约束

1. **分层**：Router（校验/编排）→ Service（业务）→ Provider（外部）。Provider 之外不出现 SDK 调用。
2. **密钥只在后端**：前端任何响应字段都不得包含 Key；日志打印前统一脱敏。
3. **异步优先**：API 层用 `async def` + `httpx.AsyncClient`；长耗时工作一律入队，不在请求内 `await`。
4. **不阻塞事件循环**：ffmpeg 用子进程（`asyncio.create_subprocess_exec` 或 Celery 内 `subprocess.run`）。
5. **配置即校验**：`app/core/config.py` 用 pydantic-settings 定义全部变量；缺少必填项启动即失败。
6. **可测试**：Provider 均以 `Protocol`/ABC 定义接口，测试用 Fake 实现，不打真实 API。

---

## 3. 数据模型

### 3.1 与前端类型对齐（重要契约）

前端 `src/lib/types.ts` 的字段必须被后端完整覆盖，且**保留原字段名**，把新增能力做成**增量字段**，
以便前端渐进迁移。

| 前端类型 | 后端承接方式 | 备注 |
| --- | --- | --- |
| `Project` | `project` 表 + `GET /api/projects` | `cover` 改为 COS URL；`updatedAt` 改为 ISO 字符串（前端需微调） |
| `Scene.image` | `scene.first_frame_key`（衍生 URL） | 响应仍返回 `image` 字段名，兼容前端渲染 |
| `Scene.status` | `scene.status` 枚举 | 见 §3.3 状态机 |
| `Scene.directorData` | `scene.director_data` JSONB | 结构不变 |
| `Scene.model` / `seed` | `scene.model_tier` / `scene.seed` | 用于生成参数与复现 |
| `Character.image` | `character.image_key` | 响应映射为 `image` |
| `Character.voice` / `voiceId` | `character.voice_label` / `voice_id` | 见 §4.3.3 音色映射 |
| `Task.type` | `task.kind` 英文枚举 | 响应同时返回 `type`（兼容旧值）+ `typeLabel`，见 §5.1 |
| `Task.progress` | `task.progress` 0–100 | 由 Celery 任务写回 |

### 3.2 数据库模型（SQLAlchemy 2.0 + Alembic）

```python
# backend/app/models/__init__.py
from datetime import datetime
from sqlalchemy import (JSON, DateTime, Float, ForeignKey, Index, Integer,
                        String, UniqueConstraint, func)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "project"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), default="local-user", index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(2000), default="")
    style: Mapped[str] = mapped_column(String(32), default="电影写实")
    ratio: Mapped[str] = mapped_column(String(8), default="9:16")      # 9:16 | 16:9 | 1:1
    status: Mapped[str] = mapped_column(String(16), default="草稿")     # 草稿 | 剪辑中 | 已导出
    cover_key: Mapped[str | None] = mapped_column(String(512))
    outline: Mapped[dict | None] = mapped_column(JSON)                 # 两段式 Pass 1 产物
    export_settings: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now(), onupdate=func.now())

    scenes: Mapped[list["Scene"]] = relationship(back_populates="project",
                                                 cascade="all, delete-orphan",
                                                 order_by="Scene.order_index")
    characters: Mapped[list["Character"]] = relationship(back_populates="project",
                                                         cascade="all, delete-orphan")


class Scene(Base):
    __tablename__ = "scene"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), index=True)
    order_index: Mapped[int] = mapped_column(Integer)                  # 镜号，从 0 开始
    title: Mapped[str] = mapped_column(String(100))
    shot_type: Mapped[str] = mapped_column(String(8), default="中景")
    camera_move: Mapped[str] = mapped_column(String(16), default="固定")
    duration_sec: Mapped[float] = mapped_column(Float, default=5.0)
    image_prompt: Mapped[str] = mapped_column(String(2000), default="")
    video_prompt: Mapped[str] = mapped_column(String(2000), default="")  # 运镜/动作提示词
    dialogue: Mapped[str] = mapped_column(String(1000), default="")
    narration: Mapped[str] = mapped_column(String(1000), default="")
    status: Mapped[str] = mapped_column(String(16), default="draft")
    model_tier: Mapped[str] = mapped_column(String(16), default="standard")  # standard | turbo
    seed: Mapped[str] = mapped_column(String(32), default="")
    director_data: Mapped[dict | None] = mapped_column(JSON)
    first_frame_key: Mapped[str | None] = mapped_column(String(512))
    video_key: Mapped[str | None] = mapped_column(String(512))
    audio_key: Mapped[str | None] = mapped_column(String(512))
    narration_key: Mapped[str | None] = mapped_column(String(512))
    last_error: Mapped[str | None] = mapped_column(String(1000))

    __table_args__ = (
        UniqueConstraint("project_id", "order_index", name="uq_scene_order"),
        Index("ix_scene_project_status", "project_id", "status"),
    )


class Character(Base):
    __tablename__ = "character"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(50))
    age: Mapped[str] = mapped_column(String(8), default="")
    description: Mapped[str] = mapped_column(String(1000), default="")
    clothing: Mapped[str] = mapped_column(String(500), default="")
    voice_label: Mapped[str] = mapped_column(String(32), default="女声 · 冷静")
    voice_id: Mapped[str] = mapped_column(String(64), default="male-qn-qingse")
    image_key: Mapped[str | None] = mapped_column(String(512))          # 参考图
    consistency: Mapped[str] = mapped_column(String(16), default="参考图模式")


class Task(Base):
    __tablename__ = "task"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)       # 同时作为 Celery task_id
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), index=True)
    scene_id: Mapped[str | None] = mapped_column(ForeignKey("scene.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(16))                      # image|video|tts|compose|script
    status: Mapped[str] = mapped_column(String(16), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    provider: Mapped[str | None] = mapped_column(String(32))
    provider_task_id: Mapped[str | None] = mapped_column(String(128))  # 视频类异步任务 ID
    dedupe_key: Mapped[str | None] = mapped_column(String(64), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(1000))
    logs: Mapped[list | None] = mapped_column(JSON)                    # 有限长度日志行
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_task_project_status", "project_id", "status"),)


class Asset(Base):
    __tablename__ = "asset"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(String(32), index=True)
    scene_id: Mapped[str | None] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(20))   # first-frame|video|audio|narration|cover|character-ref|export
    object_key: Mapped[str] = mapped_column(String(512), unique=True)
    url: Mapped[str | None] = mapped_column(String(1024))
    mime_type: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_asset_project_kind", "project_id", "kind"),)


class ExportJob(Base):
    __tablename__ = "export_job"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    settings: Mapped[dict] = mapped_column(JSON)     # resolution/fps/format/subtitles/music/mood/watermark/intro
    output_key: Mapped[str | None] = mapped_column(String(512))
    duration_sec: Mapped[float | None] = mapped_column(Float)
    cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

迁移：`alembic revision --autogenerate -m "init"` → `alembic upgrade head`。
`Asset` 与 `Scene`/`ExportJob` 通过 `object_key` 关联而非外键，以允许「先上传后绑定」的上传流程。

### 3.3 分镜状态机

沿用前端已有状态（`types.ts` 中已定义 `image_ready`）：

```text
draft ──enqueue(image)──▶ image_pending ──success──▶ image_ready
  ▲                              │                      │
  │                            fail                  enqueue(video)
  │                              ▼                      ▼
  └────────────────────────── failed ◀── fail ── video_pending
                                 │                      │
                              retry()                success
                                 │                      ▼
                                 └──────────────────▶ done
```

| 事件 | status 变化 | 附带写回 |
| --- | --- | --- |
| 入队生图 | `image_pending` | — |
| 生图成功 | `image_ready` | `first_frame_key`、`Asset(first-frame)` |
| 入队生视频 | `video_pending` | 要求 `first_frame_key` 非空 |
| 生视频成功 | `done` | `video_key` |
| 任务失败 | `failed` | `last_error` |
| 取消 / 重试 | 回退到 `draft` 或 `image_ready`（按是否有首帧图） | 与前端 `cancel()` / `retry()` 语义一致 |

推进规则（对应前端 `store.tick()` 中已有约束）：同一分镜同类型任务只允许一个
`queued|running`，重复入队返回 `409`。

---

## 4. 外部资源接入

适配器统一放在 `backend/app/providers/<capability>/`，Service 层只依赖抽象接口。

### 4.1 LLM · DeepSeek（本期启用）

| 项 | 值 |
| --- | --- |
| Base URL | `DEEPSEEK_BASE_URL`（默认 `https://api.deepseek.com`） |
| 路径 | `POST {BASE}/chat/completions`（OpenAI 兼容） |
| 模型 | `DEEPSEEK_MODEL`（`deepseek-flash`） |
| 鉴权 | `Authorization: Bearer ${DEEPSEEK_API_KEY}` |
| 可选 | `DEEPSEEK_REASONING_EFFORT`（low/medium/high，留空用服务端默认） |
| 客户端 | `httpx.AsyncClient`（不引入重型 SDK，便于统一超时/重试/脱敏） |

#### 4.1.1 两段式生成流程

```text
输入：idea, style, ratio, durationSec, sceneCount(自动/8/12/16), characters[]
  │
  ├─ Pass 1  大纲扩写 ──▶ { logline, synopsis, themes[], characters[{name, age, persona, clothing}],
  │                        scenes[{ title, summary }] }
  │
  └─ Pass 2  逐场拆分镜 ──▶ Scene[]  ← Prompt 约束 + JSON 模式 + pydantic 校验
```

#### 4.1.2 结构化输出策略

DeepSeek 支持 `response_format: {"type": "json_object"}`，但**不保证严格 Schema**，
因此采用「提示词约束 + JSON 模式 + pydantic 校验 + 一次修复重试」四道保险：

1. 在 system prompt 中给出**完整 JSON Schema** 与一个 few-shot 示例。
2. 请求体带 `response_format: {"type": "json_object"}`。
3. `Model.model_validate_json()` 校验；失败时把 `ValidationError` 摘要作为新消息追加，重试 1 次。
4. 仍失败则该任务标记 `failed`，保留原始响应片段到 `task.logs`，不污染已有分镜。

Pass 1 请求示例：

```python
# app/providers/llm/deepseek.py
resp = await client.post(
    f"{settings.deepseek_base_url}/chat/completions",
    headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
    json={
        "model": settings.deepseek_model,
        "response_format": {"type": "json_object"},
        "temperature": 0.8,
        "messages": [
            {"role": "system", "content": OUTLINE_SYSTEM_PROMPT},
            {"role": "user", "content": user_brief},
        ],
    },
    timeout=Timeout(connect=10, read=120),
)
```

Pass 2 输出的分镜 Schema（**与前端 `Scene` 字段一一对应**）：

```python
# app/schemas/script.py
class GeneratedScene(BaseModel):
    title: str = Field(max_length=50)
    shot_type: Literal["远景", "全景", "中景", "近景", "特写"]
    camera_move: Literal["固定", "缓推", "拉远", "摇镜", "缓慢横移", "跟随"]
    duration_sec: float = Field(ge=3, le=10)     # 与前端向导 3–10s 校验一致
    image_prompt: str
    dialogue: str = ""
    narration: str = ""


class GeneratedScript(BaseModel):
    scenes: list[GeneratedScene] = Field(min_length=1, max_length=24)
```

#### 4.1.3 Prompt 资产

导演知识（镜头语言模板、节奏模板、风格前缀与负面词）集中存放于 `backend/app/prompts/`：

```text
backend/app/prompts/
├── script_outline.py    # Pass 1 system prompt
├── script_scenes.py     # Pass 2 system prompt + JSON Schema
├── style_presets.py     # 6 种风格的 style_prefix 与 negative_words
├── camera_lexicon.py    # shot_type / camera_move → 镜头语言自然语言映射
├── optimize_prompt.py   # 「AI 优化」按钮
└── stage_layout.py      # AI 自动摆位（director_data 初值）
```

风格前缀必须**注入每个分镜的图片 prompt**，`negative_words` 按 §4.2.4 规则转换为正向排除描述，
实现架构文档要求的「全项目风格锁定」。

#### 4.1.4 工程要点

- **超时**：连接 10s / 读取 120s（Pass 1 与 Pass 2 可分别配置）。
- **重试**：仅对 429 / 5xx / 网络错误重试，指数退避 `1s→2s→4s`，最多 3 次。
- **流式**：`stream: true` 时用 `StreamingResponse` 把 chunk 转发给前端，用于向导页打字机阶段文案
  （`正在构思故事梗概…` / `正在拆分分镜（第 3/12 镜）…`）。
- **Token 预算**：生成前按 `sceneCount × 每镜预算` 估算，超过 `LLM_MAX_TOKENS_PER_JOB` 则分批生成
  （每批 6 镜）后合并。
- **幂等**：同一 `project_id + idea + style` 的重复提交走 `dedupe_key`，避免重复扣费。

### 4.2 图片生成 · gpt-image-2.5（本期启用）

| 项 | 值 |
| --- | --- |
| Base URL | `IMAGE_BASE_URL`（`https://mfttai.cc`，OpenAI 兼容中转） |
| 文生图 | `POST {BASE}/v1/images/generations` |
| 图生图 | `POST {BASE}/v1/images/edits`（`multipart/form-data`） |
| 模型 | `IMAGE_MODEL`（`gpt-image-2.5`） |
| 鉴权 | `Authorization: Bearer ${IMAGE_API_KEY}` |
| 尺寸 | `IMAGE_SIZE`（`1024x1536`） |
| 质量 | `IMAGE_QUALITY`（`low` / `medium` / `high`） |
| 返回 | `IMAGE_RESPONSE_FORMAT`（`b64_json` / `url`） |

> 中转服务与 OpenAI 官方 Images API **入参、出参完全一致**，因此 Provider 实现按官方规范编写，
> 后续更换中转域名或切回官方只需改 `IMAGE_BASE_URL` / `IMAGE_API_KEY`。

#### 4.2.1 请求与响应

```python
# app/providers/image/gpt_image.py
resp = await client.post(
    f"{settings.image_base_url}/v1/images/generations",
    headers={"Authorization": f"Bearer {settings.image_api_key}"},
    json={
        "model": settings.image_model,          # gpt-image-2.5
        "prompt": full_prompt,                  # style_prefix + 画面描述 + 排除项
        "n": settings.image_n,
        "size": settings.image_size,            # 1024x1536 / 1536x1024 / 1024x1024
        "quality": settings.image_quality,
        "response_format": settings.image_response_format,
    },
    timeout=Timeout(connect=10, read=settings.image_timeout_seconds),
)
# 兼容 b64_json 与 url 两种返回，统一拿到二进制后落 COS
item = resp.json()["data"][0]
raw = base64.b64decode(item["b64_json"]) if "b64_json" in item else await fetch_bytes(item["url"])
assert raw[:8] in (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1")  # 魔数校验
```

流程：**生成 → 魔数校验 → 上传 COS（`first-frame.png`）→ 写回 `scene.first_frame_key` + `Asset`**。

#### 4.2.2 尺寸映射（与项目画幅对齐）

| 项目 `ratio` | `IMAGE_SIZE` | 说明 |
| --- | --- | --- |
| `9:16`（默认竖屏短剧） | `1024x1536` | 导出时裁切/缩放到 1080×1920 |
| `16:9`（横屏电影） | `1536x1024` | 导出到 1920×1080 |
| `1:1` | `1024x1024` | 方形 |

#### 4.2.3 角色一致性策略（三层）

架构文档指出的最大难点，按成本递进使用：

1. **参考图模式（默认）**：把 `character.image_key` 对应图片作为参考图，调用
   `POST /v1/images/edits`（`multipart/form-data`，参考图字段 `image[]`）+ 画面 prompt，
   由模型保持人物外观。角色卡在 UI 上强制「先建角色卡，再生成分镜」。
2. **全局风格前缀**：`prompts/style_presets.py` 的 `style_prefix` 注入每个 prompt，锁定全片视觉。
3. **首帧链式约束**：同一场景的后续分镜，以前一镜首帧作为额外参考图，控制机位与光照连续性
   （注意参考图数量上限，超出时按优先级裁剪为 1–2 张）。

> 若中转服务对 `image[]` 数量或 `input_fidelity` 等参数有差异，在 Provider 内做能力探测并降级为
> 「纯文生图 + 风格前缀」，同时记录 `provider_capabilities` 到 `task.logs`。

#### 4.2.4 负面词处理

OpenAI Images API 没有 `negative_prompt` 参数，因此 `style_presets` 中的负面词
（如「文字、水印、多余手指、畸变」）需**转写为正向排除描述**追加到 prompt 末尾，
例如：`画面中不出现任何文字、水印、logo 或多余肢体，构图干净`。

#### 4.2.5 工程要点

- **超时**：`IMAGE_TIMEOUT_SECONDS`（默认 180s），出图比文本慢，不能沿用 LLM 的 120s。
- **重试**：仅 429 / 5xx / 超时重试 2 次，退避 `3s→9s`；内容被拒（content policy）不重试，直接失败。
- **并发**：`image` 队列默认并发 2（`WORKER_CONCURRENCY_IMAGE`），避免中转限流。
- **成本**：按张计费，写入 `task.cost_cents`；草稿用 `quality=low`，定稿 `high`。
- **幂等**：`dedupe_key = sha1(kind + scene_id + full_prompt + model + size + quality + seed)`，
  命中已成功的资产直接复用，不重复出图。

### 4.3 TTS · MiniMax Speech-2.8（本期启用）

| 项 | 值 |
| --- | --- |
| Base URL | `MINIMAX_TTS_BASE_URL`（`https://api.minimax.cn`） |
| 路径 | `POST {BASE}/v1/t2a_v2` |
| 模型 | `MINIMAX_TTS_MODEL`（`speech-2.8-hd`，低延迟可切 `speech-2.8-turbo`） |
| 默认音色 | `MINIMAX_TTS_VOICE_ID`（`male-qn-qingse`） |
| 输出格式 | `MINIMAX_TTS_AUDIO_FORMAT`（`mp3`） |
| 鉴权 | `Authorization: Bearer ${MINIMAX_API_KEY}` |
| 可选 | `MINIMAX_GROUP_ID`（部分账号需作为 `GroupId` 查询参数携带，空则不带） |

#### 4.3.1 请求体

```jsonc
// POST /v1/t2a_v2?GroupId=<MINIMAX_GROUP_ID 可选>
{
  "model": "speech-2.8-hd",
  "text": "末世第三年，我依然在送件。",
  "stream": false,
  "output_format": "hex",              // 直接返回 hex 音频，避免二次下载
  "subtitle_enable": false,
  "voice_setting": {
    "voice_id": "male-qn-qingse",
    "speed": 1.0,
    "vol": 1.0,
    "pitch": 0
  },
  "audio_setting": {
    "sample_rate": 32000,
    "bitrate": 128000,
    "format": "mp3",
    "channel": 1
  }
}
```

#### 4.3.2 响应处理

`data.audio` 为 **hex 字符串**（非 base64）：

```python
# app/providers/tts/minimax.py
payload = resp.json()
hex_audio = payload["data"]["audio"]              # hex，不是 base64
raw = bytes.fromhex(hex_audio)                    # → mp3 字节
key = f"projects/{project_id}/scenes/{scene_id}/audio/{task_id}.mp3"
await storage.put(key, raw, "audio/mpeg")
await db_update_scene(scene_id, audio_key=key)
```

同时兼容 `data.audio_file`（部分部署直接返回临时 URL）分支：若存在则先 `httpx` 下载再上传 COS，
保证产物最终落在自有存储。音色映射见 §4.3.3。

#### 4.3.3 音色映射表（前端标签 → MiniMax voice_id）

前端 `Character.voice` 是展示用中文标签，后端必须映射为 `voice_id`：

| 前端标签 | `voiceId` | 说明 |
| --- | --- | --- |
| `女声 · 冷静` | `female-shaonv` | 默认女主音色 |
| `女声 · 温柔` | `female-yujie` | |
| `男声 · 沉稳` | `male-qn-qingse` | 默认男主音色 |
| `男声 · 青年` | `male-qn-jingying` | |

实现为 `backend/app/providers/tts/voice_map.py`，并暴露
`GET /api/tts/voices` 返回「label + voiceId + 试听短音频 URL」。
具体 voice_id 需在接入时用 `GET {BASE}/v1/get_voice` 或控制台核对后固化。

#### 4.3.4 工程要点

- **文本长度**：单次请求文本上限按 `TTS_MAX_CHARS`（默认 2000）切分；超长台词按标点切段
  并行合成，再用 ffmpeg `concat` 合并音频。
- **试听接口**：`POST /api/tts/preview` 合成固定短句（如「总有人，在等一封信。」），
  结果按 `sha1(text + voice_id)` 缓存到 COS，命中直接返回 URL，避免重复扣费。
- **旁白与台词分开**：`narration` / `dialogue` 分别合成（`narration_key` / `audio_key`），
  便于 §7.4 的音画对齐分别处理。
- **静音兜底**：空字符串不发起请求；前端 `dialogue` 为空时不产生音频资产。

### 4.4 对象存储 · 腾讯云 COS（本期启用）

| 项 | 值 |
| --- | --- |
| SDK | `cos-python-sdk-v5` |
| AppId | `TENCENT_COS_APP_ID` |
| Bucket | `TENCENT_COS_BUCKET`（格式 `<bucketname>-<APPID>`） |
| Region | `TENCENT_COS_REGION`（`ap-nanjing`） |
| SecretId/Key | `TENCENT_SECRET_ID` / `TENCENT_SECRET_KEY`（**仅后端**） |
| SessionToken | `TENCENT_COS_SESSION_TOKEN`（仅 STS 临时密钥时需要） |
| 公网域名 | `TENCENT_COS_PUBLIC_BASE_URL` |
| CDN | 可选，`TENCENT_COS_CDN_BASE_URL` |

#### 4.4.1 objectKey 命名规范

```text
projects/{projectId}/cover.{ext}
projects/{projectId}/characters/{characterId}/ref.{ext}
projects/{projectId}/scenes/{sceneId}/first-frame.png
projects/{projectId}/scenes/{sceneId}/video.mp4
projects/{projectId}/scenes/{sceneId}/audio/{taskId}.mp3         # 台词
projects/{projectId}/scenes/{sceneId}/narration/{taskId}.mp3     # 旁白
projects/{projectId}/exports/{exportJobId}/output.mp4
projects/{projectId}/exports/{exportJobId}/subtitles.ass
projects/{projectId}/exports/{exportJobId}/cover.png
```

#### 4.4.2 上传与 URL 生成

```python
# app/providers/storage/cos.py
from qcloud_cos import CosConfig, CosS3Client

client = CosS3Client(CosConfig(
    Region=settings.tencent_cos_region,
    SecretId=settings.tencent_secret_id,
    SecretKey=settings.tencent_secret_key,
    Token=settings.tencent_cos_session_token or None,
))

async def put(key: str, body: bytes, content_type: str) -> str:
    await asyncio.to_thread(                                   # SDK 是同步的，放到线程池
        client.put_object,
        Bucket=settings.tencent_cos_bucket, Body=body, Key=key, ContentType=content_type,
    )
    return build_url(key)
```

`build_url()` 规则：优先 `TENCENT_COS_CDN_BASE_URL`，其次 `TENCENT_COS_PUBLIC_BASE_URL`；
若桶为私有读，则改为 `client.get_presigned_url(Method="GET", Key=key, Expired=7200)` 生成签名 URL。

#### 4.4.3 上传入口

前端角色参考图当前是 **base64 DataURL**（`FileReader.readAsDataURL`，≤1.2MB）。后端提供两种方式：

1. `POST /api/assets/upload`（`multipart/form-data`）：推荐，前端改为 `FormData` 提交。
2. 兼容旧流程：`POST /api/assets`（JSON `{ dataUrl }`）后端解码后上传，仅用于过渡期。

校验：白名单 `image/png|jpeg|webp`，单文件 ≤ `MEDIA_MAX_MB`（默认 5MB），超限返回 `413`。

> **注意**：`.env.example` 原有的 `公网访问域名=...`（含中文）不是合法环境变量名，
> 已修正为 `TENCENT_COS_PUBLIC_BASE_URL`，请勿再使用旧名。

### 4.5 视频生成 · MiniMax H3（本期不接入，仅预留）

视频能力以 Provider 抽象预留，`FEATURE_VIDEO_GENERATION=false` 时 `video` 队列走 Mock 实现。

```python
# app/providers/video/base.py
class VideoProvider(Protocol):
    id: str

    async def create(self, req: VideoRequest) -> str: ...          # 返回 provider_task_id

    async def query(self, provider_task_id: str) -> VideoStatus: ...  # queued|running|done|failed
```

| 实现 | 行为 |
| --- | --- |
| `MockVideoProvider`（本期默认） | 立即返回 `status=failed`/`fileUrl=None`，由合成管线走 §7.2 静帧运镜方案 |
| `MiniMaxH3Provider`（骨架已实现，flag 关闭） | `POST {MINIMAX_VIDEO_BASE_URL}{MINIMAX_VIDEO_CREATE_PATH}` 创建任务，`GET ...{QUERY_PATH}/{task_id}` 轮询；请求体使用 `model` + `content[]`（text/image）+ `duration` + `ratio`，创建后把 `task_id` 存入 `task.provider_task_id`，按 `MINIMAX_VIDEO_POLL_INTERVAL_MS`（3000ms）轮询，完成后下载视频落 COS |

开启方式：`FEATURE_VIDEO_GENERATION=true` + 填 `MINIMAX_API_KEY`，
业务代码与前端零改动。视频接口并发通常仅 1–3，限流与指数退避在 Celery 层统一实现。

### 4.6 成本护栏

1. **生成前预估**：`GET /api/projects/{id}/estimate` 按分镜数、出图张数、TTS 字数计算预估费用
   （**明确标注为估算值**，遵循 DESIGN.md 不虚构真实运营数字的要求）。
2. **开关**：`FEATURE_VIDEO_GENERATION` 默认关闭；`COST_HARD_LIMIT_CENTS` 超限直接拒绝入队（402）。
3. **档位**：草稿用 `turbo` / `quality=low`，定稿用 `standard` / `quality=high`
   （对应前端「模型档位」下拉）。
4. **累计**：每次任务完成写入 `task.cost_cents`，项目维度求和展示在队列页与导出页。

---

## 5. API 设计

### 5.1 通用约定

- 风格：REST + JSON；所有路径以 `/api` 开头；API 层不直连第三方。
- 校验：**pydantic v2** 模型定义在 `backend/app/schemas/`，FastAPI 自动注入并返回 422 结构。
- 响应：直接返回资源对象或数组，不额外包 `{ data }`（减少前端改动）。
- 错误：统一异常处理器输出

```json
{ "error": { "code": "SCENE_HAS_RUNNING_TASK", "message": "该分镜已有进行中的任务", "details": {} } }
```

- 时间：ISO 8601 字符串（`2026-09-22T10:00:00.000Z`）。
- 分页：`?cursor=<id>&limit=20`，响应含 `next_cursor`。
- `task.kind` 枚举：`image | video | tts | compose | script`；响应同时返回
  `type`（兼容前端旧值：`image→"图片"`、`video→"视频"`、`tts→"配音"`、`compose→"合成"`）
  与 `typeLabel`，前端可逐步切换到 `kind`。
- OpenAPI 文档由 FastAPI 自带（`/docs`、`/openapi.json`），作为前后端联调的单一事实来源。

### 5.2 接口清单

#### 项目

| 方法 | 路径 | 说明 | 对应前端动作 |
| --- | --- | --- | --- |
| GET | `/api/projects` | 列表（含 `status`/`q`/`sort` 过滤） | `projects` 初始数据 |
| POST | `/api/projects` | 创建（可由向导一次性带 `characters` 与生成参数） | `addProject` |
| GET | `/api/projects/{id}` | 详情（含 scenes / characters） | `useProject()` |
| PATCH | `/api/projects/{id}` | 改名 / 改梗概 / 改 style / ratio / exportSettings | `patchProject` |
| DELETE | `/api/projects/{id}` | 级联删除分镜与任务 | `removeProject` |
| POST | `/api/projects/{id}/copy` | 深拷贝项目 | `copyProject` |
| GET | `/api/projects/{id}/estimate` | 成本预估 | 导出页 / 队列页 |

#### 剧本与 AI 辅助

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/projects/{id}/script/generate` | 触发两段式生成；`Accept: text/event-stream` 时返回 SSE 阶段进度，否则返回 `taskId` |
| POST | `/api/ai/optimize-prompt` | 单镜画面 Prompt 优化（Studio「AI 优化」） |
| POST | `/api/ai/camera-description` | `director_data` → 运镜自然语言（「生成示例运镜描述」） |
| POST | `/api/ai/stage-layout` | 依据分镜描述生成 `director_data` 初值（「AI 自动摆位」） |

#### 角色

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/projects/{id}/characters` | 角色列表 |
| POST | `/api/projects/{id}/characters` | 新增 |
| PATCH | `/api/characters/{id}` | 编辑 |
| DELETE | `/api/characters/{id}` | 删除 |
| POST | `/api/characters/{id}/voice-preview` | 音色试听（合成固定短句） |

#### 分镜

| 方法 | 路径 | 说明 | 对应前端动作 |
| --- | --- | --- | --- |
| POST | `/api/projects/{id}/scenes` | 新增分镜 | `addScene` |
| PATCH | `/api/scenes/{id}` | 编辑（title/shot_type/camera_move/duration_sec/image_prompt/dialogue/narration/director_data/model/seed） | `patchScene` |
| DELETE | `/api/scenes/{id}` | 删除 | `removeScene` |
| POST | `/api/scenes/{id}/copy` | 复制 | `copyScene` |
| PATCH | `/api/projects/{id}/scenes/order` | 拖拽排序，body `{ ids: string[] }` | `reorderScene` |

#### 任务

| 方法 | 路径 | 说明 | 对应前端动作 |
| --- | --- | --- | --- |
| POST | `/api/tasks` | 批量入队，`{ projectId, sceneIds[], kind }` | `enqueue` |
| GET | `/api/projects/{id}/tasks` | 任务列表（队列页） | `tasks` |
| POST | `/api/tasks/{id}/retry` | 重试 | `retry` |
| POST | `/api/tasks/{id}/cancel` | 取消 | `cancel` |
| POST | `/api/projects/{id}/queue/pause` | 暂停/继续（body `{ paused }`） | `togglePause` |
| GET | `/api/projects/{id}/events` | **SSE** 事件流（任务与分镜状态） | 替代 `tick()` |

#### 资产 / TTS / 导出

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/assets/upload` | `multipart/form-data` 上传（角色参考图、封面） |
| GET | `/api/assets/{id}` | 元数据；`?redirect=1` 时 302 到 COS 签名 URL |
| GET | `/api/tts/voices` | 音色列表（label + voiceId + 试听 URL） |
| POST | `/api/tts` | 直接合成（`{ text, voiceId }`），返回 `{ url, durationMs }` |
| POST | `/api/projects/{id}/exports` | 创建导出任务，body 为导出设置 |
| GET | `/api/exports/{id}` | 导出进度与结果 URL |
| GET | `/api/health` | 存活探针（DB / Redis / ffmpeg / COS） |

### 5.3 关键接口示例

**入队生成（前端 `enqueue`）**

```http
POST /api/tasks
{ "projectId": "proj_1", "sceneIds": ["sc_1","sc_2"], "kind": "image" }
```

```jsonc
// 202 Accepted
{
  "queued": [
    { "id": "task_1", "projectId": "proj_1", "sceneId": "sc_1", "kind": "image",
      "type": "图片", "typeLabel": "生图", "status": "queued", "progress": 0,
      "createdAt": "2026-09-22T10:00:00.000Z" }
  ],
  "rejected": [ { "sceneId": "sc_3", "code": "SCENE_HAS_RUNNING_TASK" } ]
}
```

**SSE 事件流（替代 `tick()` 轮询）**

```http
GET /api/projects/proj_1/events
Accept: text/event-stream
```

```text
event: task
data: {"id":"task_1","sceneId":"sc_1","kind":"image","status":"running","progress":48}

event: scene
data: {"id":"sc_1","status":"image_ready","image":"https://cos.../first-frame.png"}

event: task
data: {"id":"task_1","sceneId":"sc_1","kind":"image","status":"done","progress":100}

event: ping
data: {"ts":1790000000000}
```

- 实现：`StreamingResponse` 订阅 Redis channel `project:{id}:events`，把事件按 SSE 格式产出。
- 15s 无事件发送 `ping` 保持连接；`request.is_disconnected()` 时清理订阅。
- 前端在 `EventSource` 断线后按 3s 退避重连，并用 `GET /api/projects/{id}/tasks` 做全量对账。

**创建导出**

```jsonc
POST /api/projects/proj_1/exports
{
  "resolution": "1080p",   // 720p | 1080p | 2K
  "fps": 24,               // 24 | 30
  "format": "MP4",         // MP4 | WebM
  "subtitles": true,
  "music": false,
  "mood": "悬疑",
  "watermark": false,
  "intro": false
}
```

```jsonc
// 200 → 同时写回 project.export_settings，并创建 kind=compose 的 Task
{ "exportJobId": "exp_1", "taskId": "task_9", "status": "queued" }
```

### 5.4 错误码

| HTTP | code | 说明 |
| --- | --- | --- |
| 400 | `VALIDATION_ERROR` | pydantic 校验失败，`details` 含字段错误 |
| 400 | `SCENE_DURATION_OUT_OF_RANGE` | 单镜时长不在 3–10s（与前端向导同规则） |
| 402 | `COST_LIMIT_EXCEEDED` | 超出成本硬上限 |
| 403 | `FEATURE_DISABLED` | `FEATURE_VIDEO_GENERATION` 等开关关闭 |
| 404 | `RESOURCE_NOT_FOUND` | 项目/分镜/任务不存在 |
| 409 | `SCENE_HAS_RUNNING_TASK` | 同分镜已有排队/运行中任务 |
| 409 | `FIRST_FRAME_REQUIRED` | 未生成首帧图即请求生视频 |
| 413 | `PAYLOAD_TOO_LARGE` | 上传超 `MEDIA_MAX_MB` |
| 422 | `PROVIDER_OUTPUT_INVALID` | LLM 输出经修复后仍不符合 Schema |
| 429 | `RATE_LIMITED` | 触发限流，响应带 `Retry-After` |
| 502 | `PROVIDER_ERROR` | 第三方返回错误（消息脱敏后透出） |
| 504 | `PROVIDER_TIMEOUT` | 第三方超时 |

---

## 6. 任务队列与进度推送（Celery）

### 6.1 队列划分

`backend/app/worker.py` 中通过 `task_routes` 把任务路由到独立队列，每类队列用独立
worker 进程控制并发：

| Queue | Celery task | 并发（默认） | 超时（soft/hard） | 重试 |
| --- | --- | --- | --- | --- |
| `script` | `tasks.script.generate_script` | 2 | 150s / 180s | 3，指数退避 |
| `tts` | `tasks.tts.synthesize` | 3 | 80s / 90s | 3 |
| `image` | `tasks.image.generate_first_frame` | 2 | 150s / 180s | 2 |
| `video` | `tasks.video.generate_clip` | 1 | — / 600s | 2 |
| `compose` | `tasks.compose.export_project` | 1 | — / 900s | 1 |

```bash
# 启动方式（每类任务独立 worker，便于按需扩缩容与限流）
celery -A app.worker worker -Q image   -c 2 -n image@%h
celery -A app.worker worker -Q tts     -c 3 -n tts@%h
celery -A app.worker worker -Q script,compose -c 1 -n main@%h
```

```python
# app/worker.py
celery = Celery("cineai", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.update(
    task_routes={"tasks.image.*": {"queue": "image"}, "tasks.tts.*": {"queue": "tts"},
                 "tasks.video.*": {"queue": "video"}, "tasks.compose.*": {"queue": "compose"},
                 "tasks.script.*": {"queue": "script"}},
    task_acks_late=True,                  # Worker 崩溃时任务可被重新投递
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,         # 长任务不做预取，保证公平
    result_expires=86400,
    timezone="Asia/Shanghai",
)
```

### 6.2 任务生命周期

```text
API 校验 → 写 Task(queued) → celery.send_task(name, args, task_id=task.id, queue=...)
   → Worker 取任务 → Task(running, started_at) → 阶段化进度写回
   → 成功：落资产 → 更新 Scene/Project → Task(done, finished_at)
   → 失败：attempts++ → attempts < max_attempts ? 退避重试 : Task(failed, error)
```

- **task_id 复用**：Celery `task_id` 直接使用数据库 `task.id`，天然去重，且可用
  `AsyncResult(task_id).state` 查询。
- **进度上报**：

```python
# app/core/progress.py
def report(task: Task, progress: int, message: str | None = None, **extra) -> None:
    db_update_task(task.id, progress=progress)
    redis.publish(f"project:{task.project_id}:events", json.dumps({
        "event": "task",
        "data": {"id": task.id, "sceneId": task.scene_id, "kind": task.kind,
                 "status": "running", "progress": progress, "message": message, **extra},
    }, ensure_ascii=False))
```

   同时调用 `self.update_state(state="PROGRESS", meta={"progress": progress})`，
   使非 SSE 客户端也能通过 `AsyncResult` 查到进度。

- 完成后额外发 `scene` 事件，前端收到即更新分镜卡片，无需轮询。

### 6.3 幂等、取消、暂停与重试

- **幂等**：`dedupe_key = sha1(kind + scene_id + image_prompt + model_tier + seed + provider_id)`。
  入队前查库：若已有同 key 且 `status=done`，直接返回原资产 URL，不重复扣费。
- **重试**：

```python
@celery.task(bind=True, autoretry_for=(TransientProviderError,),
             retry_backoff=True, retry_backoff_max=60, retry_jitter=True, max_retries=3)
def generate_first_frame(self, task_id: str) -> None: ...
```

  仅 `TransientProviderError`（网络 / 429 / 5xx / 超时）自动重试；
  `VALIDATION_ERROR` / `PROVIDER_OUTPUT_INVALID` 不重试，直接置 `failed`。
- **取消**：
  - `queued`：`celery.control.revoke(task_id, terminate=False)` 并置 `cancelled`。
  - `running`：置 Redis 标志 `cancel:{task_id}=1`，Worker 在阶段检查点读到后主动抛出
    `CancelledError` 并捕获为 `cancelled`；视频类再额外 `revoke(terminate=True)`。
- **暂停 / 继续**（对应前端 `togglePause()`）：Celery 无原生队列暂停，采用「停止消费 + 标志位」：

```python
# 暂停：停止从队列拉取新任务，运行中的任务不受影响
celery.control.cancel_consumer("image")
celery.control.cancel_consumer("tts")
# 继续
celery.control.add_consumer("image", destination=None)
```

  同时写 Redis `queue:paused=1`，供 `/api/projects/{id}/queue/pause` 与队列页文案读取。
- **死信**：超过 `max_attempts` 的任务保留在 DB（`failed`），不自动清理，供队列页查看日志。

### 6.4 进度推送

- 单一事件入口 `GET /api/projects/{id}/events`（SSE），避免前端多条长连接。
- 事件类型：`task`、`scene`、`export`（合成阶段：`生成配音 → 拼接分镜 → 烧录字幕 → 混音`，
  与前端导出页阶段文案一致）、`ping`。
- 服务端限制：每项目最多 5 条并发 SSE 连接；超出返回 `429`。
- 断线重连：前端 `EventSource` 自动重连，重连成功后调用
  `GET /api/projects/{id}/tasks` 与 `GET /api/projects/{id}` 全量对账，防止丢事件。
- Redis Pub/Sub 的局限：消息不持久化。若要求「离线期间的事件也不丢」，改用
  Redis Stream（`XADD` / `XREAD` + `last_id` 断点续传），本期 Pub/Sub 足够。

---

## 7. 合成导出管线（ffmpeg）

### 7.1 标准管线（架构文档模块 4 的落地）

```text
各分镜片段（真实视频 或 静帧运镜片段）
  ├─ 1. 转码对齐：统一 resolution / fps / SAR / 立体声 48kHz
  ├─ 2. 时长对齐：按 duration_sec 裁剪或补帧（见 §7.4）
  ├─ 3. 拼接：concat demuxer（硬切）或 xfade（叠化/黑场）
  ├─ 4. 配音：dialogue 音频按时间轴 adelay 对位；narration 独立音轨
  ├─ 5. 字幕：dialogue → ASS/SRT → subtitles 滤镜烧录（可开关）
  ├─ 6. BGM：amix + sidechaincompress 自动闪避（ducking，可开关）
  ├─ 7. 片头片尾 / 水印（可开关）
  ├─ 8. 封面：取首镜首帧或指定帧 → PNG
  └─ 9. 上传 COS → ExportJob(done, output_key)
```

关键命令骨架（示意，实际由 `services/compose.py` 的 `build_ffmpeg_args()` 生成）：

```bash
# 统一转码（每镜）
ffmpeg -i scene_03.mp4 -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=24,setsar=1" \
       -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -c:a aac -ar 48000 -ac 2 scene_03.norm.mp4

# 硬切拼接
ffmpeg -f concat -safe 0 -i list.txt -c copy merged.mp4

# 混音（配音 + BGM 闪避）
ffmpeg -i merged.mp4 -i voice.m4a -i bgm.mp3 \
  -filter_complex "[1:a]adelay=1200|1200[vo];[2:a]volume=0.35[bg];\
                   [bg][vo]sidechaincompress=threshold=0.05:ratio=8[bgd];\
                   [vo][bgd]amix=inputs=2:duration=first:dropout_transition=0[aout]" \
  -map 0:v -map "[aout]" -c:v copy -c:a aac -b:a 192k mixed.mp4

# 字幕烧录
ffmpeg -i mixed.mp4 -vf "subtitles=subtitles.ass:fontsdir=./fonts" -c:a copy final.mp4
```

Python 侧以子进程调用，并用 `-progress pipe:1` 解析进度：

```python
proc = await asyncio.create_subprocess_exec(
    *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
)
async for line in proc.stdout:
    if line.startswith(b"out_time_ms="):
        report(export_task, progress=calc_progress(line))
```

### 7.2 静帧运镜降级方案（本期核心）

视频模型未接入时，用 `zoompan` 把首帧图变成有运镜的动态片段，保证**本期即可导出真实 MP4**：

```bash
# 缓慢推近（对应 camera_move = 缓推）
ffmpeg -loop 1 -i first-frame.png -t 5 \
  -vf "scale=2160:3840,zoompan=z='min(zoom+0.0008,1.25)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=120:s=1080x1920,fps=24" \
  -c:v libx264 -pix_fmt yuv420p segment.mp4
```

`camera_move` → ffmpeg 表达式映射：

| camera_move | 实现 |
| --- | --- |
| 固定 | 静态图，`zoompan` 恒定 z=1（可选轻微呼吸感） |
| 缓推 | z 由 1 → 1.25 线性增长 |
| 拉远 | z 由 1.25 → 1 |
| 缓慢横移 | x 由 0 → `iw-iw/zoom` |
| 摇镜 | x 单向平移 + 轻微 z 变化 |
| 跟随 | 依据 `director_data.actorTracks` 的位移方向做同步平移 |

> 由 `camera_move` + `director_data.cameraTrack.keyframes` 计算出实际平移/缩放曲线，
> 生成上表参数。这样 3D 导演台的摆位信息在本期就有真实产出价值。

> 命名与展现：产物在 UI 中标注为「分镜动态预演」，不标称 AI 视频（见 §1.4）。

### 7.3 导出设置映射

| 前端设置 | 映射 |
| --- | --- |
| `resolution` | 720p→`720x1280`(9:16)/`1280x720`(16:9)；1080p→`1080x1920`/`1920x1080`；2K→`1440x2560`/`2560x1440` |
| `fps` | 24 / 30，写入转码与 `zoompan` 的 `d` 参数 |
| `format` | MP4→`libx264 + aac`；WebM→`libvpx-vp9 + libopus` |
| `ratio` | 由项目 `ratio` 决定画布尺寸；字幕安全区随之调整 |
| `subtitles` | 开关 ASS 烧录 |
| `music` + `mood` | 从 `BGM_DIR` 选曲（悬疑/温情/热血/轻快），缺省静音 |
| `watermark` | 叠加 `public/assets/watermark.png`（`overlay` 滤镜，右下角） |
| `intro` | 拼接片头（`public/assets/intro.mp4`，不存在则跳过并记日志） |

### 7.4 音画对齐策略

架构文档指出的核心矛盾：片段长度 ≠ TTS 时长。本期策略：

1. **以音频为准（默认）**：先合成 TTS 得到实际时长 `audio_ms`，
   再让片段时长 = `max(duration_sec, audio_ms + 300ms 缓冲)`；
   差值在 ±15% 内用 `setpts` 变速，超出则用定格尾帧补足。
2. **垫片**：缺口 > 1.5s 时，尾部冻结末帧（`tpad=stop_mode=clone`）。
3. **裁剪**：视频长于音频过多时，从尾部裁剪，避免截断台词。
4. 对齐结果写入 `ExportJob` 日志，便于排查。

---

## 8. 前端接入改造清单

后端交付后，前端需改动（本清单用于跨端协同，不改变现有 UI 规范）：

### 8.1 store 动作 → API 映射

`src/lib/store.ts` 中的每个动作改为「乐观更新 + 调用 API + 失败回滚」：

| store 动作 | API |
| --- | --- |
| `addProject` | `POST /api/projects` |
| `patchProject` / `patchScene` | `PATCH /api/projects/{id}` · `PATCH /api/scenes/{id}` |
| `addScene` / `copyScene` / `removeScene` | `POST /api/projects/{id}/scenes` · `POST /api/scenes/{id}/copy` · `DELETE /api/scenes/{id}` |
| `reorderScene` | `PATCH /api/projects/{id}/scenes/order` |
| `saveCharacter` / `removeCharacter` | `POST·PATCH /api/characters` · `DELETE /api/characters/{id}` |
| `enqueue` / `retry` / `cancel` / `togglePause` | `/api/tasks*` |
| `tick` | **删除**，改由 SSE 驱动 |
| 向导 `生成分镜剧本` | `POST /api/projects/{id}/script/generate`（SSE） |
| `AI 优化` / `生成运镜描述` / `载入示例摆位` | `/api/ai/*` |
| `speak()`（语音试听） | `GET /api/tts/voices` + `<audio src>` |
| `recordPreview()`（浏览器录制） | 保留作为离线降级；在线改调 `POST /api/projects/{id}/exports` |
| `coverImage()`（封面导出） | 改为使用后端生成的 COS 封面 URL |

### 8.2 类型字段增量（`src/lib/types.ts`）

```ts
export type Scene = {
  /* …原有字段保持不变… */
  narration?: string;      // 新增：旁白
  videoPrompt?: string;    // 新增：视频提示词
  imageUrl?: string;       // 新增：首帧图 COS 地址（与 image 并存，image 保留兼容）
  videoUrl?: string;       // 新增：成片片段
  audioUrl?: string;       // 新增：台词配音
  lastError?: string;
};
export type Task = {
  /* …原有字段… */
  kind?: "image" | "video" | "tts" | "compose" | "script"; // 新增，逐步替代 type
  typeLabel?: string;
  provider?: string;
  costCents?: number;
};
export type Character = { /* …原有字段… */ voiceId?: string };
```

### 8.3 渐进迁移与开关

- 环境变量 `NEXT_PUBLIC_API_MODE=local|remote` 与 `NEXT_PUBLIC_API_BASE_URL`：
  `local` 维持现状（localStorage + Mock），`remote` 走 FastAPI。便于对照与回滚。
- 保留 `localStorage` 作为**离线缓存**：远程模式下拉取成功即覆盖缓存，写操作失败时不清空。
- `AppShell` 的「本地演示 · 自动保存」文案需随模式切换为「云端已同步」（保留 DESIGN.md
  不虚构状态的边界）。
- 导出页现有提示「真实视频、配音与混音将在后端接入后生成」在 B1 完成后更新为
  「服务端合成：真实配音与字幕，画面为分镜动态预演」。

---

## 9. 环境变量

### 9.1 `.env.example` 已配置（含真实密钥）

| 变量 | 本期 | 用途 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` | ✅ 启用 | 剧本与文本生成 |
| `DEEPSEEK_REASONING_EFFORT` | 可选 | 推理强度 |
| `IMAGE_API_KEY` / `IMAGE_BASE_URL` / `IMAGE_MODEL` | ✅ 启用 | **gpt-image-2.5 首帧图生成（中转 mfttai.cc）** |
| `IMAGE_SIZE` / `IMAGE_QUALITY` / `IMAGE_N` / `IMAGE_RESPONSE_FORMAT` / `IMAGE_TIMEOUT_SECONDS` | ✅ 启用 | 出图参数 |
| `MINIMAX_API_KEY` | ✅ 启用 | TTS 鉴权（**当前为空，需手动填写**） |
| `MINIMAX_TTS_BASE_URL` / `MINIMAX_TTS_MODEL` / `MINIMAX_TTS_VOICE_ID` / `MINIMAX_TTS_AUDIO_FORMAT` | ✅ 启用 | TTS |
| `MINIMAX_GROUP_ID` | 可选 | 部分账号需携带 |
| `MINIMAX_VIDEO_*` | ⛔ 预留 | H3 视频，flag 关闭 |
| `TENCENT_SECRET_ID` / `TENCENT_SECRET_KEY` | ✅ 启用 | COS 鉴权（**当前为空，需手动填写**） |
| `TENCENT_COS_APP_ID` / `TENCENT_COS_BUCKET` / `TENCENT_COS_REGION` | ✅ 启用 | COS 定位（Bucket 待填） |
| `TENCENT_COS_PUBLIC_BASE_URL` | ✅ 启用 | 素材公网域名（已由原名 `公网访问域名` 修正而来） |
| `TENCENT_COS_SESSION_TOKEN` | 可选 | 仅 STS 临时密钥 |
| `TENCENT_COS_CDN_BASE_URL` | 可选 | CDN 加速域名 |

> **密钥管理提示**：`.env.example` 现已按项目要求记录 `IMAGE_API_KEY` 与
> `DEEPSEEK_API_KEY` 的真实值，属于**有意为之**。若后续要开源或对外分发，
> 请先清空这两个字段，或将其迁移到不入库的 `.env.local`。
> 部署时后端通过 `pydantic-settings` 读取 `.env.local`，`.gitignore` 需包含该文件。

### 9.2 后端新增

```dotenv
# 数据与队列
DATABASE_URL=postgresql+asyncpg://cineai:cineai@localhost:5432/cineai
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# Worker 并发
WORKER_CONCURRENCY_SCRIPT=2
WORKER_CONCURRENCY_TTS=3
WORKER_CONCURRENCY_IMAGE=2
WORKER_CONCURRENCY_VIDEO=1
WORKER_CONCURRENCY_COMPOSE=1

# 功能开关（本期关闭视频）
FEATURE_VIDEO_GENERATION=false

# 媒体与限制
MEDIA_MAX_MB=5
TTS_MAX_CHARS=2000
FFMPEG_PATH=/usr/bin/ffmpeg
FFPROBE_PATH=/usr/bin/ffprobe
BGM_DIR=./public/assets/bgm
LLM_MAX_TOKENS_PER_JOB=60000
PROVIDER_TIMEOUT_MS=120000

# 成本护栏（单价默认 0 占位，避免虚构价格；接入后按实填写）
COST_HARD_LIMIT_CENTS=5000
COST_UNIT_PRICE_JSON={"llmPerMToken":0,"imagePerCall":0,"ttsPerKChar":0,"videoPerSec":0}

# 服务
APP_BASE_URL=http://127.0.0.1:3000      # 前端地址（CORS 白名单）
API_CORS_ORIGINS=http://127.0.0.1:3000
API_RATE_LIMIT_PER_MIN=120
```

### 9.3 配置加载与校验

```python
# backend/app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env.local", "../.env"), env_file_encoding="utf-8", extra="ignore",
    )
    deepseek_api_key: str
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"

    image_api_key: str
    image_base_url: str = "https://mfttai.cc"
    image_model: str = "gpt-image-2.5"
    image_size: str = "1024x1536"
    image_quality: str = "medium"
    image_n: int = 1
    image_response_format: str = "b64_json"
    image_timeout_seconds: int = 180

    redis_url: str = "redis://localhost:6379/0"
    database_url: str
    feature_video_generation: bool = False
    # …其余字段略


settings = Settings()   # 缺少必填项 → 启动即失败，不静默降级
```

`FEATURE_VIDEO_GENERATION=true` 但缺少 `MINIMAX_API_KEY` 时，在启动钩子中抛出明确错误。

---

## 10. 安全、成本与合规

1. **密钥隔离**：所有第三方 Key 仅在 Python 后端读取；Provider 模块不导入到任何可被前端调用的路径。
2. **CORS 收紧**：`API_CORS_ORIGINS` 只允许前端来源，生产同源部署时关闭通配。
3. **上传安全**：类型白名单、大小上限、随机化 objectKey、禁止可执行扩展名。
4. **限流**：按 IP + 项目维度限流（`API_RATE_LIMIT_PER_MIN`）；生成类接口更严格。
5. **输入过滤**：对 idea / prompt / 台词做长度与敏感词检查后再送第三方。
6. **错误脱敏**：第三方错误信息中的 Key、请求头一律过滤后再返回前端。
7. **成本**：`COST_HARD_LIMIT_CENTS` 硬拦截 + 生成前预估 + 草稿档位默认 `turbo` / `quality=low`。
8. **数据**：默认单用户 `owner_id=local-user`；删除项目级联删除任务与资产记录，
   并异步清理 COS 对象（失败仅记日志，不阻塞请求）。
9. **合规**：生成内容需保留来源与参数（`scene.model_tier` / `seed` / `task.provider` / `provider_task_id`），
   便于回溯；对外导出物不宣称未实际执行的能力。

---

## 11. 可观测性

- **日志**：结构化 JSON（`structlog` 或 `logging` + JSON formatter），字段
  `ts / level / module / task_id / project_id / provider / duration_ms`；密钥与完整 prompt 截断脱敏。
- **指标**：各队列 `waiting/active/failed` 数、任务成功率与 P95 耗时、第三方错误率、
  TTS 字符数、出图张数、ffmpeg 耗时；暴露 `/api/metrics`（`prometheus-client`）。
- **Celery 观测**：`flower` 作为可选面板（`celery -A app.worker flower`），仅内网访问。
- **健康检查**：`/api/health` 分别探测 DB、Redis、ffmpeg、COS（轻量 HEAD）。
- **告警**：`failed` 任务数突增、COS 上传失败率、第三方 401/429 触发告警。

---

## 12. 里程碑与验收

| 阶段 | 内容 | 验收标准 |
| --- | --- | --- |
| **B1.1 骨架与持久化** | FastAPI + SQLAlchemy + Alembic + 项目/角色/分镜 CRUD | 刷新、换浏览器后数据一致；`/docs` 可访问；`NEXT_PUBLIC_API_MODE=remote` 可用 |
| **B1.2 剧本生成** | DeepSeek 两段式 + SSE 阶段进度 | 输入 1 句话，产出 ≥8 个合法分镜（pydantic 通过）；向导显示 4 段阶段文案 |
| **B1.3 首帧图生成** | gpt-image-2.5 Provider + COS 落盘 | 批量生图后每镜有真实 AI 画面；参考图模式角色外观基本一致 |
| **B1.4 队列与进度** | Celery + Redis + SSE | 队列页进度实时更新；暂停/取消/重试生效 |
| **B1.5 配音** | MiniMax TTS + 音色映射 | 每镜台词生成 mp3，时长回写；音色试听可用 |
| **B1.6 合成导出** | ffmpeg 静帧运镜 + 字幕 + BGM | 导出一个 **真实 MP4**（≥30s，含画面/配音/字幕），可下载播放 |
| **B1.7 收尾** | 成本护栏、日志、健康检查、限流 | 估算可见、超限被拦、`/api/health` 全绿 |

**端到端验收用例**：新建项目输入「末世废土中，一个快递机器人学会了说谎…」→
生成 12 镜剧本 → 批量生图（gpt-image-2.5 真实出图）→ 批量配音（真实 TTS）→ 微调运镜 →
导出 1080p/24fps MP4（含硬字幕）→ 下载播放顺畅、音画基本同步。

---

## 13. 风险与开放问题

| # | 风险 / 问题 | 影响 | 建议 |
| --- | --- | --- | --- |
| 1 | `gpt-image-2.5` 经中转的**稳定性与限流策略未知** | 出图失败率、并发上限不可预期 | 先做 20 张压测确定安全并发；`image` 队列默认 2，失败退避重试 |
| 2 | 图生图参数（`image[]` 数量上限、`input_fidelity` 等）在中转端可能不一致 | 角色一致性效果不确定 | Provider 内做能力探测，不支持时降级为「纯文生图 + 风格前缀」，并记录到 `task.logs` |
| 3 | 视频模型成本高，暂不接入 | 无 AI 视频 | 采用 §7.2 静帧运镜；B3 开启 `FEATURE_VIDEO_GENERATION` 即可切换 |
| 4 | `MiniMax voice_id` 需与账号音色清单核对 | 音色映射表可能不准 | 接入时先调 `get_voice` / 控制台核对，`voice_map.py` 单点维护 |
| 5 | TTS 时长与镜头时长不一致 | 音画不同步 | §7.4 策略；必要时在 UI 提示「以音频为准」 |
| 6 | `.env.example` 有意记录了真实 Key | 开源/分发时泄露 | 已在文件头写明注意；开源前清空 `IMAGE_API_KEY` / `DEEPSEEK_API_KEY` |
| 7 | Celery 无原生「暂停队列」语义 | `togglePause` 实现依赖 `cancel_consumer` | 已给出实现方案；若后续要更精细控制，改用 Redis 标志 + 任务入口检查 |
| 8 | Redis Pub/Sub 消息不持久化 | 断线期间事件丢失 | 前端重连后全量对账；如需强一致改用 Redis Stream |
| 9 | COS 桶读权限策略未定 | 素材无法直连播放 | 明确「私有 + 签名 URL」或「公有读 + CDN」，二选一后在 §4.4 固化 |
| 10 | 前端 `Task.type` 中文枚举 | 与后端英文 `kind` 并存 | §5.1 双字段返回，前端按批次迁移 |
| 11 | 前后端分离带来 CORS / SSE 代理问题 | 开发期联调受阻 | 生产用 nginx 同源反代；SSE 路径关闭 `proxy_buffering` |

---

## 附录 A · 完整目录结构

```text
MyAIGCDemo/
├── src/                          # 前端：Next.js 16（保持现状，仅改数据源）
├── public/assets/                # 前端素材（含 BGM、水印、片头）
├── design/specs/                 # 本 Spec 与前端 Spec
├── .env.example                  # 外部资源清单（本期含真实密钥）
├── .env.local                    # 实际配置（gitignore）
└── backend/                      # Python 后端
    ├── pyproject.toml
    ├── Dockerfile
    ├── alembic.ini
    ├── alembic/versions/
    ├── app/
    │   ├── main.py               # FastAPI 实例 / 路由挂载 / CORS / 异常处理
    │   ├── worker.py             # Celery app：队列路由、超时、重试、task_routes
    │   ├── core/
    │   │   ├── config.py         # pydantic-settings
    │   │   ├── db.py             # async engine / session / Base
    │   │   ├── redis.py          # 连接池 + Pub/Sub 进度通道
    │   │   ├── logging.py        # 结构化日志 + 脱敏
    │   │   └── errors.py         # 错误码与全局异常处理器
    │   ├── models/               # SQLAlchemy 2.0 模型（§3.2）
    │   ├── schemas/              # pydantic v2 请求/响应
    │   ├── api/
    │   │   ├── deps.py           # 依赖注入（db session / pagination / 当前用户占位）
    │   │   └── routers/
    │   │       ├── projects.py  scenes.py  characters.py
    │   │       ├── tasks.py     exports.py  assets.py
    │   │       ├── tts.py       ai.py       events.py   # events 为 SSE
    │   │       └── health.py
    │   ├── services/             # 编排层
    │   │   ├── script.py  image.py  tts.py  compose.py  storage.py
    │   ├── providers/            # 外部能力适配器
    │   │   ├── llm/deepseek.py
    │   │   ├── image/gpt_image.py
    │   │   ├── tts/minimax.py , voice_map.py
    │   │   ├── video/base.py , mock.py , minimax_h3.py
    │   │   └── storage/cos.py
    │   ├── tasks/                # Celery 任务
    │   │   ├── script.py  image.py  tts.py  video.py  compose.py
    │   └── prompts/              # 导演知识 / 风格模板 / 负面词
    └── tests/
```

## 附录 B · 前后端共享契约

后端 pydantic 模型与前端 `src/lib/types.ts` 必须保持字段名一致（camelCase 由 FastAPI
`alias_generator=to_camel` 输出）。前端类型草案：

```ts
// src/lib/types.ts（增量，与后端 schemas 对齐）
export type TaskKind = "image" | "video" | "tts" | "compose" | "script";
export type TaskStatus = "queued" | "running" | "done" | "failed" | "cancelled";
export type LegacyTaskType = "图片" | "视频" | "配音" | "合成";

export type SseEvent =
  | { event: "task"; data: { id: string; sceneId: string | null; kind: TaskKind;
                            status: TaskStatus; progress: number; message?: string } }
  | { event: "scene"; data: { id: string; status: string; image?: string;
                             videoUrl?: string; audioUrl?: string } }
  | { event: "export"; data: { exportJobId: string; stage: string; progress: number } }
  | { event: "ping"; data: { ts: number } };
```

pydantic 侧对应：

```python
# app/schemas/task.py
class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_camel, populate_by_name=True)

    id: str
    project_id: str
    scene_id: str | None
    kind: Literal["image", "video", "tts", "compose", "script"]
    type: str | None            # 兼容字段：图片 / 视频 / 配音 / 合成
    type_label: str | None
    status: Literal["queued", "running", "done", "failed", "cancelled"]
    progress: int
    provider: str | None = None
    cost_cents: int = 0
    error: str | None = None
    created_at: datetime
```
