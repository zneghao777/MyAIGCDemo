# 任务三提示词：口型同步

将以下全文复制给编码代理执行。

---

## 角色与目标

你是本仓库的高级后端与全栈工程师。本次任务为短剧的每一镜增加口型同步能力。

仓库根目录：`/Users/zenghao/MyAIGCDemo`。

评估报告的结论是：**口型同步是开源界最弱的一环。** 在调研的 20+ 个项目中，多数（Jellyfish、huobao、ArcReel、LocalMiniDrama、Toonflow）完全没有这个阶段；开源组件（MuseTalk、LatentSync、SadTalker）相对视频生成模型已经落后；**多人同框在开源方案中尚未解决**，需要按发言人裁切。

因此本任务的第一设计原则是：**诚实缺席，而不是假装拥有。**

## 前置条件

**任务一与任务二必须已经完成。** 具体确认：

- 任务一的 `copy.ts`、`TechnicalDetails.tsx`、`capabilities` 机制均可用。
- 任务二的分集结构已就位，`Scene` 已有 `episode_id`，`dependency_stamp` 已是集合结构。
- 任务一的 `T1-E3` 已完成：`IMAGE_MAX_REFERENCES` 已提到 4，分镜 prompt 已约束参考图预算。

缺少任何一项，停止并报告。

> `T1-E3` 是硬前置。口型同步需要清晰正脸，而多角色同框镜头无法满足。如果分镜生成阶段还在产生大量双人同框镜头，口型同步会被大量跳过，这个功能就没有意义。

## 第一步：必读材料

1. `design/specs/优化与能力扩展Spec-CineAI-Studio.md` —— **§4 是你的完整工作范围**。**先读 §T3-B0**，那一节纠正了一个关键前提；再看 §5 跨任务契约、§6 风险与回滚、§7 明确不做的事。
2. `design/reviews/2026-10-01-flow-ux-audit/短剧生成流程与交互体验评估报告.md` —— §2.2 的口型同步对比行，以及 §4 的 P2-13。
3. `backend/app/services/video_correction.py` —— **本任务最重要的参考文件**。它实现了「一镜的可选用视频候选」的完整范式：`locked_scene`（加锁取数）、`select_candidate`（八步选用流程）。口型同步按它实现，不要另创一套。
4. `backend/app/providers/base.py` 与 `backend/app/providers/__init__.py` —— 现有 5 个 Provider 协议与 `providers()` 工厂的注册方式（`@lru_cache` + 位置参数 dataclass）。视频字段是「启用/禁用二选一」的现成模板。
5. `backend/app/services/video.py` —— 尤其是 `organized_prompt()` 的台词时间拼接与 `source()` 的指纹组成。理解这两者的区别是 T3-B3 的关键。
6. `backend/app/services/video_dependency.py` —— 看它读取的是哪个字段。T3-B5 是验证项，不是改造项。
7. `backend/app/tasks/execute.py` —— 任务执行、重试、取消、清理的完整模式；以及视频结果如何直接写入场景。
8. `backend/app/services/video_capacity.py` —— Redis 准入控制的现有模式，你的口型队列参考它。

> **行号是评估时的快照。** 任务一与任务二刚落地的改动会让行号整体漂移。以实际代码为准，函数名与符号名比行号可靠。不要为了匹配文档行号而改动无关代码。

## 第二步：设计决策（动手前必须先想清楚）

在写代码前，用一段话回答以下五个问题，写进完成报告的开头。答不出来就先不要写代码。

1. **视频为什么不能照抄图片候选的写法？** 读 `select_candidate` 与 `video_correction.select_candidate`，说明视频结果在本仓库的实际流转路径，以及口型同步该参照哪一个。
2. **引擎从哪来？** 本仓库的开发机没有 GPU。说明 `none` / `http` / `local` 三种模式各自解决什么问题，以及为什么默认必须是 `none`。
3. **怎么判断"做不了"？** Spec §T3-B4 列了四种跳过情况，并规定了每种由谁判定。说明为什么「没有可对齐的正脸」必须由引擎判定，而不能在本地判断。
4. **怎么保证没有骗人？** Spec §T3-C1 要求 `alignment_score` 在无法测量时为 `null`。为什么不能填一个估计值？
5. **用户在哪里第一次知道这件事做不了？** 必须在点击之前，不是在等了两分钟之后。

