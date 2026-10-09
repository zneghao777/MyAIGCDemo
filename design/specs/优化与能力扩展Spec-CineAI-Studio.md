# CineAI Studio 优化与能力扩展 Spec（Phase C）

本文档把《短剧生成流程与交互体验评估报告》（`design/reviews/2026-10-01-flow-ux-audit/`）的结论转化为可执行的开发规格。本轮工作分为三个长任务：**任务一质量整改**、**任务二分集结构**、**任务三口型同步**。三个任务按顺序执行，每个任务独立可验收、可回滚。

阅读本文档前，请先阅读评估报告，尤其是 §3.5 的缺陷清单（B1–B14）与 §4 的改进方向。本文档为每个缺陷分配了任务与阶段编号，不重复论证。

## 0. 文档约定

### 0.1 编号体系

本文档使用三级编号，贯穿 Spec 与三份任务提示词：

- **任务**：`T1` 质量整改、`T2` 分集结构、`T3` 口型同步。
- **阶段**：`T1-A` … `T1-E`、`T2-A` … `T2-D`、`T3-A` … `T3-D`。一个阶段是一组可独立提交、独立验证的改动。
- **条目**：`T1-A1`、`T1-A2` 等。条目是最小可验收单元。

评估报告中的缺陷编号（`B1`–`B14`）在本文档中保留，用于追溯。

### 0.2 证据要求

每个阶段的完成报告必须包含**可复制的命令输出**，不接受"已完成"这类无证据陈述。以下命令是各阶段的最低验证要求：

```bash
# 仓库根目录
npm run typecheck
npm run build

# 后端
backend/.venv/bin/python -m pytest backend/tests -q
```

涉及数据库结构变更时，额外要求：

```bash
backend/.venv/bin/python -m alembic upgrade head
backend/.venv/bin/python -m alembic downgrade -1
backend/.venv/bin/python -m alembic upgrade head
```

涉及界面变更时，额外要求提交截图，截图存放在 `design/reviews/2026-10-01-flow-ux-audit/shots/after/`。

### 0.3 硬约束

以下约束适用于全部三个任务，后文不再重复。

1. **不引入新依赖**，除非本文档明确要求。前端不新增状态管理库、不新增 UI 组件库、不新增测试框架之外的工具。后端不新增数据库、消息队列或对象存储。
2. **不修改既有测试的断言来让测试通过。** 如果某条既有断言因本轮改动而失效，必须在完成报告中单独列出该断言、说明它为何失效、并给出替代断言。静默改断言视为未完成。
3. **所有用户可见文案集中管理。** 任务一建立 `src/features/creative/copy.ts` 后，此后新增的任何用户可见字符串必须从该文件引用，不得内联。
4. **技术标识不出现在默认界面。** 供应商名、模型 ID、命令行工具名、内部 ID、版本哈希、原始 JSON 一律进入 `<TechnicalDetails>` 折叠区。
5. **提交粒度。** 一个阶段一个 commit，commit message 使用 `T1-A: <描述>` 格式。禁止把多个阶段压成一个 commit。
6. **不删除历史数据。** 迁移只做新增与搬移，不删除列、不删除行。降级脚本必须能还原到迁移前的数据形状。
7. **保持现有 API 契约。** 除非本文档明确要求变更，否则不修改既有端点的请求或响应形状。

## 1. 基线：本轮要解决的问题

评估报告的核心结论是：**工程严谨度远高于产品完成度**。后端在候选制、版本门禁、依赖失效传播、费用前置四个方面达到开源界第一梯队；前端则存在流程断裂、术语泄漏、可见缺陷三类问题。三个任务分别对应这三类问题与其后的能力扩展。

下表是本轮要消除的全部问题，按任务归类。

| 来源 | 问题 | 归属 |
| --- | --- | --- |
| 报告 §2.4-P0-2 | 环境素材阶段游离主链，确认后不推进 | T1-A |
| 报告 §2.4-P0-3 | 阶段编号与进度计数互相矛盾（3 项已确认 vs 2/3） | T1-A |
| 报告 §3.5-B2 | 导出 tab 状态写死，与真实验收数矛盾 | T1-A |
| 报告 §3.4-1 | 空态把用户引回已完成的步骤 | T1-A |
| 报告 §3.4-2 | 环境页保存与生成按钮互斥，禁用无出路 | T1-A |
| 报告 §3.3 全部 15 项 | 技术术语泄漏 | T1-B |
| 报告 §3.5-B1 | 原始英文报错 `Failed to fetch` 直接展示 | T1-B |
| 报告 §3.2 | 任务列表 14 条同名；检视面板 5 个平级按钮；状态句平铺 | T1-C |
| 报告 §2.4-P1-5 | 费用弹窗显示「最多 0 次调用」「未配置完整价格」 | T1-C |
| 报告 §3.5-B3/B4/B5/B6/B7/B10 | 任务标签、封面破图、假英文标题、警告样式误用、空播放器、移动端提示 | T1-D |
| 报告 §3.5-B8/B9；报告 §2.4-P1-8 | BGM 曲风死 UI、片头与水印静默 no-op（三个死开关） | T1-D |
| 报告 §3.1 | 同色 10 个值；`:has()` 布局劫持 | T1-E |
| 报告 §2.4-P1-7 | 参考图上限 2 阻塞双人对白镜头 | T1-E |
| 报告 §4-17 | 前端零测试 | T1-E |
| 报告 §3.5-B11 | `creative.stage` 死字段（后端） | T1-E5 |
| 报告 §3.5-B12 | worker 写入绕过项目行锁（后端） | T1-E5 |
| 报告 §3.5-B14 | 改环境文案无条件否掉整个分镜阶段（后端） | T1-E5 |
| 报告 §3.5-B13 | 依赖戳单字段；旁白未钉住模型（后端） | T2-C |
| 报告 §2.4-P0-1 | 无分集结构 | T2 |
| 报告 §2.4-P1（口型） | 无口型同步 | T3 |

**缺陷归属总账**：报告 §3.5 共 14 项。B1–B10（十项，前端）全部由任务一关闭。B11、B12、B14（三项，后端）由 T1-E5 关闭。B13（一项，后端）由 T2-C1 关闭。不存在未分配的缺陷。

## 2. 任务一：流程闭环、术语翻译层与缺陷修复

任务一不新增创作能力，只把已有能力做对、说清、修好。完成后，用户应能走完一条无断点的五阶段主链，界面上不再出现工程语汇，评估报告 §3.5 十四项缺陷中的十三项（B1–B12、B14）关闭；剩余一项 B13 属于跨集失效传播，由任务二 T2-C1 关闭。

任务一分为五个阶段，按下表顺序执行。A、B 是本任务的核心，必须先完成；C、D、E 可以与 B 并行评审，但提交顺序不变。

| 阶段 | 内容 | 主要文件 |
| --- | --- | --- |
| T1-A | 主线闭环与阶段一致性 | `Creative.tsx`、`LocationsWorkspace.tsx`、`CreativeStudio.tsx`、`services/creative.py` |
| T1-B | 用户语言层与错误兜底 | 新建 `copy.ts`、`TechnicalDetails.tsx`；`api.ts` 与各 feature 文件 |
| T1-C | 信息主次与费用弹窗 | `shared.tsx`、`Creative.tsx`、`Export.tsx` |
| T1-D | 视觉与交互缺陷 | `Export.tsx`、`Home.tsx`、`workbench.css`、`AppShell.tsx` |
| T1-E | 工程加固、配置修正与后端正确性 | `workbench.css`、`globals.css`、`backend/app/core/config.py`、`.env.local`、`backend/app/tasks/execute.py`、`backend/app/services/creative.py`、`backend/app/services/voice_continuity.py`、`backend/app/api/routers/creative.py`、新建前端与后端测试 |

### T1-A 主线闭环与阶段一致性

目标是把五个阶段变成一条编号连续、计数一致、每阶段都有明确出口的主链。

#### T1-A1 环境阶段纳入编号体系

把阶段导航从 `01 / 02 / 环境素材 / 03 / 04` 改为 `01 故事方案 / 02 角色形象与声音 / 03 环境素材 / 04 分镜创作 / 05 预览与导出`。

修改 `src/features/Creative.tsx:305-350` 的阶段数组。此改动会级联影响以下位置，必须同步：

- 阶段按钮的 `aria-current` 与 `active` 判定逻辑保持不变，只改标签。
- `setTab` 的取值集合新增 `locations` 已在集合内，无需改动。
- 任何按标签文本定位的代码（含 Playwright 脚本与测试）必须同步更新。

#### T1-A2 环境阶段提供前进出口

`LocationsWorkspace` 增加 `onNext` 回调。用户确认最后一个地点的环境版本后，页面底部出现与 T1-A1 其他阶段一致的 `ActionBar`，主行动按钮为「确认环境，进入分镜 →」，点击后调用 `setTab("storyboard")`。

实现要求：

- 在 `LocationsWorkspace` 的 props 中新增 `onNext: () => void` 与 `confirmedCount: number`、`totalCount: number`。
- 当且仅当 `locations` 非空且每一个 `states[id]?.confirmed` 为真时，`ActionBar` 的主按钮可用。否则按钮禁用，并在状态区显示还差几个地点，例如「还有 2 个地点未确认环境版本」。
- 当 `locations` 为空时，`ActionBar` 显示「请先确认故事中的地点」并提供一个跳回故事阶段的次按钮，不要渲染不可用的主按钮。
- `ActionBar` 组件从 `./shared` 引入，与 `StoryWorkspace`、`CharacterWorkspace` 用法一致。

#### T1-A3 进度计数改为 5 阶段口径

页头「项目进度 · X / 3 阶段已确认」改为「项目进度 · X / 5 阶段已确认」，其中 X 为五个阶段中状态为已确认的数量。

各阶段的「已确认」判定必须以服务端返回为准，不得在组件内自行推导：

| 阶段 | 判定来源 |
| --- | --- |
| 01 故事方案 | `plan_confirmed` |
| 02 角色形象与声音 | `cast_confirmed` |
| 03 环境素材 | 所有 `locations[id].confirmed` 为真且至少有一个地点 |
| 04 分镜创作 | `shots_confirmed` |
| 05 预览与导出 | `export_confirmation` 存在且未过期 |

后端 `workflowReadiness`（`backend/app/services/creative.py:289-316`）新增 `plan`、`cast`、`locations`、`shots`、`export` 五个布尔字段，前端只读该结构，不再重复推导。`routers/creative.py:102-123` 的 `stageStates` 同步使用同一套判定，确保页头计数与阶段标签永远一致。

> **说明**：`stageStates` 与 `workflowReadiness` 当前是两套独立推导，这正是「3 项已确认」与「2/3」矛盾的根因。本条目要求二者收敛到同一个后端函数。

#### T1-A4 阶段标签改为服务端真值

删除 `Creative.tsx:346` 中对导出阶段的写死状态：

