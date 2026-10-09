# Open-Source AI Short-Drama (AI短剧) Production Pipelines — Verified Landscape & Industry-Standard Reference Workflow

**Research date:** 2026-10 (all star counts / push dates captured from the GitHub REST API during this session)
**Method:** GitHub REST API (`/repos/{owner}/{repo}`, `/search/repositories`) + raw README fetches over `curl`.
**Verification rule applied:** every repo below was confirmed to exist via a successful API response returning `full_name`. Star counts are the live API values. Where a claim comes from a project's own README rather than independent verification, it is labelled as such.

> **Environment note:** the `web_fetch` tool was unusable in this session (github.com resolved to a non-public IP and was rejected by policy). All HTTP work was done with `curl` in `bash`, which worked normally. This did not reduce coverage — the GitHub REST API is a stronger source than HTML scraping.

---

## 0. Headline corrections to the candidate list

The task named several candidates. Three of them are **materially different from what the prompt assumed**, and this changes what the "industry standard" baseline should be:

| Candidate as given | Reality (verified) |
|---|---|
| `markthree/Jellyfish` | **Exists but is a 1-star stub.** ★1, 0 forks, 0 watchers, last push 2026-03-16, Apache-2.0. Its README's own Roadmap section lists *"章节拍摄工作台 — 完整分镜编辑、视频生成与预览流程"* as **进行中/规划中** (in-progress/planned) and the only ✅-complete items are front-end interaction shells. It also still contains placeholder links `https://github.com/your-org/jellyfish/issues`. **It is a UI scaffold, not an end-to-end pipeline.** The real project is **`Forget-C/Jellyfish` (★6,561)** — same logo, same screenshots, same English text, Apache-2.0. `markthree/Jellyfish` is a downstream copy/snapshot. |
| `waoowaoo` | The canonical repo is **`waooAI/waoowaoo` (★14,346)**. `saturndec/waoowaoo` (still referenced in its own README star-history badge) now **301-redirects** to it — verified via API redirect to repository id `1139782619`. **The project has pivoted and relicensed:** the current README describes a generic "AI creative workspace for images and videos" (canvas + right-hand assistant), explicitly says *"Music and voiceover controls are not included in this preview"*, and states it is licensed under **Elastic License 2.0 — "source-available software, not OSI-approved open source."** The 分集→配音→口型 pipeline only survives in the repo's *description* and in older forks such as `123Mr-king/waoowaoo` (★14). |
| `HBAI-Ltd/Toonflow-app` | **Confirmed and large.** ★16,312, 2,913 forks, MIT, TypeScript, last push 2026-10-01. |