## 第三步：按阶段施工

Spec §4 把任务三分为四个阶段：`T3-A` Provider 抽象与配置、`T3-B` 生成链路、`T3-C` 质量报告、`T3-D` 前端界面。

严格按 A → B → C → D 顺序执行。每个阶段单独提交，message 格式 `T3-A: <描述>`。

### T3-A Provider 抽象与配置

新增 `LipSyncProvider` 协议与三种实现。新增六个配置项。

**`LIPSYNC_PROVIDER` 默认必须是 `none`。** 这是最重要的默认值：保证现有部署升级后行为完全不变，界面上不会冒出任何口型入口。

**注册方式照抄视频字段。** `providers()` 是 `@lru_cache` 的位置参数 dataclass，新增字段必须在 dataclass 与构造调用中按同一顺序同时插入。视频字段的写法是现成模板：

```python
MiniMaxVideo() if get_settings().feature_video_generation else DisabledVideo(),
```

`DisabledLipSync` 必须存在，即使它只返回一条「未启用」错误——这样调用方不需要到处判空。

`http` 模式的**请求与响应契约已在 Spec §T3-A2 定义**（multipart 上传 video/audio/options，200 + `video/*` 响应体，报告走 `X-Lipsync-Report` 响应头）。按该契约实现，你的测试桩也按该契约写。**契约的一个关键点：镜头做不了时返回 200 且 `alignable=false`，不要用 4xx 表达业务结果。**

### T3-B 生成链路

**先读 Spec §T3-B0，这一节纠正了一个关键前提：视频在本仓库里不走候选制。**

- 图片与音频走候选制；**视频不走**——`select_candidate` 没有视频生成结果的分支，视频任务在 `execute.py` 里直接 `save_state` 写 `scene.video_key` 与 `video_takes`。
- **唯一的例外是 `video_correction`**：本地上传的修正版视频是可选用的候选，走 `/select`。
- **口型同步属于后者。** 按 `services/video_correction.py` 的八步流程实现，不要另创一套。
- 别忘了给 `src/features/Creative.tsx` 的 `select()` 判断加上 `"lipsync"`——它决定用场景版本号还是角色版本号做 `expected`，漏了会稳定触发 409。

新增 `cineai.lipsync` 队列与 `shot_lipsync` 操作。

### T3-B1b 三处必须同时注册（最容易漏）

**新增一个操作在本仓库要改三个地方，少任何一处都不会报错，只会静默不工作。** Spec §T3-B1b 给了完整说明，简表：

| # | 位置 | 现状 | 漏掉的后果 |
| --- | --- | --- | --- |
| ① | `routers/creative.py` 的 `job_payload` | `kind` 是 `image`/`tts`/`script` 三段式，**未匹配的静默落到 `script`** | 任务被脚本 worker 捡走，语义完全错误 |
| ② | `worker_config.py` 的队列清单 | 只有 `script/image/tts/video/compose` | 任务投到 `cineai.lipsync` 但**无人监听，永远停在 queued**，不报错不超时 |
| ③ | `services/creative.py` 的 `execute_candidate` | `if/elif` 链，**没有终结 `else`** | 未匹配的操作带着空 result 继续走，产出一条空候选 |

三处都改完，再按下面的验收方式确认。

**验收方式（关键）**：提交一个 `shot_lipsync` 任务后，确认 `Task.kind == "lipsync"`、队列为 `cineai.lipsync`、且 `status` 从 `queued` **变为 `running`**（有 worker 认领）。

> **只确认「任务创建成功」不算通过。** 上面三处漏任何一处，任务创建都会成功。必须看到它真正被 worker 领取并执行。

**`T3-B3 从视频 prompt 中剥离台词`是本任务质量的关键。** 当前 H3 收到的 prompt 包含台词文本与实测时间，模型被要求「按已标记台词与动作触发时间表演」。当口型同步启用时，模型自行生成的嘴型会与后期对齐的口型冲突。