```tsx
flow.issues.length ? "结构待就绪" : "结构就绪 · 待艺术验收",
```

改为读取 `workflowReadiness` 的真实结果，并区分三种情况：

- 有未解决的 `issues`：显示「结构待就绪」。
- 结构就绪但仍有镜头未完成艺术验收：显示「结构就绪 · 待艺术验收」。
- 全部镜头已验收：显示「已就绪」。

同时修正 `Creative.tsx:945` 的状态句，见 T1-C3。

#### T1-A5 修复空态死循环

`src/features/CreativeStudio.tsx:296-309` 的空态 CTA 当前只有两个分支，导致「故事已确认、角色已确认、无分镜」的项目被引导回已完成角色阶段。改为三个分支：

1. 故事未确认：按钮文案「开始故事方案」，跳转 `plan`。
2. 故事已确认、角色未确认：按钮文案「确认角色形象与声音」，跳转 `characters`。
3. 故事与角色均已确认、无分镜：按钮文案「生成分镜草案」，**直接触发分镜生成流程**（即调用现有 `onGenerate`，进入费用估算弹窗），不再跳转页面。

#### T1-A6 解除环境页的按钮互斥

`LocationsWorkspace.tsx:37-40` 当前存在两个互斥的禁用条件：保存按钮 `disabled={!dirty}`，生成与上传按钮 `disabled={dirty}`。用户永远只有一个按钮可用，且没有从禁用状态走出来的显式路径。

改为：

- 保存按钮保持 `disabled={!dirty}`（无改动时无需保存，这是合理的）。
- 生成候选、上传环境图两个入口在 `dirty` 时**不再禁用**。点击时若存在未保存改动，先弹出确认：「环境设定尚未保存。是否保存后继续？」提供「保存并继续」与「取消」两个选项。
- 「保存并继续」执行保存，成功后自动继续原操作。
- 把 `:37` 的被动 warning 文案改为可操作提示：「环境设定有未保存的修改」，并在其后直接渲染「保存场景设定」按钮。

#### T1-A 验收标准

完成 T1-A 后，以下操作必须全部成立：

1. 打开任一无分镜的项目（例如库中的「宿舍八卦风暴」），进入分镜阶段，空态按钮显示「生成分镜草案」，点击后出现费用估算弹窗。
2. 打开阶段导航，五个标签依次为 `01 故事方案`、`02 角色形象与声音`、`03 环境素材`、`04 分镜创作`、`05 预览与导出`。
3. 对「宿舍八卦风暴」，页头计数显示「3 / 5 阶段已确认」，与阶段标签中显示「已确认」的数量一致。
4. 进入环境阶段，页面底部出现操作栏；确认全部地点后主按钮可用。
5. 在环境阶段修改任一字段，生成候选按钮仍可点击，点击后出现保存确认弹窗。
6. 打开一个全部镜头已验收的项目（例如「给夜晚留一盏灯」），导出阶段标签显示「已就绪」，不再显示「待艺术验收」。

### T1-B 用户语言层与错误兜底

目标是把工程语言翻译成创作者语言，并保证任何情况下都不向用户展示原始技术信息。

#### T1-B1 新建文案字典

新建 `src/features/creative/copy.ts`，导出以下映射与函数。命名与键名以本节为准，后续任务与提示词引用同一套。

```ts
// 操作类型 → 用户可读名称
export const operationLabels: Record<string, string>

// 任务状态 → 用户可读短语
export function taskStatusLabel(status: string, extra?: { selected?: boolean; stale?: boolean }): string

// 错误码 → 中文文案与恢复建议
export function errorMessage(error: unknown): { title: string; detail: string; action?: string }

// 素材类型 → 中文
export const assetKindLabels: Record<string, string>

// 统一的「还剩什么没做」句式
export function remainingLabel(done: number, total: number, unit: string): string
```

`errorMessage` 是本节的核心。它必须：

- 对 `ApiError` 按 `code` 字段匹配，覆盖 `STALE_VERSION`、`STALE_CANDIDATE`、`STALE_TASK`、`PRECHECK_FAILED`、`REFERENCE_LIMIT`、`REFERENCE_REQUIRED`、`BGM_REQUIRED`、`COST_LIMIT_EXCEEDED`、`VIDEO_POINTS_LIMIT`、`RATE_LIMITED`、`SCENE_HAS_RUNNING_TASK`、`AUDIO_EXCEEDS_VIDEO`、`NETWORK_ERROR` 十三个码，每个码给出一句现象描述与一句恢复建议。
- 对未知 `ApiError` 回退为「请求未成功（错误码 {status}）。请重试；若持续失败，请把技术详情中的内容反馈给维护者。」
- 对非 `ApiError` 一律回退为通用文案，**绝不返回 `error.message` 原文**。

#### T1-B2 修复网络层异常泄漏

`src/lib/api.ts:27` 的 `fetch` 调用没有任何异常处理。浏览器网络失败时，`fetch` 抛出原生的 `TypeError: Failed to fetch`，该错误不带 `ApiError` 的 `code`，于是被 20 处 `e.message` 直接渲染到界面。评估报告实测到「罗峰 · 我为宇宙」分镜页顶部出现红色 `Failed to fetch`。

修改 `api` 函数，把 `fetch` 包进 `try/catch`：

- 捕获 `TypeError` 与 `DOMException`，转换为 `ApiError`，`status` 为 `0`，`code` 为 `"NETWORK_ERROR"`，message 为「网络连接失败」。
- 若传入的 `signal` 已 abort，重新抛出 `AbortError`，不要吞掉取消语义。
- 保留现有 429 冷却逻辑不变。

#### T1-B3 收敛全部错误展示点

全项目有 20 处形如 `e instanceof Error ? e.message : String(e)` 的直接透传。全部改为调用 `copy.ts` 的 `errorMessage(e)`，并按返回结构渲染：标题用 `role="alert"`，详情用次要文字样式，`action` 非空时渲染为可点按钮或链接。

`<TechnicalDetails>` 折叠区可以保留原始 message，但默认折叠。

#### T1-B4 新建统一的 TechnicalDetails 组件

新建 `src/features/creative/TechnicalDetails.tsx`，接收 `{ title?: string; data: unknown; extra?: ReactNode }`，渲染一个默认折叠的 `<details>`，摘要文案为「技术详情」，内容为格式化 JSON。

用它替换以下四处重复实现，替换后四处的外观与交互必须一致：

- `src/features/creative/shared.tsx:232-235`
- `src/features/creative/HistoryWorkspace.tsx:265-270`
- `src/features/creative/CandidateList.tsx:131-136`
- `src/features/creative/CharacterWorkspace.tsx:564-570`

`CharacterWorkspace.tsx` 的摘要文案当前是「技术详情与角色库」，替换后摘要统一为「技术详情」，其中的角色库操作作为 `extra` 传入，保留在折叠区内部。

#### T1-B5 术语收敛

按下表逐条替换。左列为当前界面上真实出现的字符串，右列为替换后结果。全部替换点必须逐一核对，不接受抽样。

| 当前文案 | 位置 | 替换为 |
| --- | --- | --- |
| 弹窗标题「MiniMax H3 · 并发分镜视频」 | `VideoGeneration.tsx:68` | 「生成分镜视频」 |
| 「稳定模式 · 2 句 · mimo-v2.5-tts-voiceclone」 | `CandidateList.tsx:93` | 「稳定音色 · 2 句」，模型 ID 移入技术详情 |
| 「起止状态与 H3」 | `SceneTools.tsx:324` | 「起止画面」 |
| 「不会调用 H3 超分」 | `Export.tsx:392` | 「本地放大不会增加原片细节，也不会调用云端超分」 |
| 「请先保存要修正的分镜与 H3 输入」 | `VideoRetake.tsx:58` | 「请先保存要修正的分镜」 |
| 「来源 H3 任务：{id}」 | `CandidateList.tsx:48`、`VideoCorrection.tsx:52` | 「来源：本项目已生成的原片」，ID 移入技术详情 |
| 「历史 H3 原片」 | `VideoCorrection.tsx:54` | 「历史原片」 |
| 「修正版来源 H3 任务」 | `VideoCorrection.tsx:54` | 「修正版来源」 |
| 「采用历史 H3 原片保留灯光与动作」 | `VideoCorrection.tsx:56` | 「采用历史原片保留灯光与动作」 |
| 「原 H3 视频保留」 | `CandidateList.tsx:52` | 「原视频保留」 |
| 「通过本地 ffmpeg 合成」 | `Export.tsx:544` | 「在本机完成合成，不调用云端模型」 |
| 「父版本 {hash8}」 | `CandidateList.tsx:76`、`CharacterWorkspace.tsx:324` | 整句移入技术详情 |
| 「任务 {id} · 远端 {providerTaskId}」 | `VideoGeneration.tsx:93` | 「已在云端排队」，ID 移入技术详情 |
| 「申请编号 {nonce} · 输入版本 {expected}」 | `VideoRetake.tsx:67` | 整句移入技术详情 |
| 「角色编号：{id} · 版本 {n}」 | `CharacterWorkspace.tsx:568` | 整句移入技术详情，折叠区标题保留「角色版本信息」 |
| 「{job.id.slice(0, 8)}」 | `Export.tsx:649` | 从行内移除，移入技术详情 |
| 「Picture 1 · 输入素材 · {asset_id}」 | `VideoGeneration.tsx:71` | 「画面素材 1」，asset id 移入技术详情 |
| 「并发上限 2（服务端可配置）」 | `VideoGeneration.tsx:73` | 「同时最多生成 2 个镜头」 |
| 「预计 ¥X.XX（非账单）」 | `Creative.tsx:1057` | 「预计 ¥X.XX，实际以服务商结算为准」 |
| 「最多 {calls} 次调用」 | `Creative.tsx:1052` | 「本次将调用模型 {calls} 次」 |
| 「调用失败不会伪装成功；外部请求超时可能已计费，需明确重试。」 | `Creative.tsx:1060` | 「调用失败会如实告知，不会静默重试。若请求超时，可能已产生费用。」 |
| 「本系统未实现自动视觉一致性审核。」 | `Creative.tsx:657` | 删除整句，改为「外观与表演请在预览中确认。」 |
| 「多角色参考图上限：{n} 张。降级原因保存在候选和任务中。」 | `Creative.tsx:660-663` | 删除「降级原因」句，改为「本镜最多使用 {n} 张参考图。」 |
| 「素材确认：X 个环境版本；预演：已确认；动态视频艺术验收：N/M 镜。」 | `Creative.tsx:945` | 拆成独立的状态行，见 T1-C3 |
| `operationNames[op] \|\| "生成任务"` 的兜底 | `shared.tsx:188` | 兜底改为「生成任务 · 类型未知」，并优先使用后端 `typeLabel`，见 T1-C1 |

替换完成后，用以下命令生成**待分类清单**：