**Also verified as non-existent / unverifiable:** `fudan-generative-ai/hallo` and `KwaiVGI/LivePortrait` returned no repo at those exact paths (LivePortrait's canonical owner differs). `Novella AI (~89★)` is claimed in `wind-comic`'s README but **I could not verify any such repo** — search for "novella drama" returned nothing matching. Treat that specific claim as unverified.

---

## 1. Tier A — Full end-to-end novel/idea → finished episode platforms

These are the projects that actually implement the whole chain. This is the core comparison set.

### 1.1 `Forget-C/Jellyfish` — the real Jellyfish (★6,561)

- **URL:** https://github.com/Forget-C/Jellyfish
- **Stats:** ★6,561 · forks 1,136 · Python (backend) + React/Vite (frontend) · created 2026-03-06 · last push 2026-07-30 · Apache-2.0
- **Stack:** FastAPI + MySQL + Redis + RustFS (S3-compatible), Docker Compose, OpenAPI-generated frontend client.

**Exact pipeline stages (from README):**

```
项目/章节管理 → 剧本输入 → 章节剧本拆解为分镜 (script breakdown)
  → 角色/场景/道具/服装/对白 抽取
  → 分镜筹备 (shot preparation): 抽取并刷新候选资产 → 采纳/忽略候选 → 关联已有实体 → 修正分镜基础信息
  → 统一 readiness 状态判定 shot ready
  → 生成工作台: 关键帧/参考图管理 → 视频提示词预览 → 单镜/批量预检 → 图/视频生成
  → 生成产物回写分镜与媒体系统
  → 异步任务中心 (状态/取消/耗时/跳回上下文)
```

The README states the main workflow explicitly as:
`script breakdown → shot preparation → candidate confirmation → shot ready → generation workspace`

**Automated vs manual:** LLM-driven breakdown and extraction are automated. **Candidate confirmation is an explicit human gate** — the system deliberately separates *"prepared"* from *"currently generating"*. Users accept/ignore asset and dialogue candidates and link existing entities.

**Cross-cutting handling:**
- (a) **Multi-episode:** chapter (章节) is the first-class unit for scripts, shots and generation; projects aggregate chapter stats.
- (b) **Character consistency:** a shared entity model across characters/actors, scenes, props and costumes, reusable at shot level; "check name existence" is used to *encourage reuse of existing assets* rather than creating duplicates — a genuinely good consistency mechanism.
- (c) **Shot/scene aggregation:** shots are the atomic unit; media is written back with shot+entity context preserved.
- (d) **Lip-sync:** **not present in the current README.** The UI-level feature appears only in the stale `markthree` copy ("智能对口型"). Do not credit Jellyfish with lip-sync.
- (e) **Cost control:** none documented.
- (f) **Human review gates:** strong — the candidate-confirmation + shot-readiness model is the most explicit review gate of any project surveyed.

### 1.2 `HBAI-Ltd/Toonflow-app` (★16,312)

- **URL:** https://github.com/HBAI-Ltd/Toonflow-app
- **Stats:** ★16,312 · forks 2,913 · TypeScript · created 2026-01-29 · last push 2026-10-01 · MIT
- **Shape:** cross-platform desktop app + local server (`http://127.0.0.1:3000`), infinite canvas, AI agents, visual workflows, MCP + plugin extensibility. Topics include `storyboarding`, `text-to-video`, `image-to-video`, `workflow-automation`, `node-based-editor`.

**Pipeline stages:** 剧本创作 → 资产管理 → 图像生成 → 视频生成 → 智能分镜, organized on an **infinite canvas** rather than a linear wizard. Reference to "LibTV"/"TapNow" canvas paradigms.

**Cost control — the single best-documented real cost figure in the whole survey:** the README publishes a worked case: 2-hour production, ~2-minute finished film, Seedance 2.0 (video) + GPT Image 2 (image) + Claude Opus 4.6 (text), **total model cost ≈ ¥130, split ≈ ¥10 language / ¥120 video / <¥1 image.** This is the empirical proof of where money actually goes: **video generation dominates (~92%).**

**Weaknesses:** no documented lip-sync stage, no documented episode/season hierarchy, no cost *pre-estimation* (only post-hoc reporting).

### 1.3 `chatfire-AI/huobao-drama` / 火宝短剧 (★15,627)

- **URL:** https://github.com/chatfire-AI/huobao-drama
- **Stats:** ★15,627 · forks 2,901 · Vue/Nuxt 3 · created 2026-01-05 · last push 2026-09-28 · license "Other" (custom — not OSI-standard)
- **Stack:** Nuxt 3 + Vue 3 / Hono + Drizzle + **Mastra AI agents** + better-sqlite3; Electron desktop build; FFmpeg bundled via npm.

**Exact pipeline (README "Visual Walkthrough", 6 steps):**
1. **新建项目** — aspect ratio (16:9 / 9:16, fixed after creation) + visual style (injected into every image prompt)
2. **配置 AI 服务**
3. **剧本阶段** — paste source novel → "AI Rewrite" → shooting script **split by episode** with scenes and characters annotated; switchable text model and tone
4. **资产阶段** — run extraction → character/scene/prop list → generate a consistent reference image for each (or batch). *"These images are injected as reference material when generating videos."*
5. **分镜与视频** — storyboard breakdown (AI splits shots + writes video prompts) → pick video model → review/tweak each shot prompt (`@character` refs map to reference images automatically) → Batch Generate Videos → one-click retry of failures
6. **合并导出** — select shots, "Start Merging", FFmpeg assembles the full episode; "Mark Done" lights the progress rail

**Four built-in Mastra agents (the cleanest named decomposition of any project):**

| Agent | Role |
|---|---|
| `script_rewriter` | Novel → formatted script rewriting |
| `extractor` | Intelligent extraction **and dedup** of characters / scenes / props |
| `storyboard_breaker` | Script → storyboard sequence breakdown |
| `prompt_generator` | Image prompts for characters/scenes/props + storyboard video prompts |

Agent skills live as `SKILL.md` files under `backend/workspace/skills/` and are **editable in the UI** — a practical pattern worth copying.

**Cross-cutting:**
- (a) **Multi-episode:** yes — episode list shows production status of every episode; "Enter Studio" to resume. Strongest episode-level UX of the Tier A set.
- (b) **Consistency:** reference images per asset injected as reference material (reference-conditioned, not a versioned identity model).
- (c) **Aggregation:** shot → episode via explicit selection and merge; supports **selective stitching** (validates video files exist before merging).
- (d) **Lip-sync:** **none.**
- (e) **Cost control:** none documented.
- (f) **Review gates:** light — per-shot prompt review before batch generation; "Mark Done" manual completion.

### 1.4 `HKUDS/ViMax` (★12,540) — HKU Data Intelligence Lab

- **URL:** https://github.com/HKUDS/ViMax
- **Stats:** ★12,540 · Python · created ~2026 · last push 2026-09-30 · **MIT** (most permissive of the large end-to-end projects)

**Three pipelines** (verified in `pipelines/`): `idea2video_pipeline.py`, `novel2movie_pipeline.py`, `script2video_pipeline.py`.

**The single most instructive artifact in this whole survey — the `agents/` directory, which is a literal ordered implementation of the pipeline:**

```
novel_compressor.py          → 长篇压缩 (long-form compression)
event_extractor.py           → 事件抽取
global_information_planner.py → 全局信息规划
character_extractor.py       → 角色抽取
character_portraits_generator.py → 角色定妆/肖像生成
scene_extractor.py           → 场景抽取
screenwriter.py              → 编剧
script_planner.py            → 剧本规划
script_enhancer.py           → 剧本增强
storyboard_artist.py         → 分镜
camera_image_generator.py    → 镜头画面(首帧)生成
reference_image_selector.py  → 参考图选择
best_image_selector.py       → 最佳图选择 (candidate selection!)
```

**Cross-cutting:**
- (a) **Multi-episode:** `novel2movie` explicitly does *"adapt long-form fiction into episodic visual narratives with narrative compression, character tracking, and scene planning."*
- (b) **Consistency:** "coordinate references, first frames, camera continuity" + **AutoCameo** (identity from a reference photo). `reference_image_selector` + `best_image_selector` = automated candidate selection.
- (c) **Aggregation:** parallelized generation of compatible shots; multi-scene multi-shot assembly.
- (d) **Lip-sync:** "Audio and Video Binding — synchronized storytelling"; character voice + SFX integrated. Not a dedicated lip-sync model stage.
- (e) **Cost control:** none documented.
- (f) **Review gates:** **Agent Loop + TUI** — "discuss ideas, revise plans, resume sessions, review text artifacts, and control rendering from one interactive workspace." Session reuse + context compaction. Web UI for inspecting artifacts/storyboard progress. Review is conversational rather than gated.

### 1.5 `calesthio/OpenMontage` (★62,087) — largest by stars, but NOT a short-drama tool

- **URL:** https://github.com/calesthio/OpenMontage
- **Stats:** ★62,087 · forks 7,918 · Python · created 2026-03-29 · last push 2026-09-06 · **AGPL-3.0** · 340 open issues

**Important scoping correction:** this is an *agentic general video production system* (12 pipelines: Animated Explainer, Animation, Avatar Spokesperson, Cinematic, Clip Factory, Documentary Montage, Hybrid, Localization & Dub, Podcast Repurpose, Screen Demo, Talking Head). **There is no short-drama / 分集 pipeline.** It is the reference for *production governance*, not for drama.

**Its canonical stage flow (applies to every pipeline):**
```
research -> proposal -> script -> scene_plan -> assets -> edit -> compose
```

**Why it matters for your comparison — it is by far the strongest on engineering governance:**
- **Human approval gates are enforced, not suggested:** proposal, script, scene plan, generated assets and publish all pause for sign-off. **The checkpoint writer rejects a "completed" gated stage without recorded approval**, and superseded checkpoints are archived so the audit trail survives revisions. This is the only project surveyed where a gate is enforced *in the state machine* rather than by convention.
- **Budget controls (the most mature cost model found):** **Estimate before execution → Reserve budget → Reconcile after**, with modes `observe` / `warn` / `cap`, **per-action approval above a threshold (default $0.50)**, and a **total budget cap (default $10)**. This is cost pre-estimation — the thing almost everyone else lacks.
- **Scored provider selection** — 7-dimension scoring: task fit 30%, output quality 20%, control features 15%, reliability 15%, cost efficiency 10%, latency 5%, continuity 5%. Winning provider + score logged with all alternatives considered.
- **Pre-compose validation** blocks render if the delivery promise is violated, slideshow-risk is critical, or renderer family is missing.
- **Post-render self-review** — ffprobe validation, frames at 4 positions checked for black frames/broken overlays, audio levels checked for silence/clipping, subtitle presence checked. **If review fails, the video is not presented.**
- **Decision audit trail** — every provider/style/music/voice/renderer choice and fallback logged with alternatives, confidence and reasoning.

### 1.6 `dramaclaw/dramaclaw` (★6,615)

- **URL:** https://github.com/dramaclaw/dramaclaw
- **Stats:** ★6,615 · forks 787 · Python · created 2026-03-27 · last push 2026-10-01 · license "Other" (Elastic 2.0 per third-party analysis; `wind-comic` notes "not FOSS")

**Pipeline — explicitly four phases: Ingest → Plan → Produce → Deliver.** Verified stages:
- **Structured ingest** — projects build episodes, characters and scenes straight from manuscript or screenplay (**Fountain supported**), "no knowledge graph or embeddings required"
- **Asset library & identity consistency** — characters/scenes/props/voices organised by purpose and folder; **stable identities across episodes**, character portraits and per-episode variants
- **Episode planning & script generation** — chapter segmentation, beat planning, multi-episode arcs; **adaptive / literal / staged script modes with review-and-repair loops**
- **Storyboards & first frames** — beat-driven stylized generation, **grid splitting, image-pool selection**
- **Voice-over, video composition & export** — emotion-aware speech, episode assembly, video + subtitle export and full asset pack
- **Visual Style** — upload a reference image to extract style parameters and apply across the whole project
- **Task Center** — status/progress/logs, **cancel / retry, resume-from-checkpoint for long runs; prerequisites validated before a job is queued**

**Standout architectural ideas (both unique in this survey):**
- **Director World — spatially consistent sets:** image → 3D Gaussian Splat set and scene-360 panoramas as canvas nodes — "a framable virtual set that locks spatial structure, character blocking and camera placement, so the same location stays consistent across shots." This is a genuinely different answer to scene consistency than reference-images.
- **Dual-track: canvas AND pipeline over one asset library** — "explore on the canvas, commit what works to the series, project the series back onto a canvas." Every stage is "an independent async task with its own interface. Run sequentially, skip steps, resume mid-way."
- **Previz stage** (in development): in-browser 3D blocking with character rigs/paths and a real lens/sensor camera model, capturing the framed shot straight into the next node.
- **MCP server** exposes DramaClaw to Claude Code / Codex.

**Real episodes published** (58-episode series shown), i.e. evidence of actual production use.

### 1.7 `ArcReel/ArcReel` (★5,257) — strongest on cost tracking + editable delivery

- **URL:** https://github.com/ArcReel/ArcReel
- **Stats:** ★5,257 · forks 1,036 · Python · created 2026-02-07 · last push 2026-10-01 · **AGPL-3.0**

**Exact pipeline (verified Mermaid from README):**
```
小说 / 成品剧本 / 商品素材
  → 内容分析与项目规划
  → 角色 / 场景 / 道具资产
  → 分集与结构化剧本
  → 分镜图 / 多宫格分镜
  → 视频片段 / 旁白音轨
  → 成片合成
  → (branch) 剪映草稿导出
```

**Cross-cutting:**
- (a) **Multi-episode:** explicit 分集 stage; published 3+ episodes of a real series.
- (b) **Consistency:** "角色一致" as the headline promise; asset stage before episode scripting.
- (c) **Aggregation:** 成片合成 plus **multi-grid storyboards**.
- (d) **Lip-sync:** none documented.
- (e) **Cost control:** **best-in-class among the drama projects** — "统一配置文本、图像、视频和 TTS 能力，并在**生成前后**查看费用与实际用量" (view cost **before and after** generation, plus actual usage). Combined with "成本可追踪" as a headline property.
- (f) **Review gates:** "可审核、可中断恢复的生产流水线" — every stage can be agent-orchestrated **or** user-reviewed/adjusted/regenerated. Plus:
- **Delivery that stays editable:** JIANYING (剪映) draft export — "continue adjusting subtitles, voiceover, pacing and transitions in 剪映." Explicitly notes CapCut compatibility is unverified. This is a **major practical insight**: the open-source pipeline stops at an editable timeline, not a locked MP4.

### 1.8 `alibaba/lumenx` (★1,318) — the only Big-Tech-backed entry

- **URL:** https://github.com/alibaba/lumenx
- **Stats:** ★1,318 · TypeScript/Python · last push 2026-08-11 · **MIT** · by StarLotus / Alibaba Group
- **Positioning:** "AI-Native Motion Comic & Video Creation Platform" — 短漫剧. Two modules: **Studio** (pipeline-first) and **Playground** (standalone generation).

**Exact pipeline (stated as 剧本→分镜→资产→视频→合成→导出):**
- 深度剧本分析 — LLM extracts 角色/场景/道具, generates structured storyboard script
- 可控美术指导 — custom visual style, unified art direction across the film
- 多模型资产生成 — **角色三视图 (character three-view/turnaround)**, 场景定调图, 道具参考图
- AI 分镜视频 — I2V / R2V multi-mode + **批量抽卡 (batch candidate rolls)**
- 智能配音 — **CosyVoice / Qwen3-TTS** multi-timbre dialogue synthesis
- 一键合成导出 — timeline edit + FFmpeg concat

**Notable:** the only project with **角色三视图** as an explicit named stage (industry practice: generate a turnaround sheet to lock identity), and the only one with first-class **批量抽卡** (candidate sampling) in the pipeline vocabulary. Uses Alibaba's own DashScope model catalog with a YAML→JSON `config/model_catalog/`.

### 1.9 `shuyu-labs/BigBanana-AI-Director` (★2,252) — best articulation of keyframe-driven consistency

- **URL:** https://github.com/shuyu-labs/BigBanana-AI-Director
- **Stats:** ★2,252 · last push 2026-09-29 · **license: non-commercial** (repo says future versions ship only as official Docker images, source no longer public; full source only for commercial licensees)

**Explicit four-phase pipeline, named in the README's own screenshots:**
- **Phase 01 叙事规划 (Narrative Planning)** — 项目 → 季 → 集 hierarchy; structured script generation; AI continuation + manual refinement; **全自动计划预审 (automatic plan pre-review)** where you decide per-shot whether to use the 九宫格分镜 (9-grid storyboard) or 首尾帧 (first/last-frame) chain
- **Phase 02 一致性资产 (Consistency Assets)** — character 定妆照, 衣橱系统, scene/prop assetization, cross-project asset reuse, batch backfill of missing assets
- **Phase 03 镜头制作 (Shot Workbench)** — grid shot workbench; **Start Frame / End Frame** generation/upload/inherit/edit; **九宫格分镜预览** (generate 9 candidate viewpoints, pick the full image or crop a single cell as first frame); context-aware generation; dual video chains (single-image I2V or first/last-frame interpolation)
- **Phase 04 成片交付 (Delivery)** — CutOS editing, finished-film export, delivery as master video / clip archive / source assets for Premiere/Resolve

**The core thesis, stated bluntly in the README:** *"AI 漫剧最致命的痛点不是画质、不是配音，而是**角色一致性**——换个镜头就变脸"* and *"先有演员和片场，再开机"* (cast the actors and build the set before you roll camera).

**Triple-lock consistency mechanism:**
1. **定妆照系统** — standard reference image per character, the visual anchor all shots reference
2. **衣橱系统** — multiple looks per character, all variants generated from a Base Look so facial features hold: *"换衣服不换人"*
3. **上下文感知生成** — shot generation automatically reads the current scene image, the character's current costume reference and prop references

**Honest self-assessment (rare and valuable):** *"BigBanana 不是最自动化的 AI 漫剧工具，但它是目前最可控的方案之一"* and automation is rated **中高 (medium-high), 需手动微调**. It also publishes real timing: a 5-minute / 10-shot short takes **1–2 hours** of AI-director work (script+characters ~20 min, storyboard ~15 min, image gen ~30 min, video gen ~20 min, voice ~10 min), **2–3 hours** end-to-end for a skilled user — and *"每个环节都支持人工审核和调整"* (every stage supports human review and adjustment).

**Data locality:** project data lives in **browser IndexedDB**, not server-side.

### 1.10 `xuanyustudio/LocalMiniDrama` (★1,903) — cleanest canonical 8-step list

- **URL:** https://github.com/xuanyustudio/LocalMiniDrama
- **Stats:** ★1,903 · JavaScript · last push 2026-09-14 · "数据不出本机" (fully local), Lite + full desktop builds

**The README's own table is the closest thing to a published canonical stage list:**

| # | Stage | Detail |
|---|---|---|
| 1 | 故事生成 | 输入梗概 + 风格 → AI 自动生成**多集**剧本 |
| 2 | 剧本编辑 | **分集管理**, script text freely editable |
| 3 | 角色生成 | AI extracts character list, generate each character image |
| 4 | 场景生成 | Auto-extract scenes from script, generate scene background |
| 5 | 道具生成 | Extract/manually add props, generate prop images |
| 6 | 分镜生成 | Per-episode auto storyboard (**含景别/运镜/台词** — shot size / camera move / dialogue) |
| 7 | 图片/视频生成 | Per-shot still frame + video clip |
| 8 | 合成视频 | Auto-concat all shot videos into the complete episode |

**Additional engineering worth stealing:**
- **一键生成 / 补全并生成** — full auto from characters to composed video, **智能跳过已有内容** (intelligently skips already-generated content)
- **失败自动重试，每步最多 3 次** — auto-retry 3× per step against rate limits, with live progress and error logs
- **工作流组 (workflow groups)** — box-select storyboards → create workflow → **整组重跑 (rerun the whole group)** with independent checkboxes for image/video/voice. This is the closest thing to *batch dependency-aware rerun* in the drama projects.
- 尾帧衔接 (tail-frame chaining) between shots · `@图片N` multi-image reference · 工程 ZIP export/import · global asset library · 16:9/9:16/1:1
- A **LibTV-style canvas mode** sharing the same data as list mode; per-shot vertical pipeline row (文本→首帧/尾帧→视频).

### 1.11 `xhongc/ai_story` (★1,704) — best explicit pipeline-state model

- **URL:** https://github.com/xhongc/ai_story
- **Stats:** ★1,704 · Python · last push 2026-09-17

**Pipeline (README):**
```
输入主题 → 文案改写 → 分镜生成 → 图片生成 → 运镜规划 → 视频生成 → 完成
```
Note **运镜规划 (camera-move planning) is a separate stage** — distinct from storyboard generation. Most projects fold this into the storyboard prompt.

**Engineering model:** *"基于 **Pipeline 责任链模式**"* (chain-of-responsibility), Celery async task queue, and:
- **阶段回滚功能** (stage rollback) — first-class
- 支持暂停、恢复、重试任意阶段 (pause / resume / retry **any** stage)
- **每个阶段可配置多个模型** + load balancing (轮询/随机/权重/最少负载) + 限流配置
- **使用量统计和成本分析** (usage statistics and cost analysis)
- Prompt **版本管理** (version management) with template variables, effect evaluation and test/preview

This is the most complete *runtime* model (rollback + per-stage retry + per-stage multi-model + cost analytics) among the Chinese projects.

### 1.12 `ChrisChen667788/wind-comic` (★591) — most detailed engineering writeup in the entire survey

- **URL:** https://github.com/ChrisChen667788/wind-comic
- **Stats:** ★591 · forks 69 · TypeScript · last push 2026-10-01 · MIT

**Named 8-agent pipeline:** Director (plans story) → Writer (dialogue under McKee structure) → Style Bible Frame (locks the look) → Character Designer (extracts an **8-dimension DNA signature** per character) → Storyboard (renders with **Vision Audit, auto-regen on score <70**) → Video producer (**races multiple engines** — Minimax / Veo / Kling, first good clip wins) → Editor (j/l-cuts on emotional beats, burns CJK subtitles) → Lipsync.

Its data flow: `TEXT → JSON → PNG → IMG → MP4`, every artifact persisted and **"independently reusable, so any stage can be re-run in isolation."**

**This project answers the advanced architectural questions better than any other:**

| Question | wind-comic's answer |
|---|---|
| Candidate/version model? | **Yes** — "Takes are versioned like voice retakes — adopt or roll back." Segment retake boxes bad frames, does a **free dry-run** first, then generates only the patch, splices, verifies frame count before recording the take; the first adoption **keeps the original as its own take** so rollback is one click. |
| Dependency-based invalidation? | **Yes, explicitly** — "Every stage at a glance — what's ready, what's gone **stale** because you changed something upstream, and a **one-click rerun that knows exactly which downstream stages it invalidates**." Implemented in `lib/pipeline-stages.ts` + `components/director-console.tsx` (4-stage pipeline model + stale detection + single-stage rerun). |
| Cost pre-estimation? | **Partly** — per-project cost attribution **by stage** (LLM / image / video / TTS / lip-sync), saving hints, and an **ok/warn/over budget guard**. Plus "a free dry-run shows what will be generated" before spending. |
| Quality gates? | **Yes, multi-dimensional** — a **four-dimension publish-readiness gate**: picture-vs-script · consistency · lip-sync alignability · **measured mouth-vs-audio**. Plus a ffprobe film health report per project *and* per series, batch re-render of degraded shots, and **a season-export health gate so no broken episode sneaks into the compilation**. |
| Lip-sync? | **Yes, the most complete of any project** — per-character voice routing (auto by name + manual pick/audition) → TTS → **viseme keyframe track** → measured **mouth-vs-audio alignment score** (Web-Audio) → **drift auto-correct** → pluggable engine render (**wav2lip / SadTalker / MuseTalk**, BYO `LIPSYNC_API_URL`) → written back into the timeline. **One-click whole-film lip-sync** with a Vision QC self-heal loop. Also uses Kling lip-sync API for talking heads with Sync.so and Hailuo as auto-fallback, **stripping dialogue from the prompt so the model only generates lip *motion*, then syncing to TTS audio in post.** Honest limits: dialogue audio must be ≥2s, source video must be at a public URL, ja/ko/ru degrade to an **honest skip** (surfaced in the UI). |
| Multi-episode? | **Yes** — novel → chapter-aware episodes, N-episode parallel, **real TTS narration + burned SRT**. v12.214→244 added **剧情记忆 (plot memory)**: episode N's Writer is injected with prior-episode recaps + continuity discipline, explicitly benchmarked against 红果/阅文's 60–100 episode continuity. |

**Also — its competitive analysis is itself a research asset**, and its self-corrections are unusually honest (it retracts four "only we have this" claims and even admits a pacing gate "only warned" and didn't match the code until v12.455).

**Stated economics (from its README, attributed to industry sources):** traditional 1-season cost 30–150万元 (premium 150–300万) vs pure-AI 2–10万元; per-minute ~1万元 vs 100–4000元 → **80–90% cost reduction**. **Crucially: "制作只占总成本 7.5%，投流占 70–85%"** — production is ~7.5% of total cost and ad spend is 70–85%, therefore *"任何以「更便宜地出片」为唯一卖点的工具，价值天花板极低"* (any tool whose only selling point is cheaper rendering has a very low value ceiling). This is a strategic finding, not just a technical one.

### 1.13 Others verified in Tier A (shorter notes)

- **`Stonewuu/ai-fusion-video` (★1,553, MIT, Java 21/Spring Boot + AgentScope)** — https://github.com/Stonewuu/ai-fusion-video — Agent-driven; 按分集和场景组织剧本 (organizes scripts by **episode and scene**), decomposes/adjusts storyboards, per-shot asset generation. Agent workspace with streaming dialogue, multimodal context, **tool permissions, Skills, MCP and sub-agents**; sessions and run state persisted. **Acknowledges `waoowaoo` for its script UI design reference.**
- **`LingGuoAI/LingGuo-Drama` (★1,542)** — https://github.com/LingGuoAI/LingGuo-Drama — 剧本→角色→场景→分镜→图片/视频生成→片段合并 backend workbench; Go; FFmpeg required; self-describes as a base for secondary development.
- **`yi1108/printfilm` (★4,052, MIT)** — https://github.com/yi1108/printfilm — template-driven: 主题/剧本 → 分镜 → 生图 → 生视频 → FFmpeg 合成成片. **Notably: "口播由 Seedance 出片时生成，无需单独配音"** — dialogue/lip-motion is generated *by the video model itself*, so it **skips the TTS and lip-sync stages entirely.** "每个阶段都可以回头重做单镜" (any stage can be redone per-shot). Optional billing, off by default.
- **`freestylefly/director_ai` (★1,776)** — https://github.com/freestylefly/director_ai — mobile AI 漫剧 app, one-click script + storyboard + video composition; last push 2026-05-01 (slower).
- **`EvoLinkAI/ai-short-drama` (★45, MIT-ish, self-hosted Docker)** — https://github.com/EvoLinkAI/ai-short-drama — the cleanest one-line statement of the canonical pipeline: **"Novel Text → AI Script Analysis → Storyboard → Images → Videos → Voiceover → Final Drama."** Low stars but cited by `wind-comic` as a genuine MIT end-to-end competitor.
- **`murongg/openframe` (★120, AGPL-3.0)** — https://github.com/murongg/openframe — 项目→剧本→角色/道具/场景→分镜→生产/导出, **exports FCPXML/EDL**.
- **`Xiao-rx/Douyin-Micro-Horror-Studio` (★59, MIT)** — https://github.com/Xiao-rx/Douyin-Micro-Horror-Studio — explicitly a **「半自动化」(semi-automated)** toolchain, honestly labelled: 全季主线规划 → 剧本创作 → 世界观与人物设定 → 视觉锚定图提示 → 分镜与文案提示词 → 分镜视频拼接 → AI 配音与成片 → 运营话术与封面文案. Note it includes **全季主线规划 (full-season arc planning)** and **运营话术与封面文案 (marketing copy + cover text)** — stages no other repo covers.
- **`YYC-Cube/YYC3-AI-Family-Comic-Drama` (★0)** — https://github.com/YYC-Cube/YYC3-AI-Family-Comic-Drama — 8 agents, six stages 小说→分镜→图像→视频→成片→运营. Claims **≤2元/集** and **一致性≥80%** but **0 stars, 0 forks** — treat as an unvalidated personal project, included only because it states explicit cost/consistency targets.

---

## 2. Agent-skill collections — a distinct, important architectural pattern

These are not web apps. They are **file-first, agent-native skill packs** that run inside Claude Code / Codex. They are arguably closer to an "industry-standard reference workflow" than the web apps, because they encode the *method* explicitly and are version-controllable.

### 2.1 `eternityspring/shuohao-skills` (★4,023, Apache-2.0)

- **URL:** https://github.com/eternityspring/shuohao-skills
- **Stats:** ★4,023 · forks 545 · last push 2026-09-26 · Apache-2.0

**Six skills forming a five-stage pipeline** (plus a composer):

| Skill | Does what |
|---|---|
| `novel-outline` | Novel → short-drama outline set: adaptation notes, cast list, **爽点表 (payoff/hook table)**, **分集梗概 (per-episode synopsis)**, asset inventory incl. narrative props. **14 quality gates, all script-checked.** Supports a "health check" mode on existing outlines. |
| `novel-characters` | Characters → 人物画像, 形象提示词, **音色提示词 (voice-timbre prompts)**, character设定图. Consumes `outline.json`. |
| `character-refs` | Actually **generates** character reference images: describe a character → split fields → complete → confirm → **generate a front full-body anchor first**, then headshot / 90° profile / back / detail all reference only that anchor, tiered on demand. Every image labelled, individually re-generatable, and **过期自动标出 (stale ones auto-flagged)**. Providers: Qwen Image (ComfyUI), codex, GPT Image 2 API, custom command. |
| `novel-art` | Art bible (scenes + narrative props): **一致性锚点**, lighting/state variants, scale references, empty-plate prompts. **10 quality gates.** |
| `novel-script` | Script: scenes + **beat flow (action/dialogue alternating)**, **per-episode duration deterministically computed from speech rate**, hook must land within the first 3 beats (a gate), and a **台词本 (dialogue sheet) aggregated per character with voice-timbre prompts that plugs straight into TTS**. **10 quality gates.** |
| `novel-storyboard` | Storyboard: **段 (segment, one generation ≤15s) → 分镜 (shot, 2–5s hard gate) → 分镜图 (main frame pinned at 0.00s, sub-frames pinned to their cut points)**; MiniMax H3 prompt alignment instructions reconciled **word-by-word against the cut timestamps**; storyboard frames actually rendered using the art-bible images as references; one-command export of an **H3 / Seedance production package**. **18 quality gates.** |

**Why this is the most rigorous artifact in the survey:** it enforces **deterministic, script-checked quality gates (14 + 10 + 10 + 18)** rather than LLM-judged vibes; it derives **per-episode duration analytically from speech rate**; it enforces **shot length as a hard constraint (2–5s)** tied to the generative model's real limit; it does **dependency-based staleness** on reference images; and the explicit statement *"分镜只做输出不做新决定"* (the storyboard stage makes no new decisions, it only outputs) is a clean separation-of-concerns principle.

### 2.2 `zenstory-ai/drama-skills` (★2,422, MIT) — the clearest published canonical stage list

- **URL:** https://github.com/zenstory-ai/drama-skills
- **Stats:** ★2,422 · forks 523 · last push 2026-09-28 · MIT · 11 skills

**Its stated end-to-end flow:**
```
原著分析 → 分集剧本 → 视觉设定 → 图片提示词与分镜 → 视频提示词 → 确认后生产 → 剪辑成片 → 审查
```

**The 11 skills (this is effectively a role decomposition of the whole industry):**

| Skill | Responsibility |
|---|---|
| `short-drama` | Init, routing, **visual direction / Look Development**, Dashboard |
| `short-drama-novel-analyze` | Long-novel sampling quick-eval, chapter index, per-chapter function extraction, plot units & pacing, adaptation value, **episode-split candidates** |
| `short-drama-develop` | Traceable adaptation, **agent-led slicing of multi-episode drafts with resumable continuation**, story engine, **episode map**, director's statement, genre & hook handbook |
| `short-drama-write` | Per-episode objective, causal beats, shootable script |
| `short-drama-assets` | Characters/looks, locations/views, props/states, optional **character voice direction** and continuity decisions |
| `short-drama-image-prompts` | Lookdev style frames, character/scene/prop reference-board prompts, targeted-revision notes |
| `short-drama-storyboard` | Optional scene visual plan + **Coverage Audition**, source-text adherence, shots, boundaries, **frozen keyframes** |
| `short-drama-video-prompts` | Per-shot action, multi-character performance & attention handoffs, cinematography, sound, **start/end state**, pick-up notes, and **cross-shot timeline music spec** |
| `short-drama-produce` | **Shows bounded image/video/TTS/music tasks, obtains per-batch explicit confirmation, then executes via external adapters and records results** |
| `short-drama-edit` | Usable takes per shot, in/out point rationale, shot order, dialogue completeness, **subtitles and loudness**, written as an edit sheet then rendered |
| `short-drama-review` | Structural/content review; project-level calibration diagnostics and revision conclusions |

**Three design principles it states outright, which I consider the strongest normative statements found:**
1. **"五份 Markdown 就是创作事实"** — per episode only `剧本.md`, `视觉设定.md`, `分镜.md`, `图片提示词.md`, … are maintained. Plain files are the source of truth; no vendor lock-in.
2. **"先预览、确认，再生产"** — *any* image, video, voice or music task first shows the exact batch contents and parameters in a file; **only after explicit confirmation does it call the paid external API.** "刻意把确认放在生产之前" (deliberately place confirmation before production).
3. **成片也在套件里** — the edit skill writes down in/out points *and why they were chosen*; subtitles are taken **word-for-word from the script**; loudness is normalized before render. Provider credentials never enter the project.

**Real published sample with cost:** a 68-second vertical sample adapted from a 20-chapter novel, 20 shots, **video generation cost ≈ ¥40.**

### 2.3 `liangdabiao/Seedance2-Storyboard-Generator` (★2,506)

- **URL:** https://github.com/liangdabiao/Seedance2-Storyboard-Generator
- **Stats:** ★2,506 · forks 371 · last push 2026-09-21 · no license file
- Skill tooling that turns 小说/故事 into **multi-episode video** by generating the script/storyboard first, explicitly motivated by *"试错成本越来越高，提示词的重要性从来没有像今天这样大"* (trial-and-error cost keeps rising; prompt quality has never mattered more).

---

## 3. ComfyUI-native pipelines

### 3.1 `Work-Fisher/ComfyUI-Novel-Director` (★213)

- **URL:** https://github.com/Work-Fisher/ComfyUI-Novel-Director
- **Stats:** ★213 · forks 17 · Python · created 2026-01-26 · last push 2026-02-27 · README says MIT

A ComfyUI custom-node pack for AI 短剧 / 有声小说 / 动态漫. It consumes **LLM-generated JSON** and automates storyboard parsing → casting → TTS-driven generation → final merge. Node graph:

```
1. 演员选角 (Casting, 6 per node, chainable via prev_cast_dict, reference image → IP-Adapter to lock faces)
2A. 有声剧脚本加载 (Audio JSON: role_list[name, instruct, text] + juben)
2B. 分镜脚本加载 (Visual JSON: storyboard_list[prompt, main_character])
2C. 视频提示词加载 (Video JSON: video_prompts — motion/camera)
3. 场景处理器 / Scene Iterator — flattens all lists into a per-scene data stream,
   prepends "Role:" to Text and Instruct, dispatches dialogue/prompt/motion/character image downstream
3B. 时长计算器 — computes frame count from audio duration; Buffer Frames holds the image past speech end
4. 实时存档 Saver — writes Scene_000.mp4…, pads silence when video > audio, emits manifest.txt
5. 最终合并 Render — ffmpeg/moviepy lossless concat → Final_Movie.mp4, can return to ComfyUI Video Combine
```

**Key ideas:** the **Scene Iterator** "一键生成 100 集" (one click, 100 episodes) pattern; **audio-duration-driven frame count** with explicit buffer frames for "breathing room" on cuts; per-scene archive files so a single scene can be regenerated; character-to-image binding for IP-Adapter face locking. **Known caveat it documents honestly:** for outputs >1 minute the Final Render node may only return the first frame as a preview to avoid VRAM overflow, though the full file is saved.

### 3.2 `SwotAtmk/infinite-creation` (★29, MIT)

- **URL:** https://github.com/SwotAtmk/infinite-creation
- **Stats:** ★29 · forks 3 · JavaScript · created 2026-09-09 · last push 2026-09-30 · MIT
- Local **ComfyUI + MiniMax H3 + Agent + Skill** fully automatic "infinite" video production from a submitted novel/script, explicitly **unbounded in duration**. Topics: `agent`, `agent-skills`, `deepseek`, `minimax-h3`.

### 3.3 Supporting / adjacent ComfyUI components

- `chaojie/ComfyUI-MuseTalk` (★301, MIT) — https://github.com/chaojie/ComfyUI-MuseTalk — the official-linked MuseTalk node.

---

## 4. Lip-sync / talking-head component layer (NOT pipelines — components)

These are the building blocks a drama pipeline must integrate. Verified stats:

| Repo | ★ | Last push | License | What it is / practical constraints |
|---|---|---|---|---|
| [OpenTalker/SadTalker](https://github.com/OpenTalker/SadTalker) | 14,110 | 2024-06-26 | NOASSERTION | Audio-driven stylized single-image talking face. **Stale (2024).** |
| [Rudrabha/Wav2Lip](https://github.com/Rudrabha/Wav2Lip) | 13,226 | 2025-06-22 | none stated | The classic. Video + audio → lip-synced video. Needs a face; quality dated but ubiquitous as the fallback. |
| [OpenTalker/video-retalking](https://github.com/OpenTalker/video-retalking) | 7,294 | 2024-08-05 | Apache-2.0 | SIGGRAPH Asia 2022, audio-based lip sync for talking-head editing in the wild. Stale. |
| [TMElyralab/MuseTalk](https://github.com/TMElyralab/MuseTalk) | 6,652 | 2025-09-26 | NOASSERTION | **Real-time (30fps+ on V100)**; latent inpainting, single step, NOT diffusion. Trained on HDTF+private. **Tested on RTX 3050 Ti Laptop 4GB VRAM: 8-second video ≈ 5 minutes in fp16.** Known artifact: jitter (single-frame generation). Training code open-sourced. |
| [bytedance/LatentSync](https://github.com/bytedance/LatentSync) | 6,104 | 2025-06-20 | Apache-2.0 | **End-to-end audio-conditioned latent diffusion, no intermediate motion representation.** LatentSync 1.5/1.6 adds a temporal layer for temporal consistency, better Chinese-video performance. Training VRAM: stage1 23GB, stage2 30GB (efficient 20GB). |
| [jixiaozhong/Sonic](https://github.com/jixiaozhong/Sonic) | 3,274 | 2026-01-08 | NOASSERTION | "Shifting Focus to Global Audio Perception in Portrait Animation." Most recently maintained of the research set. |
| [ShmuelRonen/ComfyUI-LatentSyncWrapper](https://github.com/ShmuelRonen/ComfyUI-LatentSyncWrapper) | 963 | — | — | The most-used LatentSync ComfyUI node. |
| [SamKhoze/ComfyUI-DeepFuze](https://github.com/SamKhoze/ComfyUI-DeepFuze) | 461 | — | — | DeepFuze lip-sync/face integration into ComfyUI. |
| [yuvraj108c/ComfyUI-FLOAT](https://github.com/yuvraj108c/ComfyUI-FLOAT) | 272 | — | — | Audio-driven talking portrait via generative motion latent flow matching. |
| [ShmuelRonen/ComfyUI_wav2lip](https://github.com/ShmuelRonen/ComfyUI_wav2lip) | 167 | — | — | Wav2Lip node. |
| [AIFSH/ComfyUI-IP_LAP](https://github.com/AIFSH/ComfyUI-IP_LAP) | 34 | — | — | IP_LAP audio-driven video node. |

**Repos I could NOT verify (state explicitly):** `fudan-generative-ai/hallo` and `KwaiVGI/LivePortrait` did not resolve at those paths in this environment.

### How pipelines actually integrate lip-sync — the key finding

Lip-sync is **not** a naive post-processing append. Three distinct strategies appear:

1. **BYO external engine, post-hoc, with measurement (wind-comic — most mature).** Dialogue audio → **viseme keyframe track** → **measured mouth-vs-audio alignment score** → **drift auto-correct** → render via wav2lip/SadTalker/MuseTalk through a `LIPSYNC_API_URL` → write back into the timeline. Crucially the pipeline **strips dialogue from the video prompt so the model generates only lip *motion*, then syncs to TTS in post** — and it has an **honest skip** for ja/ko/ru rather than fake success. Hard constraints recorded: dialogue ≥2s, source video must be at a public URL.
2. **Cloud lip-sync API with fallback chain.** Kling lip-sync API for talking heads, Sync.so and Hailuo as auto-fallbacks.
3. **Skip it entirely — let the video model do it.** `printfilm`: *"口播由 Seedance 出片时生成，无需单独配音"* — modern video models emit synchronized speech, so the pipeline has **no separate TTS or lip-sync stage**. This is increasingly the industry direction: PixVerse C1 is described in wind-comic's analysis as the most short-drama-vertical model, with **storyboard-grid output + multi-speaker lip-sync**; Vidu Q3 ships "lip-sync driving"; HappyHorse generates joint video+audio in one pass.

**Realistic hard limits for lip-sync in 2026:** it needs a well-framed face; multi-character scenes are not solved by these components (per-speaker crops are needed); the open models are stale relative to video models; and VRAM/time is non-trivial (MuseTalk: 8s ≈ 5 min on 4GB). **In open-source practice lip-sync is a per-shot, human-supervised stage with measurement and retry — not an automatic pass.**

---

## 5. Baseline: "shorts automation" / faceless-video pipelines

These are structurally *different* and should be used as the **negative control** in the comparison.

### 5.1 `harry0703/MoneyPrinterTurbo` (★127,865)

- **URL:** https://github.com/harry0703/MoneyPrinterTurbo
- **Stats:** ★127,865 · forks 19,999 · Python · created 2024-03-11 · last push 2026-10-01 · **MIT**

**Pipeline:** topic → script (LLM, multilingual, or custom) → **keywords/terms** → **stock material** (Pexels / Pixabay / Coverr, or upload your own, or optional AI T2V via MiniMax H3 / Seedance / WaveSpeed / OFox / MuAPI / OpenAI-compatible T2I→video) → TTS → subtitles → BGM → FFmpeg edit → optional **one-click cross-platform publish to TikTok / Instagram / YouTube Shorts**.

- Four entry points: **AI Agent, WebUI, API, CLI**; batch generation of multiple videos; task history; settings/API-key import-export.
- TTS: Edge TTS (free, no API key), Azure, SiliconFlow, Gemini, MiMo, MiniMax, ElevenLabs, Chatterbox, Kokoro, Fish Audio, VoxCPM.
- **Cost control:** none in-product beyond using free stock/TTS. Cost appears only via sponsored gateway discounts.
- **Multi-episode:** no. **Character consistency:** no (no characters). **Scene aggregation:** no. **Lip-sync:** no. **Review gates:** manual per-asset override only.

### 5.2 `RayVentura/ShortGPT` (★7,999)

- **URL:** https://github.com/RayVentura/ShortGPT
- **Stats:** ★7,999 · forks 1,156 · Python · created 2023-06-27 · **last push 2025-02-10** · MIT · **stale (≈20 months)**

Engines: `ContentShortEngine` (shorts: script → render → YouTube metadata), `ContentVideoEngine` (longer: audio → auto background footage → timed captions → background assets), `ContentTranslationEngine` (dub/translate whole videos), `EditingEngine` (**Editing Markup Language** — a JSON DSL for LLM-comprehensible edit blocks). Asset sourcing via web + Pexels. Persistence via TinyDB. MoviePy for rendering. **No 分集, no consistency, no lip-sync, no cost control, no gates.**

### 5.3 `SaarD00/AI-Youtube-Shorts-Generator` / AutoShorts AI (★232)

- **URL:** https://github.com/SaarD00/AI-Youtube-Shorts-Generator
- **Stats:** ★232 · forks 63 · Python · created 2025-12-24 · last push 2026-06-26 · MIT

Pipeline: **Gemini 2.0 Flash** script (Hook → Context → Mechanism → Twist) → **edge-tts** voiceover → **Pexels dual-visual sourcing (two distinct stock clips per scene, A/B split)** → FFmpeg (smart trim to audio duration, mid-sentence visual switch, random `xfade` transitions, **silence removal**, random avatar injection into a middle scene, Windows-safe `yuv420p`/`faststart` flags). Modules are cleanly separated: `brain.py` / `audio.py` / `asset_manager.py` / `composer.py`.

### 5.4 What the baseline tells you

The shorts-automation family automates **exactly four stages**: script → TTS → stock-footage retrieval → FFmpeg assembly (+subtitles/BGM). They have **no concept of**: characters, scenes, episodes, continuity, shots as first-class entities, or generation cost control. **The delta between this family and the AI短剧 family IS the definition of the short-drama pipeline.**

---

## 6. SYNTHESIS

### 6.1 The consensus canonical stage list

Assembled from the overlap of Jellyfish, huobao-drama, LocalMiniDrama, ArcReel, DramaClaw, BigBanana, LumenX, ViMax, and drama-skills. **Stages in bold appear in the majority of projects; stages in italics appear in a strong minority but are considered marks of maturity.**

```
 0. 项目 / 世界观设定            Project & worldview setup (genre, style bible, aspect ratio, tone)
 1. 小说/创意输入                 Novel / idea / screenplay ingest
 2. 原著分析 & 分集规划           Source analysis → episode planning & 分集梗概
    (novel compression, chapter index, beat planning, season arc, hook/payoff table)
 3. 剧本生成 & 结构化             Script generation → structured screenplay (scenes, dialogue, beats)
 4. 角色/场景/道具 抽取           Character / scene / prop extraction (with dedup)
 5. 一致性资产 · 定妆             Consistency asset generation: character 定妆照 / 三视图,
                                  scene concept art, prop refs, 衣橱 (costume variants), 音色 (voice)
 6. 分镜脚本                      Storyboard: shot list + 景别/角度/运镜/情绪/时长/台词
 7. 关键帧 (首帧/尾帧)            Keyframes: first frame / last frame / reference selection
 8. 图生视频 / 首尾帧插值         Image-to-video or first-last-frame interpolation (per shot)
 9. 配音 TTS                      TTS per character with voice-timbre assignment
10. 口型同步                      Lip-sync (viseme/align/engine)   ← weak/optional in most
11. 剪辑 / 时间线                 Editing & timeline assembly
12. 字幕                          Subtitles (often burned, karaoke word-level in mature stacks)
13. 合成 & 导出                   Compose & export (MP4, or editable 剪映/EDL/FCPXML)
14. 审查 / 质检                   Review & QC gate (script audit, vision audit, publish readiness)
```

**Compact form for your comparison doc:**
`小说/创意 → 分集规划 → 剧本 → 角色/场景/道具抽取 → 一致性定妆资产 → 分镜脚本 → 关键帧 → 图生视频 → 配音 → 口型同步 → 剪辑 → 字幕 → 合成导出 → 审查`

### 6.2 MUST-HAVE vs NICE-TO-HAVE

**MUST-HAVE** (present in essentially every real end-to-end project; absence disqualifies a project from being an AI短剧 pipeline):

| Stage | Evidence |
|---|---|
| Structured script generation from source text | 100% of Tier A |
| **Character / scene / prop extraction as explicit entities** | Jellyfish, huobao (`extractor`), ArcReel, DramaClaw, BigBanana, LocalMiniDrama, LumenX, ViMax |
| **Consistency asset generation before shot generation** ("先有演员和片场，再开机") | BigBanana 定妆照+衣橱; LumenX 角色三视图; ViMax character_portraits_generator; shuohao `character-refs` anchor |
| **Shot (分镜) as the atomic generation unit**, with 景别/运镜/时长/台词 | 100% of Tier A |
| Keyframe / first-frame conditioning for I2V | BigBanana Start/End frame; LocalMiniDrama 首帧/尾帧; DramaClaw frozen keyframes |
| Per-shot video generation + retry | 100% |
| TTS with per-character voice assignment | LumenX (CosyVoice/Qwen3-TTS), huobao, ArcReel, drama-skills (台词本→TTS) |
| Episode-level aggregation and merge | huobao episode list, LocalMiniDrama 分集管理, BigBanana 季/集, Jellyfish 章节 |
| **A human confirmation gate before spending on generation** | Jellyfish candidate confirmation + readiness; drama-skills "确认后生产"; OpenMontage enforced gates; BigBanana 全自动计划预审 |

**NICE-TO-HAVE / differentiating** (present in a minority; these are where the mature projects separate):

| Stage | Who has it |
|---|---|
| **Lip-sync as a measured, retryable stage** | wind-comic (only truly complete one), plus component-level availability (MuseTalk/LatentSync/Wav2Lip) |
| **Cost pre-estimation and budget caps** | OpenMontage (estimate/reserve/reconcile, $0.50 per-action, $10 cap); ArcReel (cost before *and* after); ai_story (usage + cost analysis) |
| **Dependency-based invalidation / stale detection + targeted rerun** | wind-comic (explicit), Jellyfish (readiness states), LocalMiniDrama (workflow-group rerun), ai_story (stage rollback), DramaClaw (resume from checkpoint) |
| **Candidate/version ("take") model with rollback** | wind-comic (takes, dry-run, rollback), ViMax (`reference_image_selector`, `best_image_selector`), LumenX (批量抽卡), BigBanana (9-grid candidate views), DramaClaw (image-pool selection) |
| **Editable-timeline export (剪映/EDL/FCPXML/AAF)** | ArcReel (剪映 draft), openframe (FCPXML/EDL), wind-comic (EDL/FCP7/AAF) |
| **Automated QC gates (vision audit, ffprobe health, publish readiness)** | OpenMontage (post-render self-review, blocks presentation), wind-comic (4-dimension publish gate, season health gate, Vision Audit auto-regen <70), DramaClaw (prereq validation), shuohao (14/10/10/18 script-checked quality gates) |
| **Multi-episode plot memory (前情提要 injection)** | wind-comic (explicitly for 60–100 episode continuity) |
| **3D/spatial scene consistency** | DramaClaw (Gaussian-splat sets, 360° panoramas, previz) |
| **Cross-project reusable cast / template market** | wind-comic (Cameo IP, template market), BigBanana (cross-project asset library) |
| **Full-season arc + marketing copy stages** | Douyin-Micro-Horror-Studio (全季主线规划, 运营话术/封面文案) |

### 6.3 Common architectural patterns

**1. Multi-provider gateway is universal, BYO-key is the norm.** Every Tier A project aggregates providers. LumenX has a YAML `model_catalog`; huobao/wind-comic/DramaClaw all route through OpenAI-compatible gateways; DramaClaw is explicitly "model-neutral — all text/image/video/audio models connect through an OpenAI-compatible gateway." No project bets on one model vendor.

**2. Agent decomposition mirrors the pipeline.** huobao's 4 Mastra agents, ViMax's 13 agents, wind-comic's 8 agents, DramaClaw's Xia Director, ai-fusion-video's AgentScope sub-agents. The agent names *are* the stage list.

**3. Async task center with cancel/retry/resume is standard.** Jellyfish (unified task center with status/cancel/elapsed/jump-back), DramaClaw (Task Center with resume-from-checkpoint), ai_story (Celery + pause/resume/retry any stage), LocalMiniDrama (3× auto-retry per step), wind-comic, huobao (retry failed tasks in one click).

**4. Does anyone use a candidate/version model? — YES, and it's a maturity marker.**
- **wind-comic** is the most complete: takes are versioned like voice retakes, adopt-or-roll-back, segment-level retake with a **free dry-run before spending**, original preserved as its own take on first adoption.
- **ViMax** splits *selecting* references from *generating* them (`reference_image_selector` → `best_image_selector`).
- **LumenX** names it 批量抽卡 in the pipeline vocabulary.
- **BigBanana** generates 9 candidate viewpoints then lets you pick one cell as the first frame.
- **DramaClaw** does grid splitting + image-pool selection.
- **Jellyfish** models it as asset/dialogue *candidates* that must be accepted or ignored.

**5. Does anyone do dependency-based invalidation? — Only ONE does it properly.**
- **wind-comic** is the only project with explicit stale-detection and rerun that "knows exactly which downstream stages it invalidates" (`lib/pipeline-stages.ts` + Director Console).
- Partial implementations: Jellyfish's unified readiness state, LocalMiniDrama's workflow-group rerun, ai_story's stage rollback, DramaClaw's resume-from-checkpoint, OpenMontage's archived superseded checkpoints.
- **This is the single biggest architectural gap in the open-source field.** Most projects let you re-run a stage but cannot tell you what became invalid.

**6. Does anyone do cost pre-estimation? — Rarely, and only two do it well.**
- **OpenMontage** is the only project with a full **Estimate → Reserve → Reconcile** lifecycle plus modes `observe`/`warn`/`cap`, per-action approval threshold and total cap.
- **ArcReel** shows cost before *and* after generation plus actual usage.
- **ai_story** has usage statistics and cost analysis; **wind-comic** has per-stage attribution + ok/warn/over budget guard + free dry-run.
- **Everyone else has nothing.** Cost is reported, if at all, only after the fact. Combined with Toonflow's real data point (**~¥130 for a 2-minute film, of which ¥120 is video**), this means the industry-standard open-source pipeline gives you almost no ability to predict or cap spend before it happens.

**7. A "files are the source of truth" pattern is emerging** (drama-skills' 五份 Markdown, shuohao's five J-son artifacts + soft-linked skills, OpenMontage's `pipeline_defs/` YAML manifests + stage director markdown skills, huobao's UI-editable `SKILL.md`). This makes pipelines diffable, reviewable and agent-navigable — likely the most important 2026 trend.

**8. Declarative stage manifests + per-stage director skills.** OpenMontage (YAML manifest + markdown skill per stage) and huobao (`backend/workspace/skills/`) both externalize "how to execute this stage" into versioned files the agent reads at runtime.

### 6.4 Where open-source projects are typically WEAK

Ranked by how consistently the gap appears:

1. **Lip-sync is the weakest link.** Only wind-comic implements it as a measured, retryable, drift-corrected stage. Most Tier A projects have **no lip-sync at all** (Jellyfish, huobao, ArcReel, LocalMiniDrama, Toonflow). The component layer (MuseTalk 2025-09, LatentSync 2025-06, SadTalker 2024-06, video-retalking 2024-08) is **stale relative to the video models**, needs a well-framed face, fails on multi-character scenes, and costs real VRAM/time. Practically, projects either push the problem to the video model (printfilm: no TTS at all, Seedance emits speech) or skip it.
2. **No cost pre-estimation or hard budget enforcement.** Two projects do it well; the rest expose you to uncapped spend with no preview. Given ~¥120 of a ¥130 budget goes to video, this is a serious omission.
3. **Dependency-based invalidation is essentially absent.** One real implementation. Everything else is manual "rerun this stage and hope."
4. **Character consistency is solved by prompt/reference conditioning, not by an identity system.** Nearly everyone does reference-image injection (定妆照 + IP-Adapter + cref/sref). Only wind-comic attempts a structured identity (8-field DNA signature + embedding-based **identity drift detection** via per-shot cosine distance with outlier flagging) and BigBanana formalizes costume variants (衣橱). **There is no shared identity standard, and no open benchmark for cross-shot consistency.**
5. **Character consistency *across episodes/seasons* is worse than across shots.** wind-comic explicitly had to add plot memory for 60–100 episode continuity ("此前各集独立成篇" — previously each episode stood alone).
6. **Shot-length ceilings vs dramaturgy.** Real model limits (4–15s; 2–5s hard gate in shuohao; ≤15s generation segments) force fragmentation that makes continuous dialogue scenes hard. Only the newest models (Seedance 2.5 / Wan 3.0: native ~30s single takes) ease this.
7. **QC is mostly human eyeballing.** Only OpenMontage and wind-comic have automated, blocking QC (post-render self-review that withholds the video; 4-dimension publish gate). Others rely on the user noticing.
8. **Maintenance volatility is high.** Everything in Tier A is 5–9 months old, and several repos have already pivoted or gone source-available (`waooAI/waoowaoo` → Elastic 2.0, no voiceover in the current preview; `BigBanana` → Docker-images-only, non-commercial license; `markthree/Jellyfish` → abandoned stub). **Star count is a poor proxy for a usable pipeline** — `markthree/Jellyfish` has a beautiful README and no working generation pipeline; `EvoLinkAI/ai-short-drama` has 45 stars and a complete one.
9. **Licensing is a real trap.** waoowaoo = Elastic 2.0 (not OSI open source, hosted-service restriction); BigBanana = non-commercial; OpenMontage & ArcReel = **AGPL-3.0** (viral for network use); huobao & DramaClaw = custom/"Other"; several have no license at all. **MIT is the exception, not the rule, among the drama-specific projects** — the clean MIT set is ViMax, LumenX, Jellyfish (Forget-C), Toonflow, ai_story, wind-comic, ComfyUI-Novel-Director, drama-skills, printfilm, ai-fusion-video.
10. **Nobody solves the last mile.** Only ArcReel (剪映 draft), openframe (FCPXML/EDL) and wind-comic (EDL/FCP7/AAF) hand off to a real NLE. Everyone else terminates in a locked MP4, which makes professional revision impossible.

### 6.5 Recommended reference workflow to compare your proprietary project against

Based on the consensus plus the strongest individual patterns, the defensible "industry-standard" reference is:

```
0  项目/世界观设定            genre, style bible, aspect ratio, target duration, per-episode speech-rate budget
1  原著分析                   compression, chapter index, per-chapter function extraction, beat/payoff analysis
2  分集规划                    episode map, per-episode synopsis, hook within first 3 beats, season arc
3  剧本                      scene + beat flow (action/dialogue alternating), duration derived analytically
4  实体抽取                    角色 / 场景 / 道具 / 服装 with dedup against existing library
5  一致性资产                   character 定妆照 + 三视图 + 衣橱变体, scene concept art, prop refs, 音色 per character
   ──────── HUMAN GATE: confirm cast, art and assets ────────
6  分镜                       shot list with 景别/角度/运镜/情绪/时长/台词; shot duration 2–5s hard bound
7  关键帧与参考绑定              first/last frame, frozen keyframes, explicit reference-image binding per shot
   ──────── HUMAN GATE: bounded task preview with exact count/params/output → explicit confirm ────────
8  图生视频 / 首尾帧插值         per shot, multi-engine race, candidate takes, per-step retry (3×)
9  配音 TTS                   per-character voice routing, aggregated 台词本
10 口型同步 (optional)          viseme track → alignment score → drift correct → engine render → measured QC
11 剪辑                      in/out points with rationale, j/l-cuts, timeline
12 字幕                      word-level, burned, platform safe-area aware, from script verbatim
13 合成导出                     loudness-normalized MP4  +  editable export (剪映 / EDL / FCPXML)
14 审查                      script audit (pacing/conflict/reversal), Vision per-shot audit, ffprobe health,
                            publish-readiness gate (picture · consistency · lip-sync · alignment)
   ──────── Cross-cutting: cost estimate→reserve→reconcile, budget cap, stale detection + downstream
             invalidation, decision audit trail, provider scoring, task center with resume ────────
```

**The five capabilities that separate the mature projects from the pack** — and are therefore the right benchmark axes for your proprietary project:
1. **Enforced (not advisory) human gates backed by the state machine** — OpenMontage's checkpoint writer refuses to record a gated stage as complete without approval.
2. **Cost estimate → reserve → cap, with per-action approval** — OpenMontage; partially ArcReel/wind-comic.
3. **Dependency-based invalidation with targeted rerun** — wind-comic only.
4. **Measured, self-healing QC that can withhold output** — OpenMontage post-render review; wind-comic 4-dimension gate + Vision self-heal.
5. **Versioned "takes" with dry-run and one-click rollback** — wind-comic.

---

## 7. Explicit verification ledger

**Verified to exist with the stated stats** (all via GitHub REST API this session): Forget-C/Jellyfish (6,561), HBAI-Ltd/Toonflow-app (16,312), chatfire-AI/huobao-drama (15,627), HKUDS/ViMax (12,540), calesthio/OpenMontage (62,087), dramaclaw/dramaclaw (6,615), ArcReel/ArcReel (5,257), alibaba/lumenx (1,318), shuyu-labs/BigBanana-AI-Director (2,252), xuanyustudio/LocalMiniDrama (1,903), xhongc/ai_story (1,704), Stonewuu/ai-fusion-video (1,553), LingGuoAI/LingGuo-Drama (1,542), yi1108/printfilm (4,052), eternityspring/shuohao-skills (4,023), zenstory-ai/drama-skills (2,422), liangdabiao/Seedance2-Storyboard-Generator (2,506), freestylefly/director_ai (1,776), ChrisChen667788/wind-comic (591), Work-Fisher/ComfyUI-Novel-Director (213), murongg/openframe (120), Xiao-rx/Douyin-Micro-Horror-Studio (59), EvoLinkAI/ai-short-drama (45), SwotAtmk/infinite-creation (29), waooAI/waoowaoo (14,346), YYC-Cube/YYC3-AI-Family-Comic-Drama (0), markthree/Jellyfish (1), harry0703/MoneyPrinterTurbo (127,865), RayVentura/ShortGPT (7,999), SaarD00/AI-Youtube-Shorts-Generator (232), Rudrabha/Wav2Lip (13,226), OpenTalker/SadTalker (14,110), TMElyralab/MuseTalk (6,652), bytedance/LatentSync (6,104), OpenTalker/video-retalking (7,294), jixiaozhong/Sonic (3,274), chaojie/ComfyUI-MuseTalk (301), ShmuelRonen/ComfyUI-LatentSyncWrapper (963), SamKhoze/ComfyUI-DeepFuze (461), yuvraj108c/ComfyUI-FLOAT (272), ShmuelRonen/ComfyUI_wav2lip (167), AIFSH/ComfyUI-IP_LAP (34).

**Could NOT verify — do not cite as existing:** `fudan-generative-ai/hallo`, `KwaiVGI/LivePortrait` (owner path wrong), `Novella AI` (~89★ claimed by wind-comic's README), `saturndec/waoowaoo` (301-redirects to waooAI/waoowaoo — the old slug is dead as an independent repo).

**Largest single factual correction:** the requested `markthree/Jellyfish` is a 1-star stub whose own roadmap shows the generation pipeline as unbuilt; the substantive project is `Forget-C/Jellyfish` (6,561★).