`VIDEO_MOUTH_MOTION_ONLY` 默认为真（当 `LIPSYNC_PROVIDER != "none"`）。为真时：移除 prompt 中的台词文本，保留 `trigger_line_id` 的动作触发时间（肢体动作仍需与音轨对齐），并说明「本镜不生成台词语音，嘴部只做自然开合动作，语音由后期合成」。

**验证方式是把实际提交给 H3 的 prompt 抓出来，确认其中不含任何台词文本。** 不要只断言代码里有过滤逻辑。

> **重要：不要把 `VIDEO_MOUTH_MOTION_ONLY` 加进视频指纹。** Spec §T3-B3 解释了原因：H3 的 prompt 由 `organized_prompt()` 在提交时组装，而指纹由 `source()` 决定，两者的组成不同。只改前者的拼装不会使已有视频失效，这是期望行为——否则切换配置会导致全库视频需要重做。在完成报告里明确记录你的选择。

### T3-B5 是验证项，不是改造项

`video_dependency.py` 读取的是 `previous.video_key`。由于选用口型候选后会更新 `scene.video_key`，**依赖链会自动使用同步后的视频，不需要修改 `video_dependency.py`。**

你要做的是**证明**它成立：让 A、B 两镜构成 `continuity_from` 依赖，对 A 选用一个口型候选，重新触发 B 的首帧依赖抽取，断言抽帧使用的 `video_key` 等于 A 镜当前的 `video_key`。

**不要因为 Spec 提到这一条就去改一个本来就正确的文件。** 只有当你实际读到 `video_dependency.py` 用的不是 `video_key` 时，才需要改造，并在报告中说明偏差。

### T3-C 质量报告

每个成功同步的镜头保存 `lipsync_report`。

**最低成本的必测项不依赖人脸模型**：输出时长与输入一致（容差 1 帧）、帧率与分辨率不变、音频轨与输入音频指纹一致。这三项必须始终执行。

`alignment_score` 由引擎在 `X-Lipsync-Report` 中给出；引擎未提供时为 `null` 并说明原因。**不得填入伪造分数，也不得在本地引入人脸模型去算一个分数**（硬约束禁止新增依赖）。这一条比分数本身重要得多——评估报告的核心结论就是本项目「不伪装失败」的工程诚实是它最值钱的资产，不要在这里丢掉它。

`T3-C2 导出前门禁`：有未同步镜头时给出提示，但**不阻断导出**。未启用口型同步的部署不显示任何口型相关内容。

### T3-D 前端界面

分镜详情新增「口型同步」区块；多发言人前置预检；导出页逐镜口型状态。

**`T3-D1` 的参照物是 `VideoCorrection.tsx`，不是 `CandidateList`。** `VideoCorrection.tsx` 已经实现了「列出一镜的可选用视频候选 + 选用」的完整交互。`CandidateList` 的字段假设（`c.data.request`、`reference`、`model`）是给图片与音频候选用的，与视频候选不匹配。Spec §T3-D1 给出了接入的 props 形态。

**`T3-D2` 是本任务体验上的关键。** 若本镜涉及多位发言人，必须在用户点击之前就禁用按钮并显示原因与「拆分镜头」的建议链接。**不要让用户等两分钟后才被告知不支持。** 发言人计数是纯本地判断（读 `shot.lines` 与 `shot.narration` 的 `speaker_id` 去重），不需要任何模型。

`T3-D1` 的按钮文案必须诚实反映耗时，例如「生成口型（约 2 分钟）」，不得写成瞬时操作。

## 硬约束