```bash
grep -rnE "MiniMax|mimo-v2|H3|ffmpeg|providerTaskId|parent_revision|asset_id|nonce" \
  src/features src/components --include=*.tsx --include=*.ts \
  | grep -v "copy.ts"
```

**这条命令的输出不要求为空。** 把数据传给 `<TechnicalDetails data={...}>` 的代码行必然会被命中，那是正确写法。要求的是**逐条分类**：

> **说明**：该清单必然包含两类命中。一类是**渲染**，即字符串最终出现在默认界面上，这是缺陷；另一类是**传参**，即把原始数据交给 `TechnicalDetails` 或用于请求构造，字符串不出现在默认界面上，这是正确写法。区分方法是读命中行的上下文，确认该标识是否进入了 JSX 的可见位置。

完成报告中必须包含一张分类表，覆盖清单中的每一行：

| 文件:行 | 标识 | 分类（渲染 / 传参） | 判断依据 |

分类为「渲染」的行数为 0，才算本条目通过。任何无法归类的命中都必须在报告中列出，不要自行判断为传参。

#### T1-B 验收标准

1. 断开后端进程后，在任意页面触发一次读操作，界面显示中文提示与重试建议，不出现 `Failed to fetch` 或其他英文。
2. T1-B5 后缀清单已完成逐行分类，分类为「渲染」的行数为 0。
3. 四个 `技术详情` 折叠区外观一致，默认全部折叠。
4. 打开「生成视频」弹窗，标题为「生成分镜视频」，正文中不出现供应商名、模型 ID 或内部 ID。

### T1-C 信息主次与费用弹窗

#### T1-C1 任务列表可辨识

后端 `Task` 响应已包含 `typeLabel` 字段（实测取值为「生图」「视频」「合成」「剧本」「配音」），前端从未使用。同时，实测 36 条任务中有 14 条的 `operation` 为 `null`，这些任务在 `shared.tsx:177,188` 回落到统一的「生成任务」，导致任务列表出现 12 行以上完全相同的条目。

改动 `TaskFeedback`：

- 标题取 `operationLabels[op] ?? typeLabel ?? "生成任务"`，其中 `typeLabel` 直接读后端字段。
- 标题后追加该任务关联的分镜序号与标题，例如「镜头 03 · 微光亮起」；无关联分镜时显示所属阶段，例如「项目级 · 故事方案」。
- 追加相对时间，例如「12 分钟前」。
- 关联分镜有画面时，在标题左侧渲染 40×40 缩略图。
- `maxItems` 默认值保持 1 不变，`Creative.tsx:985` 的全量面板保持 100。
- 全量任务面板按状态排序：失败与已取消置顶，其次进行中，最后已完成。

#### T1-C2 收敛分镜检视面板

`Creative.tsx:720-756` 当前在单行平铺 5 个同权重按钮。改为两组，每组一个主按钮与一个次级入口：

- **画面组**：主按钮「生成画面」（对应现有「生成 / 复用画面候选」）；次级为下拉，包含「重新抽取画面」「生成结束状态尾帧」。
- **声音组**：主按钮「生成配音」（对应现有「生成变化台词的配音」）；次级为下拉，包含「重录本镜全部配音」。

保留全部原有功能与禁用条件，只改布局与层级。下拉使用原生 `<details>` 或已有 `Modal` 组件，不引入新依赖。

#### T1-C3 状态句拆分

`Creative.tsx:945` 当前把三个正交维度压成一句话。改为三行独立状态，每行结构为「标签 + 值 + 状态色」：

- 环境素材：已确认 1 个地点 / 共 1 个
- 静态预演：已确认 / 待确认
- 镜头艺术验收：5 / 5 已完成

状态色只用于最后一列，标签与值使用正文色。不得把三个维度塞回同一行。

#### T1-C4 费用弹窗补全信息

`Creative.tsx:1038-1087` 的费用弹窗当前只显示调用次数与总价。补三件事：

- **列出将被生成的具体对象。** 调用 `/estimate` 时若 `quote.request.operation === "batch"`，展示将被处理的镜头列表（序号与标题）与资产类型。单目标操作展示目标名称即可。
- **价格未配置时不再显示无意义数字。** 当 `estimateCents === null` 时，隐藏「本次将调用模型 N 次」这一行，改为显示「当前未配置计价规则，本次将按服务商实际用量计费。」并要求用户勾选一个确认框后才能点击「开始生成候选」。
- **「开始生成候选」按钮明确后果。** 按钮副标题说明「生成结果会作为候选保存，选用后才替换当前内容」。

`backend/app/api/routers/creative.py:713-728` 的 `estimate` 响应新增 `targets` 字段，列出将被处理的对象，供前端渲染。这是新增字段，不破坏现有消费者。

#### T1-C 验收标准

1. 打开生成任务全量面板，任意两行标题不相同；有分镜关联的行显示分镜序号与标题。
2. 分镜详情面板中，画面与声音各只有一个主按钮，其余入口在次级下拉中。
3. 导出阶段就绪检查区显示三行独立状态，不再出现分号连接的长句。
4. 在未配置计价的环境下点击「生成缺失画面与配音 · 先估算」，弹窗不出现「最多 0 次调用」，且「开始生成候选」在勾选确认框前不可点击。

### T1-D 视觉与交互缺陷

本阶段逐条关闭评估报告 §3.5 中的可见缺陷。每条都是独立的小改动，但必须逐条验证。

#### T1-D1 修复导出页布局空洞

实测导出页在约 1000px 处左列结束，右列延伸到 2375px，中间约 1400px 为纯黑。根因是 `src/app/globals.css:3041-3052` 的 `.export-columns` 为两列 grid，且 `.export-preview-panel` 使用 `align-self: start`。

改法：把右侧「导出设置」与「结构就绪与作品验收」拆成两个独立面板。设置面板留在右列，验收面板移到左列播放器下方、镜头条之前。改完后左列高度应与右列接近，页面底部不出现超过 200px 的空白区域。

#### T1-D2 修复裸链接「下载封面」

`Export.tsx:572-576` 的封面下载是无样式的裸 `<a>`。改为带 `className="btn"` 的按钮样式，并加下载图标，与相邻按钮视觉一致。

#### T1-D3 修复项目封面破图

`Home.tsx:276-280` 的 `<img src={p.cover}>` 无兜底，无分镜项目渲染空 src，导致破图、显示 alt 文本，并产生 React 控制台警告。

改法：`p.cover` 为空时不渲染 `<img>`，改用带项目名首字的占位块，样式与现有封面容器一致，保留 `cover-ratio` 与 `cover-title` 叠层。

#### T1-D4 移除假英文标题

`Home.tsx:295-303` 按 `projects.indexOf(p) % 5` 硬编码五个与项目内容无关的英文片名，实测把「宿舍八卦风暴」标为 "THE LAST DELIVERY"。

改为：优先使用项目名，英文标题仅在项目确有英文名时显示。当前数据模型没有英文字段，因此直接移除该叠层，或改为显示项目名。**不得保留任何与项目内容无关的装饰性文字。**

#### T1-D5 修复警告样式误用

`Creative.tsx:692-696` 无论是否过期，都把状态行包在 `creative-warning` 中。改为按条件切换：

- `image_stale || audio_stale` 为真：使用 `creative-warning`。
- 否则：使用普通 `helper` 样式。

同时把「需生成 / 已过期」改为更直白的「待更新」，「可复用」改为「已就绪」。

#### T1-D6 修复空音频播放器

角色编辑页显示「当前声音 · 已有样本」时，播放器为 `0:00 / 0:00`。改为：音频时长未知或为 0 时不渲染播放器，只显示「已有声音样本」文字与「试听」按钮；点击后再加载播放器。

#### T1-D7 恢复移动端提示

`workbench.css:930` 的 `body:has(.creative-workbench) .mobile-notice { display:none }` 在工作台隐藏了最需要的提示。删除该规则。改为在创作工作台内、宽度小于 1000px 时，于阶段导航上方渲染一条提示条：「当前屏幕较窄，分镜编辑建议在桌面端进行」，并保留「继续使用」关闭按钮。

#### T1-D8 处理三个死开关

实测 `public/assets/intro.mp4`、`public/assets/watermark.png` 不存在，`public/assets/bgm/` 目录不存在。导出页三个开关的副标题却写「使用服务端已配置素材」。

采用「按存在性渲染」策略，不补造素材：

- 后端 `GET /api/creative/projects/{id}` 的 `capabilities` 新增 `intro`、`watermark`、`bgmPresets` 三个布尔字段，由服务端检查文件是否存在得出。
- 前端据此渲染：为真时显示开关与曲风预设；为假时**隐藏整个控件**，改为一行说明「本部署未配置片头素材」，不渲染可点击但无效的开关。
- 用户上传 BGM 的功能保留，不受影响。

#### T1-D 验收标准

1. 导出页整页截图（`fullPage: true`）高度不超过 1800px，页面底部空白不超过 200px。
2. 「下载封面」按钮与相邻按钮样式一致。
3. 首页对无分镜项目显示占位块，控制台无 `empty string` 相关警告。
4. 首页任意项目卡片上不出现与项目名无关的文字。
5. 一个素材全部就绪的镜头，其状态行不显示为警告样式。
6. 移动端宽度 420px 打开创作工作台，出现窄屏提示。
7. 在当前部署下打开导出页，不出现片头、水印、BGM 曲风三个开关。

### T1-E 工程加固与配置修正

#### T1-E1 统一设计 token

`DESIGN.md` 规定主金色为 `#F5B942`，`workbench.css:3` 覆盖为 `--cw-gold: #e2bd75`，另有至少八个近似金色散落各处。

- 把 `--cw-gold` 收敛为 `#F5B942`。
- 在 `globals.css` 的 `:root` 中定义完整的语义色 token 集合，`workbench.css` 只引用不重定义。
- 近似金色全部收敛到 token。允许保留的例外只有渐变端点与阴影色，且必须在完成报告中列出。

#### T1-E2 移除 `:has()` 布局劫持

删除 `workbench.css:881-882` 的 `.cw-cast:has(.cw-focused-character) > ...` 规则，改为由组件显式添加状态类。组件在进入角色聚焦态时给 `.cw-cast` 添加 `cw-cast--focused` 类，CSS 针对该类书写规则。

#### T1-E3 参考图预算与剧本形状对齐

`backend/app/core/config.py:31` 的 `image_max_references` 默认值为 2，导致「2 个角色 + 1 个已确认环境」的镜头无法生成参考图，而这正是短剧的主体镜头形态。

两步改动：

- `.env.local` 与 `.env.example` 中把 `IMAGE_MAX_REFERENCES` 提高到 4。
- `services/creative.py:816-829` 的分镜生成 prompt 增加约束，明确告知模型每镜参考图预算为 `image_max_references` 张，角色与环境参考合计不得超过该值。当预算不足以覆盖角色数加环境数时，prompt 要求模型减少同框角色数或拆分镜头。

同时在 `creative.py:626-630` 的 `REFERENCE_LIMIT` 错误信息中给出可操作建议，例如「本镜需要 3 张参考图，当前上限为 2。请减少同框角色、拆分镜头，或提高 IMAGE_MAX_REFERENCES。」

> **注意**：本条目同时是任务三的前置条件。口型同步需要清晰正脸，而多角色同框镜头无法满足，因此拆分镜头的引导必须在本阶段建立。

#### T1-E4 前端测试基建与首批测试

当前后端有 24 个测试文件共 4183 行，前端为零。评估报告 §3.5 的十四项缺陷中，B1–B10 十项位于前端且全部可被组件测试捕获；B11、B12、B14 三项位于后端，其回归测试归入 T1-E5；B13 由 T2-C1 处理。

- 引入 `vitest` 与 `@testing-library/react` 作为 devDependency，在 `package.json` 新增 `test:web` 脚本。**这是本文档允许的唯一新增依赖。**
- 为下列行为编写测试，每个缺陷至少一条：
  - 阶段计数与阶段标签在给定 `workflowReadiness` 下的一致性（覆盖 T1-A3、T1-A4）。
  - 空态三分支选择逻辑（覆盖 T1-A5）。
  - `errorMessage` 对十三种错误码与未知错误的返回（覆盖 T1-B1）。
  - `api` 在 `fetch` 抛出 `TypeError` 时返回 `NETWORK_ERROR`（覆盖 T1-B2）。
  - `TaskFeedback` 在 `operation` 为 `null` 且 `typeLabel` 存在时的标题（覆盖 T1-C1）。
  - 项目封面在 `cover` 为空时的占位渲染（覆盖 T1-D3）。
  - 状态行的样式类在 stale 与非 stale 下的差异（覆盖 T1-D5）。
- 测试文件放在被测模块同级，命名为 `<模块>.test.tsx`。

#### T1-E5 后端正确性修复与死字段清理

本条目关闭报告 §3.5 中的三项后端缺陷（B11、B12、B14），并额外清理一个后端死字段 `capabilities.visualAudit`。四项改动都不改变创作能力，只修正已有行为。

**E5-a 关闭 B12：worker 写入路径补齐项目行锁。**

API 的写路径都经过 `project()` 取项目行的 `SELECT … FOR UPDATE`（`routers/creative.py:32-35`），但 worker 侧两处直接调用 `save_state`，没有取锁：

- `backend/app/tasks/execute.py:283-300`（视频轨迹与 `video_takes` 写入）
- `backend/app/services/voice_continuity.py:263-271`（整段配音的场景重写）

而 `save_state` 从**内存中**的行对象推导新版本号（`services/creative.py:41`），因此并发的 API 编辑可能被静默覆盖，版本号还可能回退，使过期的 `expected` 通过 `check_version`。

改法：**不要从零写加锁逻辑——本仓库已经有现成实现。** `backend/app/services/video_correction.py` 的 `locked_scene(db, scene_id)`（约 `:99-105`）正是「取项目行锁 → 重新读取场景行 → 刷新 → 校验空闲」的模式：

```python
async def locked_scene(db, scene_id):
    scene = await require(db, Scene, scene_id)
    project = await require(db, Project, scene.project_id, True)   # True = FOR UPDATE
    scene = await require(db, Scene, scene_id, True)
    await db.refresh(scene)
    await ensure_idle(db, scene.project_id, scene.id)
    return project, scene
```

把该函数提升为共享工具（例如移到 `services/creative.py` 或新建 `services/locking.py`），让 `video_correction`、`voice_continuity` 与 `execute.py` 三处共用同一实现。**不要复制粘贴三份。**

接入点：

- `backend/app/tasks/execute.py` 约 `:283-300`（视频轨迹与 `video_takes` 写入）
- `backend/app/services/voice_continuity.py` 约 `:263-271`（整段配音的场景重写）

关键要求：在调用 `save_state` 前取得项目行锁，并**重新读取**场景行，不要在锁外继续使用旧的内存对象——`save_state` 从内存对象推导新版本号（`services/creative.py:41`），用旧对象就等于绕过了锁。

新增回归测试 `backend/tests/test_worker_locking.py`，构造「worker 写场景的同时 API 修改同一场景」的并发场景，断言版本号单调递增、API 的修改不被静默丢弃。

**E5-b 关闭 B14：环境文案改动的失效精度。**

`services/creative.py:177` 的 `save_location` 无条件设置 `shots_confirmed=False`，即使只改了一个错别字也会取消整个分镜阶段的确认。

改法：区分「影响画面生成的字段」与「纯描述字段」。参考图、状态、地标、光照、色调、空间关系属于前者，仍然使阶段失效；`name`、`description` 等纯文案字段只更新内容与版本，不取消 `shots_confirmed`。

新增回归测试，断言「只改环境名称」不改变 `shots_confirmed`，「更换环境参考图」会改变。

**E5-c 关闭 B11：清理 `creative.stage` 死字段。**

`creative.stage` 在 `services/creative.py:350`、`:420` 与 `routers/creative.py:627`、`:642`、`:647`、`:848` 共六处被写入，但后端从不读取，前端也从不读取（阶段门禁实际由 `plan_confirmed`、`cast_confirmed`、`shots_confirmed` 三个布尔值承担）。保留会让后续开发者误以为存在一个阶段状态机。

改法：删除全部写入点与字段本身。

> **注意**：`creative.stage` 会出现在 `GET /api/creative/projects/{id}` 响应的 `project.creative` 对象中（实测该项目的值为 `"generation"`）。因此删除它也属于 API 响应形状变更，已一并列入硬约束第 4 条的命名例外。

**E5-d 清理 `capabilities.visualAudit` 死字段。**

`routers/creative.py:136` 的 `capabilities` 返回 `"visualAudit": "人工预览，未实现自动外观一致性审核"`。实测前端从未读取该字段。它的值是自我否定式表述，且与 T1-B 建立的语言层原则冲突。

改法：删除该键。

> **本条目是硬约束第 4 条的命名例外。** T1-E5 被明确授权修改 API 响应形状，仅限以下两处删除：`project.creative.stage` 与 `capabilities.visualAudit`。除此之外，任务一不得增删任何既有响应字段。这两个键都经实测确认无任何前端消费者。

#### T1-E 验收标准

1. `grep -c "!important" src/features/creative/workbench.css` 输出为 0。
2. `grep -n ":has(" src/features/creative/workbench.css` 输出为空。
3. `npm run test:web` 通过，且 B1–B10 十项前端缺陷每项至少有一条对应测试。
4. 修改 `IMAGE_MAX_REFERENCES=4` 后，构造一个 2 角色加 1 环境的镜头，估算请求不再返回 `REFERENCE_LIMIT`。
5. `backend/.venv/bin/python -m pytest backend/tests/test_worker_locking.py -q` 通过。
6. 只修改环境名称后，该项目的 `shots_confirmed` 保持为真。
7. `grep -rn 'visualAudit\|"stage": "plan"\|st\["stage"\]\|stage="characters"\|stage="storyboard"\|stage="generation"' backend/app/` 输出为空。

   > 该模式覆盖全部六处写入点：`services/creative.py:350`、`:420`，`routers/creative.py:627`、`:642`、`:647`、`:848`。注意 `tasks/execute.py:68` 的 `"stage": message` 属于导出进度事件，是无关的同名键，不应被删除；上面的模式刻意不匹配它。

## 3. 任务二：分集结构

任务二把「一个项目等于一条短片」扩展为「一个项目等于一部多集短剧」。这是本项目从短片工具变成短剧平台的分水岭，也是开源界共识的第一级结构。

任务二在任务一完成后开始。任务一建立的文案字典、`TechnicalDetails` 组件与阶段计数口径必须被复用，不得另起一套。

### T2-0 契约变更授权（先读这一节）

任务二的本质是把项目级状态拆成「项目级 + 集级」，这**必然**改变若干既有 API 响应与 JSON 结构。为避免与「保持现有 API 契约」的约束冲突，此处一次性列全部授权变更。**下列变更之外的任何既有字段增删或结构改动，都命中停止条件。**

**授权的响应结构变更（共 5 项）**：

| # | 变更 | 位置 | 性质 |
| --- | --- | --- | --- |
| 1 | `project.creative` 移出 6 个键：`plan`、`plan_draft`、`confirmed_plan`、`plan_confirmed`、`shots_confirmed`、`preview_confirmation` | `GET /api/creative/projects/{id}` | **删除**既有键，值搬入 `Episode.creative` |
| 2 | `scene.creative.dependency_stamp` 从平铺字典改为 `{"characters": {...}, "locations": {...}}` | `GET /api/creative/projects/{id}` 的 `scenes[]` | **修改**既有键结构 |
| 3 | `project.creative.narrator` 新增 `model` 键 | 同上 | 新增 |
| 4 | `project.creative` 新增 `episodes` 摘要数组（集号、标题、状态） | 同上 | 新增 |
| 5 | `workflowReadiness` 新增 `episodes` 数组，响应顶层新增 `activeEpisodeId`；既有键的**语义**改为作用于当前集，但**键与类型不变** | 同上 | 新增（不改既有键） |

> **第 5 项刻意设计为只增不改。** 既有键被 3 条测试断言引用（`test_creative.py:408`、`test_creative_assets.py:248,257`），而本任务的硬约束禁止修改既有断言。若把结构改成嵌套对象，这 3 条断言会失效且无法合法修复，任务会卡死。详见 T2-A5。

**授权的新增端点**：T2-B1 的五个集管理端点。
**授权的旧端点行为变更**：`confirm/plan` 与 `confirm/shots` 的作用域改为集级，但路径保留为别名（T2-B2）。
**授权的新增错误码**：`EPISODE_HAS_RUNNING_TASK`。
**授权的新增配置**：`EPISODE_MEMORY_MAX_CHARS`。

**明确不在授权内的**：`Character`、`Asset`、`Task`、`ExportJob` 的既有字段结构；`Candidate.kind` 的既有取值语义；`capabilities` 的既有键。这些一律不动。

### T2-A 数据模型与迁移

#### T2-A1 新增 Episode 实体

新增 `Episode` 表：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `String(36)` 主键 | 同现有实体 |
| `project_id` | FK → `project.id`，级联删除，建索引 | |
| `order_index` | `int` | 集号，从 1 开始 |
| `title` | `str` | 集标题 |
| `synopsis` | `str` | 本集梗概，用于下一集的剧情记忆 |
| `status` | `str` | 复用现有项目状态词表 |
| `creative` | `JSON` | 见 T2-A2 |
| `created_at` / `updated_at` | 同现有实体 | |

约束：`UniqueConstraint("project_id", "order_index")`。

#### T2-A2 划分项目级与集级状态

当前 `Project.creative` 同时保存了项目级与集级状态。按下列规则拆分：

**保留在 `Project.creative`（全剧共享）**：