1. **默认关闭，升级无感。** `LIPSYNC_PROVIDER` 默认 `none`，此配置下界面上不存在任何口型入口，导出页不出现任何口型文字。
2. **不得伪造成功。** 四种跳过情况必须返回 `skipped` 与具体原因，不得静默回退到原始视频，不得填伪造分数。
3. **不得阻塞导出。** 未同步的镜头只是提示，不是门禁。
4. **不新增依赖。** 本任务不需要新增任何 Python 或 npm 依赖。不要为了调用外部服务而引入新 HTTP 客户端——仓库已有 `httpx`。
5. **不改既有测试断言。** 失效的断言按任务一的规则单独列出。
6. **所有新文案进 `copy.ts`。** 不新建第二个文案文件。
7. **能力通过 `capabilities` 声明。** 新增 `lipsync`、`lipsyncEngine`、`lipsyncMaxSpeakers` 三个字段，前端据此渲染。
8. **不动 Spec §7 的范围内事项。** 特别是：不做自动视觉一致性审核、不做人脸漂移检测、不做转场库。
9. **不做 GPU 假设。** 你的代码和测试必须在没有 GPU、没有安装 MuseTalk 的机器上全部通过。人脸可对齐性由引擎判定，本地不引入人脸检测依赖。
10. **不改动既有视频的失效行为。** 不要把 `VIDEO_MOUTH_MOTION_ONLY` 或口型相关配置加进 `source()` 视频指纹。已有视频不得因为本任务被批量标记过期。
11. **不改 `video_dependency.py`，除非实测证明它读的不是 `video_key`。** 该条是验证项。
12. **保持 `video_correction` 的现有行为不变。** 你可以复用 `locked_scene` 与参照它的 `select_candidate` 流程，但不要修改它的既有逻辑。若把 `locked_scene` 提升为共享工具，必须保证 `video_correction` 的现有测试全部通过。
13. **新建或修改客户端组件时，`"use client"` 必须是文件的首条语句。** 任何 `import` 出现在它前面都会让该指令失效，模块被当成服务端组件处理，Turbopack 直接报 `The "use client" directive must be placed before other expressions`，构建失败且页面返回 500。**本仓库已经因为这一条栽过一次**（`src/lib/remote-store.ts`，T1-B 阶段）。`LipsyncPanel` 是新增的客户端组件，特别容易踩到。每次提交前跑 `npm run build` 确认。

## 完成定义

**命令级验证，全部要有实际输出：**

```bash
npm run typecheck
npm run build
npm run test:web
backend/.venv/bin/python -m pytest backend/tests -q
backend/.venv/bin/python -m pytest backend/tests/test_lipsync.py -q   # 你新增的
```

**默认关闭验证（最重要的一条）：**

在 `LIPSYNC_PROVIDER=none` 下，以下三项必须全部成立：

```bash
# 1. capabilities 中 lipsync 为 false
curl -s http://127.0.0.1:8001/api/creative/projects/<任一项目 id> | python3 -c \
  "import json,sys; print(json.load(sys.stdin)['capabilities']['lipsync'])"
# 必须输出 False

# 2. 口型文案的来源清单（用于分类，不要求为空）
grep -rln "口型" src/
```

第 3 项是**渲染验证**，必须用 Playwright 或手工截图完成，不能靠 grep：

> 在 `LIPSYNC_PROVIDER=none` 下打开分镜详情页，断言**页面上不出现任何口型相关的区块、按钮或文字**。

**关于第 2 项：这条 grep 的输出不要求为空。** `LipsyncPanel` 组件文件本身必然包含「口型」字样（按钮文案、跳过原因模板等），它存在但不渲染，这是正确写法。与 T1 的术语收敛检查同理，要求的是**分类**：把 `grep -rln` 列出的文件逐个归为「组件定义」或「实际渲染」，并在报告中给出分类表。判断依据是**页面实际渲染结果**（第 3 项），不是关键词是否存在。

只有当第 3 项渲染验证通过、且分类表中没有「在 `none` 配置下仍会渲染」的文件时，本项才算通过。

**接入验证（全部用测试桩，不需要真实引擎）：**

用一个按 Spec §T3-A2 契约实现的本地测试桩模拟 `LIPSYNC_API_URL`，确认：