- `locations`（场景与地标在全剧复用，这是角色与环境一致性的基础）
- `narrator`
- `cast_confirmed`（演员表全剧共享）
- `style`、`ratio`（现有字段已在 `Project` 表上）
- `version`、`revision`
- `export_confirmation`（保留为全季合辑的验收）

**迁移到 `Episode.creative`（每集独立）**：

- `plan`、`plan_draft`、`confirmed_plan`
- `plan_confirmed`
- `shots_confirmed`
- `preview_confirmation`

> **说明**：`cast_confirmed` 留在项目级是刻意的。角色定妆跨集共享，正是分集结构要保护的一致性资产。

> **这是 T2-0 授权表第 1 项的授权变更。** 搬移意味着 `GET /api/creative/projects/{id}` 的 `project.creative` 不再包含这 6 个键，属于删除既有键。除这 6 个键外，`project.creative` 的其它既有键一律不动。

#### T2-A3 Scene 归属到集

`Scene` 新增 `episode_id` FK。

当前 `Scene` 的唯一约束是 `UniqueConstraint("project_id", "order_index", name="uq_scene_order")`。改为 `UniqueConstraint("episode_id", "order_index", name="uq_scene_episode_order")`。`project_id` 列保留（大量查询依赖它），但唯一性判定改由 `episode_id` 承担。

**这一改动会波及全部 5 处场景创建点，必须逐个更新。** 把 `episode_id` 改为 `NOT NULL` 之后，任何不设置该字段的创建路径都会抛 IntegrityError。实测的创建点：

| # | 位置 | 现状 | 需要做什么 |
| --- | --- | --- | --- |
| 1 | `tasks/execute.py` 约 `:102` | `Scene(project_id=project_id, order_index=i, **values)` | 传入 `episode_id`；`order_index` 改为**集内**序号 |
| 2 | `routers/creative.py` 约 `:849` | `Scene(project_id=id, order_index=i)` | 同上。这是创作流程的分镜生成路径，`target` 或当前集提供 `episode_id` |
| 3 | `routers/resources.py` 约 `:67` | `Scene(project_id=row.id, order_index=i, ...)` | 旧版端点。需解析该项目的第 1 集作为默认归属 |
| 4 | `routers/resources.py` 约 `:260` | `Scene(project_id=id, order_index=len(scenes), ...)` | 同上，且 `len(scenes)` 是**项目级**计数，必须改为**集内**计数 |
| 5 | `routers/resources.py` 约 `:334` | `Scene(order_index=len(rows), **values)` | 复制场景。`values` 可能已含 `episode_id`，需显式确认；`len(rows)` 同样要改为集内计数 |

**第 3、4、5 处属于旧版端点**（`/api/projects/{id}/scenes`），它们没有剧集概念。处理方式：这些端点统一归属到项目的第 1 集。不要为它们新增剧集参数——旧端点保持既有契约，只补默认归属。

> **这是本任务最容易漏的地方。** 只改模型与迁移、不改这 5 处，会在运行期炸出 IntegrityError，而且第 4、5 处的 `len(scenes)` / `len(rows)` 会产生跨集重复的 `order_index`，触发唯一约束冲突。

#### T2-A4 迁移 0004

新增 `backend/alembic/versions/0004_episodes.py`，`upgrade` 按顺序执行：

1. 创建 `episode` 表与索引。
2. 为 `scene` 新增可空列 `episode_id` 与外键。
3. **数据搬移**：对每一个已有项目，创建一条 `Episode`，`order_index = 1`，`title` 取项目名，`synopsis` 取原 `creative.plan.synopsis`；把 T2-A2 列出的集级字段从 `Project.creative` 搬入 `Episode.creative`，并从 `Project.creative` 中移除这些键。
4. 把该项目下所有 `Scene` 的 `episode_id` 指向新建的集。
5. 删除旧的 `uq_scene_order` 约束，建立 `uq_scene_episode_order`。
6. 把 `scene.episode_id` 改为 `NOT NULL`。

`downgrade` 必须把**结构**还原到迁移前的形状：把集级字段写回每个项目 `order_index = 1` 的那一集的 `Project.creative`，删除其余集，恢复 `uq_scene_order`，删除 `scene.episode_id` 列，删除 `episode` 表。

> **区分「结构还原」与「数据保全」**：`downgrade` 能还原的是**表结构与 JSON 键的形状**，不能还原第 2 集及以后的内容——那些数据在降级时会被删除。硬约束第 1 条的「还原到迁移前的数据形状」指的是前者。

> **不要用 `input()` 做交互式确认。** 本任务的验收流程会以非交互方式连续执行 `alembic upgrade head` → `downgrade -1` → `upgrade head`；任何等待标准输入的代码都会让验收挂起。数据丢失的警告放在文件头注释与 downgrade 函数的 docstring 里即可。如果你希望保留一层保险，用**环境变量**门控（例如未设置 `CINEAI_ALLOW_EPISODE_DOWNGRADE=1` 时抛错并说明原因），但这会让验收命令多一步——默认不启用。

**关于约束与索引**：硬约束第 1 条的「只新增与搬移，不删除列、不删除行」针对的是**数据**，不是**结构**。删除 `uq_scene_order` 唯一约束、把 `scene.episode_id` 从可空改为非空，都是本任务必需的结构操作，在授权范围内。

迁移完成后必须验证：库中全部既有项目的场景数、候选数、任务数**与迁移前基线逐项一致**，且每个项目恰好有一条集记录。基线数字由操作者在迁移前用脚本记录，不要写死在文档里。

#### T2-A5 workflowReadiness 增加集级维度

**不要重构 `workflowReadiness` 的结构。** 这一条必须按「只增不改」的方式做，原因见下。

现状（T1-A3 落地后的实测结构）是一个**扁平**对象：

```jsonc
"workflowReadiness": {
  "plan": true, "cast": true, "locations": true, "shots": false, "export": false,
  "structure_ready": true, "materials_confirmed": true, "preview_confirmed": false,
  "video_accepted": false, "scene_reviews": [...], "warnings": [...]
}
```

它被前端 4 处读取（`Creative.tsx` 的计数、阶段标签、就绪行，`types.ts` 的类型声明），并被 **3 条既有测试断言**引用：

- `backend/tests/test_creative.py:408` 断言 `f["workflowReadiness"]["shots"] is True`
- `backend/tests/test_creative_assets.py:248,257` 断言 `f["workflowReadiness"]["preview_confirmed"]`

硬约束第 2 条禁止修改既有测试的断言。如果把结构改成嵌套的 `{project: {...}, episodes: [...]}`，这 3 条断言会全部失效，而你又不被允许改它们——任务会卡死在自相矛盾里。

**因此采用只增不改的方案：**

1. **保留全部既有键，语义改为「作用于 `activeEpisodeId` 对应的那一集」。** `plan`、`shots`、`structure_ready`、`preview_confirmed`、`video_accepted`、`scene_reviews`、`warnings` 改为从当前集的数据推导。迁移后每个既有项目只有第 1 集，且它就是 active 集，因此这 3 条断言的结果不变。
2. **新增 `episodes` 数组**，给集选择器提供每集状态：

   ```jsonc
   "episodes": [
     { "id": "...", "orderIndex": 1, "title": "...", "plan": true, "shots": true, "preview": true }
   ]
   ```

3. **项目级键保持全局语义**：`cast`、`locations`、`export` 仍读项目级数据。
4. **在响应顶层新增 `activeEpisodeId`**（与 `workflowReadiness` 平级），前端据此决定展示哪一集。

`stageStates` 同样只增不改：既有键 `plan`/`characters`/`storyboard` 的语义改为当前集，新增 `episodes` 数组。它与 `workflowReadiness` 必须共用同一数据来源，这是 T1-A3「两个来源收敛到一个函数」原则在分集下的延续。

> **注意 `materials_confirmed` 是混合键**：它同时要求 `cast_confirmed`（项目级）与所有场景 clean（集级）。保持现有语义，只是「所有场景」的范围从项目改为当前集。

### T2-B 后端接口

#### T2-B1 集管理端点

新增：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/creative/projects/{id}/episodes` | 列出全部集，含每集状态与镜头数 |
| `POST` | `/api/creative/projects/{id}/episodes` | 新建一集，`order_index` 取当前最大值加一 |
| `PATCH` | `/api/creative/episodes/{eid}` | 改标题与梗概 |
| `POST` | `/api/creative/episodes/{eid}/archive` | 归档，不删除 |
| `POST` | `/api/creative/episodes/{eid}/reorder` | 接受 `order_index`，重排 |

全部端点沿用现有的项目行锁与版本校验模式（`routers/creative.py:32-35` 的 `project()` 与 `check_version`）。

#### T2-B2 阶段确认改为集级

后端**没有**「当前集」这个概念，集必须由请求显式指定。定义如下，不要自行发明其他方式：

- **新路径**：`POST /api/creative/episodes/{eid}/confirm/{stage}`，集由路径参数给出。`stage` 取值 `plan` 或 `shots`。
- **旧路径别名**：`POST /api/creative/projects/{id}/confirm/{stage}` 保留一个版本，内部**固定转发到该项目 `order_index` 最小的集**（不是「当前集」，后端无从得知），并在响应头加 `Deprecation: true`。下一个版本移除。
- `confirm/cast` 保持项目级，路径 `POST /api/creative/projects/{id}/confirm/cast` 不变。

**前端的「当前集」是客户端状态。** 前端调新路径时必须把当前集的 `eid` 拼进 URL，不得依赖服务端猜测。

#### T2-B3 生成端点区分作用域

`plan` 与 `storyboard` 两个操作作用于集，`character_*`、`location_image`、`voice_*` 作用于项目。

关于请求体的 `target` 字段，**澄清一处容易误读的地方**：现有前端在 `plan` 与 `storyboard` 两个操作上**从不传 `target`**（见 `Creative.tsx` 的 `generate({ operation: "plan", nonce })` 与 `generate({ operation: "storyboard", ... })`），`target` 只在角色、场景、地点等操作上使用。因此这里不是「重定义既有语义」，而是**为一个当前为空的字段赋予含义**：

- 当 `operation` 为 `plan` 或 `storyboard` 时，`target` 解释为 `episode_id`。
- `target` 为空时，回退到该项目 `order_index` 最小的集，保持旧客户端的现有行为。

`estimate` 响应中的 `targets` 字段（T1-C4 新增）在集级操作下列出该集将被生成的镜头。

#### T2-B4 剧情记忆

这是分集结构最关键的生成侧改动。生成第 N 集（N 大于 1）时，把前面各集的上下文注入 prompt：

- `plan` 生成：注入全季主线（取第 1 集 `confirmed_plan` 的主题与人物关系）、以及前面每一集的 `synopsis` 与结尾状态。
- `storyboard` 生成：注入本集 `confirmed_plan`、上一集的结尾镜头描述、以及全剧角色表（角色 ID 与固定身份特征）。

注入内容设长度上限，超出时保留最近三集与第 1 集，中间集只保留 `synopsis`。上限以字符数配置，新增 `EPISODE_MEMORY_MAX_CHARS`，默认 4000。

> **说明**：开源界的经验是跨集一致性比跨镜一致性更难。wind-comic 为此专门增加了「剧情记忆」，并明确说明此前各集独立成篇的问题。本条目是分集结构的核心价值，不是可选优化。

#### T2-B 验收标准

1. `GET /api/creative/projects/{id}/episodes` 对**每一个既有项目**各返回一条集记录，镜头数与迁移前基线一致（项目数量由迁移前记录的基线决定，不要写死）。
2. 新建一集后，在其下生成分镜，不影响第 1 集的场景。
3. 对第 2 集生成 `plan` 时，抓取实际发送给模型的 prompt，其中包含第 1 集的 `synopsis`。
4. 旧路径 `POST /api/creative/projects/{id}/confirm/plan` 仍可用，且作用在第 1 集。

### T2-C 生成与失效传播调整

#### T2-C1 修复依赖戳单字段问题

评估报告 §2.4-P2-13 指出 `dependency_stamp` 是单字段，角色戳与环境戳互相覆盖。改为集合结构：

```python
dependency_stamp = {"characters": {character_id: revision}, "locations": {location_id: revision}}
```

同步修改 `review_fingerprint`、`preview_fingerprint`、`render_fingerprint` 的输入组成，使其覆盖全部依赖。迁移时把旧格式的单字段值转换为新格式。

> **这是 T2-0 授权表第 2 项的授权变更。** `scene.creative` 会出现在 `GET /api/creative/projects/{id}` 的 `scenes[]` 里，因此该结构改动是响应形状变更。除此之外，`scene.creative` 的其它既有键一律不动。

#### T2-C2 修复旁白未钉住模型

`init_project` 写入 `narrator` 时缺少 `model` 字段，导致运行时回落到实时配置，改 TTS 模型只让旁白失效而人物对白不失效。改为在 `init_project` 与 `PATCH /narrator` 两处都写入当前 `tts_model`，行为一致。

> **这是 T2-0 授权表第 3 项的授权新增。** 只新增 `model` 键，不改动 `narrator` 的既有键。

#### T2-C3 集级失效

新增集时不得使已有集失效。删除或归档一集时，若该集有未完成任务，返回 `SCENE_HAS_RUNNING_TASK` 同级的 `EPISODE_HAS_RUNNING_TASK` 409。

跨集共享的角色或环境变更，仍按现有规则使全部相关集的镜头失效——这是正确行为，不需要修改。

#### T2-C 验收标准

1. 同时修改一个角色与一个地点后，该镜头的 `review_fingerprint` 与修改前不同。
2. 修改 `MINIMAX_TTS_MODEL` 后，旁白与人物对白**同时**被标记为需要更新。
3. 新建第 2 集后，第 1 集的 `shots_confirmed` 保持为真。

### T2-D 前端分集界面

#### T2-D1 集选择器

在创作工作台的页头下方、阶段导航上方，新增一条集选择栏。每一集渲染为一个标签，显示集号、标题与状态点。当前集高亮。右侧提供「新建一集」入口。

集数量为 1 且项目创建时选择单集时，隐藏该栏，避免单集项目看到无意义的控件。

#### T2-D2 阶段作用域可视化

阶段导航的五个阶段中，`01 故事方案` 与 `04 分镜创作` 是集级的，`02 角色形象与声音` 与 `03 环境素材` 是项目级的。必须在界面上区分，否则用户会误以为换集后角色也要重做。

改法：项目级阶段在标签下加一行小字「全剧共享」，并使用与集级阶段不同的状态点样式。切换到另一集时，项目级阶段的状态保持不变。

#### T2-D3 分集管理页

新增 `/episodes` 路由，或在创作工作台内以辅助面板形式提供。展示每集的：集号、标题、梗概、镜头数、完成度、状态、导出记录。提供新建、编辑标题与梗概、排序、归档、导出本集的操作。

#### T2-D4 导出作用域

导出页新增作用域选择：「导出本集」与「导出全季合辑」。

技术路径要求：

- **本集导出**沿用现有流程，只处理该集的场景。`ExportJob` 需要能标识作用域：在 `ExportJob.settings` 中新增 `episode_id`（本集导出）或 `"all"`（全季），**不新增表列**。
- **全季合辑**是一个新的 compose 模式：先按 T2-D4 的顺序对每一集各自调用现有合成逻辑，得到各集成片，再用与 `compose.py` 现有 concat 相同的 concat demuxer `-c copy` 方式拼接，不重新编码各集产物。全季合辑的 `ExportJob.settings.episode_id` 为 `"all"`。
- 全季合辑的验收沿用现有项目级 `export_confirmation`；本集导出的验收使用该集自己的 `preview_confirmation`。
- 若某一集缺少可用产物，全季合辑必须**明确失败并列出缺失的集号**，不得静默跳过该集。

> **注意**：`ExportJob` 不加列、不改既有字段，只扩展 `settings` 这个 JSON 字段的内容。这不在 T2-0 的授权表内，因为它不改变响应的既有键结构，只是给既有 JSON 字段加内容。

#### T2-D 验收标准

1. 打开多集项目，集选择栏显示全部集，切换集后分镜列表随之变化，角色与环境阶段状态不变。
2. 项目级阶段标签下显示「全剧共享」。
3. 导出页可选择「本集」或「全季合辑」，全季导出产物时长等于各集之和。
4. 新建一集后，该集从零开始，不继承第 1 集的分镜。

## 4. 任务三：口型同步

任务三为每一镜增加口型同步阶段。这是本轮唯一需要额外算力的任务，因此设计上必须允许在不具备 GPU 的环境中优雅缺席。

任务三在任务二完成后开始，因为口型同步是集内逐镜操作，需要分集结构已就位。

> **重要现实约束**：开源界的口型同步方案相对视频生成模型已经落后。MuseTalk 在 4GB 显存的笔记本上处理 8 秒视频约需 5 分钟；LatentSync 对中文视频效果更好但训练与推理显存要求更高。**多人同框的口型同步在开源方案中尚未解决**，需要按发言人裁切镜头。本任务的设计必须把这些限制作为一等公民，而不是事后补丁。

### T3-A Provider 抽象与配置

#### T3-A1 新增 LipSyncProvider 协议

在 `backend/app/providers/base.py` 新增：

```python
class LipSyncProvider(Protocol):
    async def sync(
        self, video: bytes, audio: bytes, *, options: dict
    ) -> tuple[bytes, dict]: ...
```

返回的视频字节与一份报告字典。报告字段分为两部分：

**引擎提供**（来自 `http` 的 `X-Lipsync-Report` 响应头，或 `local` 命令的等价输出）：

| 字段 | 说明 |
| --- | --- |
| `engine` | 引擎名，例如 `musetalk`、`latentsync`、`stub` |
| `engine_version` | 引擎版本字符串 |
| `alignable` | 布尔。`false` 表示这个镜头做不了，必须附 `skip_reason` |
| `skip_reason` | `alignable=false` 时的具体原因，直接展示给用户 |
| `alignment_score` | 数字或 `null`。引擎未提供时必须为 `null` |

**本地计算**（不依赖引擎，见 T3-C1）：

| 字段 | 说明 |
| --- | --- |
| `duration_sec` | 输出视频时长 |
| `frames` | 输出帧数 |
| `fps`、`width`、`height` | 输出规格，用于与输入比对 |

`alignment_score` 与 `skip_reason` 由引擎决定，本地**不得**改写或估算这两个字段。

**注册方式沿用既有模式。** `providers()` 是 `@lru_cache` 的、以**位置参数**构造的 dataclass（`backend/app/providers/__init__.py`）。新增字段时必须在 `Providers` dataclass 与 `providers()` 的构造调用中**同时**按同一顺序插入。视频字段就是这个模式的现成模板：

```python
video: VideoProvider
# ...
MiniMaxVideo() if get_settings().feature_video_generation else DisabledVideo(),
```

照此写法：

```python
lipsync: LipSyncProvider
# ...
HttpLipSync() if get_settings().lipsync_provider == "http"
else LocalLipSync() if get_settings().lipsync_provider == "local"
else DisabledLipSync(),
```

`DisabledLipSync` 必须存在，即使它只返回一条「未启用」的错误。这样调用方不需要到处判空。

> **注意 `@lru_cache` 的行为**：provider 实例在首次调用 `providers()` 时按当时的配置构造并缓存。这与现有的 `video`、`tts` 字段一致。不要在运行期期待切换 `LIPSYNC_PROVIDER` 会即时生效。

#### T3-A2 三种实现

`LIPSYNC_PROVIDER` 取值为 `none`、`http`、`local`，默认 `none`。

- `none`：`capabilities.lipsync` 为 `false`，前端隐藏全部口型入口。这是默认值，保证不具备算力的部署不受影响。
- `http`：把视频与音频发到 `LIPSYNC_API_URL`。推荐方式，把 GPU 需求解耦到独立服务。参考开源界的通行做法（wind-comic 通过 `LIPSYNC_API_URL` 让用户自带引擎）。**请求与响应契约见下。**
- `local`：按 `LIPSYNC_COMMAND` 模板调用本机命令，模板支持 `{video}`、`{audio}`、`{out}` 三个占位符，命令需把处理后的视频写到 `{out}`。用于用户自行安装 MuseTalk 或 LatentSync 的场景。

**`http` 模式的请求与响应契约**（必须按此实现，测试桩也按此写）：

```http
POST {LIPSYNC_API_URL}
Content-Type: multipart/form-data