1. 对单人正脸镜头执行 `shot_lipsync`，产出 `kind="lipsync"` 候选；选用后本镜 `video_key` 指向新产物，原视频进入 `video_takes`。
2. 修改该镜配音后，`lipsync_fingerprint` 变化，旧候选标记为过期，选用返回 409 `STALE_CANDIDATE`。
3. 对双人同框镜头执行，返回 `skipped` 与「本镜有 2 位发言人」的原因，且**不产生候选**。
4. `VIDEO_MOUTH_MOTION_ONLY=true` 时，抓取 H3 提交的 prompt，其中不含任何台词文本；同时确认已有视频**没有**被批量标记过期。
5. T3-B5 的依赖链验证：A 镜选用口型候选后，B 镜依赖抽取使用的 `video_key` 等于 A 镜当前的 `video_key`。
6. 测试桩返回 `alignable=false` 时，跳过原因如实展示；测试桩返回 5xx 时，任务标记为 failed，错误信息为中文且可操作，不出现原始英文异常。

**行为级验证：**

1. `LIPSYNC_PROVIDER=none` 时，分镜详情中不存在口型区块，截图存证。
2. 双人同框镜头在点击前即被禁用，显示拆分建议，截图存证。
3. 导出页逐镜列表显示口型状态标记。
4. 成功同步的镜头在技术详情中能看到完整报告，且报告中的时长、帧率、分辨率与实际产物一致。

截图存放于 `design/reviews/2026-10-01-flow-ux-audit/shots/after-t3/`。

## 完成报告格式

```
## 设计决策
（回答第二步的五个问题，每个一段话）
## 执行摘要
## 默认关闭验证
（capabilities 输出、grep 输出）
## 接入验证
（六条，每条附命令输出；全部基于测试桩）
## 阶段完成情况
### T3-A … ### T3-D
（每阶段：状态、改动文件、commit、验收输出、偏差）
## 命令级验证结果
## 行为级验证结果
（四条，每条附截图路径）
## 未做真实引擎验证的说明
（若本机无 GPU：明确写出「本地未做真实引擎验证，原因是缺少 GPU」，
 并列出哪些结论来自测试桩、哪些需要真实引擎才能确认）
## 诚实性自检
（逐条确认：哪些地方返回了 skipped、哪些地方返回了 null、
 有没有任何地方填了估计值、有没有改动既有视频的失效行为）
## 发现但未处理
## 需要人工决策的事项
```

「未做真实引擎验证的说明」与「诚实性自检」两节不可省略。它们是本任务的核心验收项。

## 停止并报告的条件

出现以下任一情况，**立即停止**，输出当前进度与阻塞原因：

1. 任务一或任务二的前置条件不满足。
2. 你发现自己的实现需要伪造一个分数、一个状态或一个成功结果才能通过验收。
3. 你需要在没有 GPU 的机器上**安装** MuseTalk、LatentSync 或其他模型权重才能继续。写一个 HTTP 测试桩不算安装。
4. 连续三次尝试仍无法通过某个阶段的验收。
5. 需要新增任何依赖。
6. 你发现 `VIDEO_MOUTH_MOTION_ONLY` 的改动会破坏现有的视频生成测试，且无法在保留原行为的前提下兼容。
7. 你实测发现 `video_dependency.py` 读取的不是 `video_key`，导致 T3-B5 需要真正的改造。

**以下情况不构成停止条件，按本文档执行即可：**

- 视频不走候选制这件事与你的预期不符。Spec §T3-B0 已经说明，按 `video_correction` 的范式实现即可。
- `T3-B5` 看起来要改 `video_dependency.py`。它是验证项，先验证再决定是否改造。
- Spec 的行号与实际代码有偏移。任务一与任务二刚落地，偏移是预期的，以实际代码为准并在报告中记录。
- 你需要设计全季合辑之外的编排方式、测试桩的实现方式等。这是设计自由度。
- 本机没有 GPU。见下。

**如果本机确实没有 GPU 环境**，正确的做法是：完成 `T3-A` 的 Provider 抽象、`T3-B` 的 `skipped` 路径与测试桩驱动的选用流程、`T3-C` 的报告结构、`T3-D` 的全部前端，把 `LIPSYNC_PROVIDER` 保持在 `none`，用按 Spec §T3-A2 契约实现的 HTTP 测试桩验证接入路径，并在报告中明确说明「本地未做真实引擎验证，原因是缺少 GPU」。

**这仍然是一个完整合格的任务三。** T3-B 的五条验收标准全部可以用测试桩通过，不需要真实引擎。不要为了凑一个"真实运行过"的结论去伪造结果。