video=<binary mp4>      # 必填，本镜当前视频
audio=<binary wav/mp3>  # 必填，本镜配音音轨
options=<json string>   # 可选，{"max_speakers": 1} 等提示
```

成功响应必须是 `200` 且 `Content-Type` 为 `video/*`，响应体为处理后视频的二进制。报告通过响应头 `X-Lipsync-Report` 返回一个 URL-safe base64 编码的 JSON，字段为 `engine`、`engine_version`、`alignable`（布尔）、`alignment_score`（数字或 null）、`skip_reason`（字符串或 null）。

无法处理的镜头返回 `200` 且 `X-Lipsync-Report` 中 `alignable=false` 与具体的 `skip_reason`，**不要用 4xx 表达「这个镜头做不了」**——那是业务结果，不是传输错误。4xx/5xx 只用于真实的传输或服务失败。

> 选择 multipart 而不是 JSON+base64，是为了避免视频体积膨胀约 33%，也便于用 `curl -F` 手工验证。

新增配置项：`LIPSYNC_PROVIDER`、`LIPSYNC_API_URL`、`LIPSYNC_COMMAND`、`LIPSYNC_TIMEOUT_SECONDS`（默认 900）、`LIPSYNC_CONCURRENCY_LIMIT`（默认 1）。

#### T3-A 验收标准

1. `LIPSYNC_PROVIDER=none` 时，`capabilities.lipsync` 为 `false`，界面上搜索不到任何口型相关入口。
2. `LIPSYNC_PROVIDER=http` 且 `LIPSYNC_API_URL` 指向一个返回固定视频的测试桩时，`shot_lipsync` 操作产出一条候选。

### T3-B 生成链路

#### T3-B0 先读：视频在本仓库里**不走候选制**

这是一个容易踩空的前提，必须先讲清楚，否则 T3-B1 与 T3-D1 都会被写错。

- **图片与音频**走候选制：付费结果先写入 `Candidate`，用户点选用后经 `POST /api/creative/projects/{id}/select` 生效（`services/creative.py` 的 `select_candidate` 分支）。
- **视频不走候选制。** `select_candidate` 里**没有**视频生成结果的分支——`elif c.kind.startswith("shot_")` 只处理 `shot_image` 与 `shot_audio`。视频任务在 `tasks/execute.py` 里直接把结果写入场景：`save_state` 同时设置 `scene.video_key`、`creative.video`（一条 trace）与 `creative.video_takes`（历史 take 列表）。
- **唯一的例外是 `video_correction`**：本地上传的修正版视频**是**一个可选用候选，走 `/select`，由 `services/video_correction.py` 的 `select_candidate` 处理。

**所以口型同步应当参照的是 `video_correction`，不是图片候选。** 这是本任务最重要的实现指引。

`video_correction.select_candidate`（`services/video_correction.py` 约 `:293` 起）的流程是本仓库处理「可选用视频」的既有范式，逐项如下：

1. `locked_scene(db, candidate.entity_id)` —— 取项目行锁并**重新读取**场景行（该函数约在 `:99-105`，正是任务一 T1-E5-a 要复用的那个）。
2. `flow.check_version` —— 乐观并发校验。
3. `is_stale` → `STALE_CANDIDATE`。
4. 校验素材归属与内容签名（`sha256`）。
5. 组装 trace，写入 `state["video"]`、把旧 trace 追加进 `state["video_takes"]`。
6. 重置 `review` 为 `pending`，并把旧 review 推进 `review_history`。
7. `scene.video_key = asset.object_key`，`scene.status = "done"`。
8. `flow.save_state(db, scene, state, "scene")`。

口型同步按同一流程实现，差异只在第 4 步（改为校验视频与音频指纹）与第 5 步的 trace 内容。

#### T3-B1 新增 shot_lipsync 操作

新增 Celery 队列 `cineai.lipsync`，并发由 `LIPSYNC_CONCURRENCY_LIMIT` 控制。新增操作 `shot_lipsync`，输入为本镜已选视频与该镜的配音音轨。

**输出形态**：写入 `Candidate(kind="lipsync")`，并**同时**提供一条与 `video_correction` 同构的选用路径。

理由：口型同步是**可选用的视频候选**，与 `video_correction` 同类，而不是与图片同类。因此：

- 生成阶段产出 `Candidate(kind="lipsync")`，`entity_id` 为本镜 id，`data` 中保存 `key`、`asset_id`、`sha256`、`source_video_key`、`lipsync_fingerprint`、`report`、`engine`。
- 选用阶段在 `select_candidate` 中新增一个分支，与 `video_correction` 并列：

  ```python
  if c.kind == "lipsync":
      from app.services.lipsync import select_candidate as select_lipsync
      await select_lipsync(db, p, c, body.expected)
      await db.commit()
      return await project_out(db, p)
  ```

- `services/lipsync.py` 实现 `select_candidate`，内部复用 `video_correction.locked_scene` 的加锁取数模式，走 T3-B0 列出的八步，并在选用时校验 `lipsync_fingerprint`，不符返回 409 `STALE_CANDIDATE`。
- 选用后 `scene.video_key` 指向口型同步产物，`scene.creative.video` 的 trace 保留对原始视频的引用（`parent_video_key`），旧 trace 进 `video_takes`。**原始视频不得被覆盖或删除。**

前端配套改动：`src/features/Creative.tsx` 的 `select()` 函数当前判断 `c.kind.startsWith("shot_") || c.kind === "video_correction"` 来决定用场景版本号还是角色版本号做 `expected`。**必须把 `"lipsync"` 加进这个白名单**，否则 `expected` 会取到错误的版本号并触发 409。

> **`Candidate.kind` 是自由字符串**（`models/__init__.py` 的 `kind: Mapped[str]`，无枚举约束），所以 `"lipsync"` 可以直接使用，不需要迁移。

#### T3-B1b 三处必须同时注册，缺一不可

**这是本任务最容易漏的地方。** 新增一个操作在本仓库需要同时改三个地方，少任何一处都会静默失效——不是报错，是不工作。

**① 队列映射：`routers/creative.py` 的 `job_payload`（实测约 `:673-679`）**

当前实现是一个三段式表达式，**未匹配的操作会静默落到 `"script"`**：

```python
kind = (
    "image" if body.operation.endswith("image")
    else "tts" if body.operation in ("voice_preview", "voice_design", "voice_clone", "shot_audio", "role_audio")
    else "script"
)
```

必须为 `shot_lipsync` 增加分支，使其得到 `kind="lipsync"`。**注意不要让 `shot_lipsync` 落到 `"script"`**——那会让它被脚本 worker 捡走，用完全错误的语义执行。

**② Worker 进程：`backend/app/worker_config.py`（实测约 `:12-18`）**

队列在这里被显式枚举：

```python
for queue, concurrency in [("script", 2), ("image", 2), ("tts", 3), ("video", video_limit), ("compose", 1)]:
```

必须新增 `("lipsync", 1)`。

> **漏掉这一处的后果最隐蔽**：`jobs.py` 用 `queue="cineai." + row.kind` 投递，所以任务会被正确投到 `cineai.lipsync`，但**没有任何 worker 监听该队列**，任务永远停在 `queued`，界面上显示为「排队中」永不推进。不会报错，不会超时。启动脚本 `scripts/workers.py` 若也维护队列清单，同步检查。

**③ 执行分支：`services/creative.py` 的 `execute_candidate`（实测约 `:865`）**

操作分发是一条 `if/elif` 链：`plan/character/storyboard/voice_match` → `character_image/location_image/shot_image` → `voice_preview/voice_design/voice_clone` → `role_audio` → `shot_audio`。

**这条链没有终结 `else`。** 未匹配的操作不会抛错，而是带着空的 `result` 继续走到创建 `Candidate` 的代码，产出一条空候选。必须新增 `elif op == "shot_lipsync":` 分支。

**验收方式**：提交一个 `shot_lipsync` 任务后，确认 `Task.kind == "lipsync"`、队列为 `cineai.lipsync`、且有 worker 认领（`status` 从 `queued` 变为 `running`）。**只确认「任务创建成功」不算通过**——上面三处漏任何一处，任务创建都会成功，但永远不会被执行。

#### T3-B2 输入指纹

```python
lipsync_fingerprint = digest({
    "video_key": scene.video_key,
    "audio": (scene.creative or {}).get("audio") or {},
    "engine": report["engine"],
    "engine_version": report["engine_version"],
})
```

视频或音频任一变化，或更换引擎，指纹变化，旧候选失效。这与现有 `image_fingerprint`、`review_fingerprint` 的模式一致。

**音频侧直接使用已存的 `scene.creative.audio` 对象**——它已经包含 `fingerprint`、`segments`、`duration_ms`（由 `routers/creative.py` 的音频选用路径写入）。**本仓库没有名为 `audio_fingerprint()` 的函数**，不要去找或新建一个；直接把整个 `audio` 字典纳入摘要即可，这样音频内容、分句与时长任一变化都会被捕获。

参照 `services/creative.py` 的 `review_fingerprint(sc)`：它同样是把 `st.get("audio")` 整个放进 `digest(...)`。照这个写法做。

#### T3-B3 从视频 prompt 中剥离台词

这是口型质量的关键设计。当前 H3 收到的 prompt 包含台词文本与实测时间（`services/video.py:120-131`），模型被要求「按已标记台词与动作触发时间表演」。当口型同步启用时，台词文本会让模型自行生成嘴型，与后期对齐的口型冲突。

新增配置 `VIDEO_MOUTH_MOTION_ONLY`，默认跟随 `LIPSYNC_PROVIDER != "none"`。为真时：

- 从 H3 prompt 中移除台词文本，只保留动作与情绪描述。
- 保留 `trigger_line_id` 的动作触发时间，因为肢体动作仍需与音轨对齐。
- 在 prompt 中说明「本镜不生成台词语音，嘴部只做自然开合动作，语音由后期合成」。

**关于它与视频指纹的关系，这一点必须明确，否则会误伤已有数据：**

H3 的 prompt 由 `services/video.py` 的 `organized_prompt()` 在**提交时**组装，台词时间块（约 `:120-131` 的 `timing` 拼接）是它的一部分。而视频的失效指纹由 `source(scene, ratio)` 决定，其组成是 `first_frame_key`、`duration_sec`、`ratio`、`video_prompt`、`action`、`camera_move`、`generative_shot(shot)` 与 `audio_timing`——**`organized_prompt()` 的产物不在其中**。

结论：**只改 `organized_prompt()` 的拼装逻辑，不会使任何已有视频失效。** 这是期望行为，理由如下：

- 打开 `VIDEO_MOUTH_MOTION_ONLY` 后，已有视频不会被批量标记过期，用户不必重做全部镜头。
- 代价是：同一个镜头可能既有「含台词生成」的视频，又有「纯口型动作生成」的视频，两者在指纹上无法区分。这由 `video_takes` 的历史记录与口型候选的 `report` 承担可追溯性，不需要指纹承担。

**因此不要把 `VIDEO_MOUTH_MOTION_ONLY` 加进 `source()`。** 加了会导致切换配置时全库视频失效，代价远大于收益。这一条请在完成报告中明确记录你的选择。

#### T3-B4 诚实跳过

以下情况返回 `skipped` 状态与具体原因，**不得伪造成功，也不得静默回退到原始视频**：

- 本镜发言人超过一位（多人同框）。
- 视频中没有可对齐的正脸。
- 引擎返回失败或超时。
- 音轨时长与视频时长差异超过阈值。

**判定职责划分（必须按此实现，不要在本地引入人脸检测）：**

| 条件 | 由谁判定 |
| --- | --- |
| 发言人超过一位 | **本地判定**。读 `shot.lines` 与 `shot.narration` 的 `speaker_id` 去重计数，不需要模型。 |
| 没有可对齐的正脸 | **引擎判定**。引擎在 `X-Lipsync-Report` 中返回 `alignable=false` 与 `skip_reason`。本地**不得**为了这个判断引入 `cv2`、`insightface` 之类的人脸检测依赖 —— 硬约束禁止新增依赖。 |
| 引擎失败或超时 | 本地判定，来自 HTTP 状态码或子进程退出码。 |
| 音轨与视频时长差异超阈值 | **本地判定**，用现有的 `probe_video` 与音频 `duration_ms` 比较。 |

前两项属于「业务上做不了」，后两项属于「这次没做成」。界面上都要如实展示原因与建议，例如「本镜有 2 位发言人，建议拆分为两个单人镜头后重试」。

#### T3-B5 与视频依赖的关系（这是验证项，不是改造项）

`services/video_dependency.py` 的「下一镜首帧取上一镜真实最后 0.05 秒」逻辑，读取的是 `previous.video_key`（约 `:44`）。

由于 T3-B1 要求选用口型候选后把 `scene.video_key` 指向同步产物，**`video_dependency.py` 会自动使用同步后的视频，不需要任何改动。**

**因此这一条不要求你修改 `video_dependency.py`。** 你要做的是**验证并证明**它成立：

1. 让 A、B 两镜构成 `continuity_from` 依赖（B 的首帧来自 A 的尾帧）。
2. 对 A 镜选用一个口型同步候选，使 A 的 `video_key` 改变。
3. 重新触发 B 镜的首帧依赖抽取。
4. 断言抽取出的尾帧来自**同步后的** A 视频，而不是原始视频。

第 4 步的断言方式：比对抽帧所用的 `video_key` 与 A 镜当前的 `video_key`，两者必须相同。把这一步的实际输出写进完成报告。

> 如果你发现 `video_dependency.py` 读的不是 `video_key` 而是别的字段，那么**这一条才需要改造**。按实际代码判断，并在报告中说明偏差。不要因为文档这么写就去改一个本来就正确的文件。

#### T3-B 验收标准

以下第 1 至 4 条**对本地 HTTP 测试桩执行即可**，不需要真实引擎。测试桩按 T3-A2 定义的契约实现。

1. 对单人正脸镜头执行 `shot_lipsync`（引擎指向测试桩），产出一条 `kind="lipsync"` 的候选；选用后本镜 `video_key` 指向新产物，原视频进入 `video_takes`。
2. 修改该镜配音后，`lipsync_fingerprint` 变化，旧候选标记为过期，选用返回 409 `STALE_CANDIDATE`。
3. 对双人同框镜头执行，返回 `skipped` 与「本镜有 2 位发言人」的原因，且**不产生**候选。
4. `VIDEO_MOUTH_MOTION_ONLY=true` 时，抓取 H3 提交的 prompt，其中不含任何台词文本；同时确认已有视频**没有**被批量标记过期。
5. T3-B5 的依赖链验证：A 镜选用口型候选后，B 镜依赖抽取使用的 `video_key` 等于 A 镜当前的 `video_key`。

### T3-C 质量报告与可测量性

#### T3-C1 对齐报告

每个成功同步的镜头保存 `lipsync_report`，字段见 T3-A1。最低成本的必测项（不依赖人脸模型）：

- 输出时长与输入视频时长一致（容差 1 帧）。
- 帧率与分辨率不变。
- 音频轨与输入的音频指纹一致。

`alignment_score` 在人脸检测可用时填入，不可用时为 `null` 并说明原因。**不得填入伪造分数。**

#### T3-C2 导出前门禁

导出页在存在未同步镜头时给出提示，但**不阻断导出**。提示文案区分两种情况：

- 本部署未启用口型同步：不显示任何口型相关内容。
- 本部署已启用，但本集有 N 个镜头未同步：显示「本集有 N 个镜头未做口型同步」，并提供「前往处理」链接。

#### T3-C 验收标准

1. 成功同步的镜头在技术详情中能看到完整报告。
2. 报告中的时长、帧率、分辨率与实际产物一致。
3. 未启用口型同步的部署，导出页不出现任何口型相关文字。

### T3-D 前端界面

#### T3-D1 分镜详情口型区块

在分镜详情的「画面」标签页内，新增「口型同步」区块，位于视频候选列表之后。内容随状态变化：

- 未启用（`capabilities.lipsync` 为假）：整个区块不渲染。
- 无候选：显示「为这一镜生成口型同步」按钮，副标题说明预计耗时。
- 处理中：显示进度。
- 已跳过：显示跳过原因与建议动作。
- 有候选：显示候选与其报告摘要，提供「选用」与「查看技术详情」。

**候选列表的参照物是 `video_correction`，不是图片候选。** `src/features/creative/VideoCorrection.tsx` 已经实现了「列出一镜的可选用视频候选 + 选用」的完整交互，包括它如何接收 `candidates("video_correction", sc.id)` 与 `onSelect`。口型区块按同样的 props 形态接入：

```tsx
<LipsyncPanel
  key={`lipsync-${sc.id}-${sc.creative?.version}`}
  project={p}
  scene={sc}
  candidates={candidates("lipsync", sc.id)}
  busy={busy}
  reload={load}
  onSelect={select}
/>
```

`CandidateList` 是给图片与音频候选用的组件，它的字段假设（`c.data.request`、`reference`、`model` 等）与视频候选不匹配。**不要直接复用它来渲染口型候选**，除非你先确认它能正确显示视频类型的候选数据。

按钮文案必须诚实反映耗时，例如「生成口型（约 2 分钟）」，不得写成瞬时操作。

#### T3-D2 多发言人预检

在用户点击生成口型之前，若本镜的 `shot.lines` 与 `shot.narration` 涉及多位发言人，直接禁用按钮并显示原因与「拆分镜头」的建议链接。**不要让用户等两分钟后才被告知不支持。**

#### T3-D3 导出页口型状态

在导出页的逐镜列表中，为每个镜头增加一个口型状态标记：已同步、未同步、已跳过、不适用。鼠标悬停显示引擎与对齐分。

#### T3-D 验收标准

1. `LIPSYNC_PROVIDER=none` 时，分镜详情中不存在口型区块。
2. 双人同框镜头在点击前即被禁用，并显示拆分建议。
3. 导出页逐镜列表显示口型状态标记。

## 5. 跨任务契约

### 5.1 文案

任务一建立 `copy.ts` 后，任务二与任务三新增的每一条用户可见字符串都必须从该文件引用。任务二、任务三各自扩展 `copy.ts`，不新建第二个文案文件。

### 5.2 能力声明

所有可选能力通过 `GET /api/creative/projects/{id}` 的 `capabilities` 字段向界面声明。前端**不得**根据环境变量或硬编码判断能力是否存在。

任务一扩展 `capabilities`：`intro`、`watermark`、`bgmPresets`。
任务三扩展 `capabilities`：`lipsync`、`lipsyncEngine`、`lipsyncMaxSpeakers`。

### 5.3 版本与失效

任务二修改了失效传播的数据结构（T2-C1）。任务三的 `lipsync_fingerprint` 必须加入 `Scene.creative` 的失效计算链。任何新增的候选项都遵循同一模式：输入指纹、候选、选用、过期。

### 5.4 迁移

任务二引入迁移 `0004`。任务三若需要新增 `Scene.creative` 字段，通过 JSON 字段扩展即可，不需要迁移。若新增独立表，使用 `0005`。

每个迁移必须实现 `downgrade`，并经过「升级、降级、再升级」三轮验证。

### 5.5 测试

- 后端：`backend/tests/` 下新增 `test_episodes.py`（任务二）与 `test_lipsync.py`（任务三）。
- 前端：任务一建立 `npm run test:web` 后，任务二与任务三的新界面逻辑必须附带测试。

## 6. 风险与回滚

| 风险 | 任务 | 缓解 |
| --- | --- | --- |
| 分集迁移损坏现有 5 个项目的数据 | T2 | 迁移前对数据库做一次完整备份；`downgrade` 必须实测通过；迁移脚本在事务中执行 |
| 任务一的文案替换遗漏或误伤 | T1 | T1-B5 的 grep 检查必须为空；逐条核对表格，不接受抽样 |
| 口型同步耗时过长拖垮队列 | T3 | 独立队列与并发上限；默认 `none`；界面上诚实标注耗时 |
| 多人同框镜头无法同步，用户反复重试 | T3 | T3-D2 的前置预检必须在点击前拦截 |
| `IMAGE_MAX_REFERENCES` 提高后生图成本上升 | T1 | 在 `capabilities` 中暴露当前值；费用弹窗（T1-C4）列出将生成的清单 |
| 前端测试引入新依赖影响构建 | T1 | 只允许 vitest 与 testing-library；CI 中 `npm run build` 必须仍然通过 |

每个任务的回滚方式是 `git revert` 对应阶段的 commit。任务二的回滚额外需要执行迁移降级。

## 7. 明确不做

以下事项不在本轮范围内。列出它们是为了防止范围蔓延。

- 自动视觉一致性审核（人脸相似度、角色漂移检测）。本轮只做口型同步，不做外观质检。
- 分集的市场投放、发布、排期能力。
- 成片导出剪映草稿、FXML、EDL 等专业剪辑格式。
- 转场库与多轨时间线编辑。当前只有每镜首尾 0.2 秒淡化，本轮不改。
- 认证与授权。评估报告已标注该风险，但属于独立的部署议题。
- 供应商切换、新增视频或图像模型。
- 移动端完整适配。本轮只恢复窄屏提示，不做移动端布局重构。
- 修复评估报告 §2.4-P2-12 的 compose 超时风险。该问题需要引入断点续跑机制，工作量独立。

## 8. 总验收清单

三个任务全部完成后，以下检查必须全部通过。

**流程**

1. 从新建项目到导出，全流程无断点。五个阶段各有明确出口。
2. 阶段编号连续，页头计数与阶段标签永远一致。
3. 空态、错误态、加载态在五个阶段均有明确引导。

**语言**

4. 默认界面中不存在供应商名、模型 ID、命令行工具名、内部 ID、版本哈希、原始 JSON、原始英文报错。
5. 所有错误提示为中文，并给出恢复建议。

**能力**

6. 可以创建多集项目，第 N 集生成时带上前面各集的剧情记忆。
7. 角色与环境资产全剧共享，分镜按集独立。
8. 在启用 `LIPSYNC_PROVIDER` 的部署中，单人正脸镜头可生成口型同步候选；多人同框镜头在点击前被拦截并给出拆分建议。
9. 在未启用口型同步的部署中，界面上不存在任何口型相关入口。

**工程**

10. `npm run typecheck`、`npm run build`、`npm run test:web`、`backend/.venv/bin/python -m pytest backend/tests -q` 全部通过。
11. 迁移 `0004` 的升级、降级、再升级三轮验证通过，数据无损。
12. `workbench.css` 中 `!important` 与 `:has(` 的出现次数均为 0。

## Next steps

本文档定稿后，按顺序执行三份任务提示词。每份提示词是一份完整的工作单，可独立交给编码代理执行。

任务一完成后，先验收再进入任务二；任务二引入数据库迁移，必须先确认迁移在真实数据上无损，再进入任务三。任务三涉及额外算力，若短期内不具备 GPU 环境，可以只完成任务一的 T1-E3 与任务二的 T3-A 抽象层，把 `LIPSYNC_PROVIDER` 保持在 `none`，界面上不会出现任何未完成的能力入口。
