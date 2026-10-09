# 任务二提示词：分集结构

将以下全文复制给编码代理执行。

---

## 角色与目标

你是本仓库的高级后端与全栈工程师。本次任务把「一个项目等于一条短片」扩展为「一个项目等于一部多集短剧」。

仓库根目录：`/Users/zenghao/MyAIGCDemo`。

这是本项目从短片工具变成短剧平台的分水岭。评估报告的对标结论是：「分集」是开源界共识的第一级结构（LocalMiniDrama 的 8 步表把「多集剧本 / 分集管理」放在第 1–2 步，ArcReel 有独立的「分集与结构化剧本」阶段，drama-skills 有专门的 episode map），而本仓库全仓库 `episode|分集` 零命中。

**本次任务会修改数据库结构，并且要对库中全部真实项目做数据搬移。这是本轮三个任务中风险最高的一次。** 项目数量以你在第三步记录的基线为准，不要在代码或验收标准里写死。严格执行本文档的备份与验证要求。

## 前置条件

**任务一必须已经完成。** 具体确认：

- `src/features/creative/copy.ts` 存在。
- `src/features/creative/TechnicalDetails.tsx` 存在。
- `npm run test:web` 可运行。
- `workflowReadiness` 已包含 `plan`、`cast`、`locations`、`shots`、`export` 五个布尔字段。

缺少任何一项，停止并报告。任务二必须复用任务一的文案字典与能力声明机制，不得另起一套。

## 第一步：必读材料

1. `design/specs/优化与能力扩展Spec-CineAI-Studio.md` —— **§3 是你的完整工作范围**。**先读 §T2-0「契约变更授权」**，那一节列出了本任务被允许的全部响应结构变更；然后在 §3 内按 T2-A → T2-D 的顺序读。§5 是跨任务契约，§6 是风险与回滚，§7 是明确不做的事。
2. `design/reviews/2026-10-01-flow-ux-audit/短剧生成流程与交互体验评估报告.md` —— §2.4-P0-1 说明为什么分集是最高优先级的缺失能力。
3. `backend/app/models/__init__.py` —— 现有 10 张表。注意 `Scene.__table_args__` 的 `uq_scene_order`。
4. `backend/app/schemas/creative.py` —— Plan / Location / Shot 是 Pydantic 契约而非表，理解这一点再动手。
5. `backend/app/api/routers/creative.py` —— 现有 API 面。注意 `project()` 的项目行锁模式。
6. `backend/app/services/video_correction.py` —— 看 `locked_scene`（约 `:99-105`）。这是本仓库既有的「项目行锁 + 重读场景」实现，任务一 T1-E5-a 也复用它。你的集级写路径应当沿用同一模式。
7. `backend/alembic/versions/` —— 现有 3 个迁移，你写的是 `0004`。

> **行号是评估时的快照。** 任务一刚落地的改动会让行号整体漂移。以实际代码为准，不要为了匹配文档行号而改动无关代码。文档中给出的函数名与符号名比行号可靠。

## 第二步：数据安全准备

**在写任何代码之前完成这一步。**

```bash
cd /Users/zenghao/MyAIGCDemo

# 1. 记录迁移前的基线，写进报告
backend/.venv/bin/python - <<'PY'
import asyncio, json
from app.core.db import SessionLocal
from app.models import Project, Scene, Character, Candidate, Task
from sqlalchemy import select, func

async def main():
    async with SessionLocal() as db:
        for M, name in [(Project,"Project"),(Scene,"Scene"),(Character,"Character"),
                        (Candidate,"Candidate"),(Task,"Task")]:
            n = (await db.execute(select(func.count()).select_from(M))).scalar()
            print(f"{name}: {n}")
        rows = (await db.execute(select(Project.id, Project.name))).all()
        print(json.dumps(rows, ensure_ascii=False))
asyncio.run(main())
PY

# 2. 完整备份数据库
pg_dump cineai > /tmp/cineai-before-0004.sql
wc -l /tmp/cineai-before-0004.sql
```

这两条命令的输出必须粘贴进完成报告。**没有备份就不要执行迁移。** 项目数量以这里记录的结果为准，不要在代码或验收标准里写死数字。

## 第三步：按阶段施工

Spec §3 把任务二分为四个阶段：`T2-A` 数据模型与迁移、`T2-B` 后端接口、`T2-C` 生成与失效传播、`T2-D` 前端分集界面。

严格按 A → B → C → D 顺序执行。每个阶段单独提交，message 格式 `T2-A: <描述>`。

### T2-A 数据模型与迁移（最高风险阶段）

四件事：新增 `Episode` 表；把 `Project.creative` 拆成项目级与集级；`Scene` 新增 `episode_id` 并把唯一约束从 `(project_id, order_index)` 换成 `(episode_id, order_index)`；写迁移 `0004`。

**拆分规则必须严格遵守 Spec §T2-A2：**

- 留在 `Project.creative`（全剧共享）：`locations`、`narrator`、`cast_confirmed`、`export_confirmation`。
- 搬到 `Episode.creative`（每集独立）：`plan`、`plan_draft`、`confirmed_plan`、`plan_confirmed`、`shots_confirmed`、`preview_confirmation`。

> `cast_confirmed` 留在项目级是刻意的。角色定妆跨集共享，正是分集结构要保护的一致性资产。**不要把它搬到集级。**

`0004` 的 `upgrade` 必须按 Spec §T2-A4 的六步顺序执行。`downgrade` 必须实现，且必须在文件头注释中写明「降级会丢弃第 2 集及以后的全部数据」。

> **不要用 `input()` 做交互式确认。** 第 95 行那三条验收命令是连续非交互执行的，任何等待标准输入的代码都会把验收挂死。

### T2-A3 场景创建点（最容易漏的一步）

把 `scene.episode_id` 改为 `NOT NULL` 之后，**全部 5 处场景创建点**都必须设置该字段，否则运行期抛 IntegrityError。Spec §T2-A3 给了逐处清单，简表如下：

| # | 位置 | 额外注意 |
| --- | --- | --- |
| 1 | `tasks/execute.py` 约 `:102` | `order_index` 改为集内序号 |
| 2 | `routers/creative.py` 约 `:849` | 创作流程路径，`episode_id` 由集级生成参数提供 |
| 3 | `routers/resources.py` 约 `:67` | 旧版端点，默认归属第 1 集 |
| 4 | `routers/resources.py` 约 `:260` | `len(scenes)` 是项目级计数，**必须改为集内计数** |
| 5 | `routers/resources.py` 约 `:334` | 复制场景，同样要改计数口径 |

第 4、5 处若不改计数口径，会产生跨集重复的 `order_index` 并撞唯一约束。第 3、4、5 处是旧版端点，**保持既有契约**，只补默认归属，不要给它们新增剧集参数。

**迁移完成后立即验证：**

```bash
backend/.venv/bin/python -m alembic upgrade head
backend/.venv/bin/python -m alembic downgrade -1
backend/.venv/bin/python -m alembic upgrade head
```

三轮必须全部成功。然后再跑一遍第二步的基线查询，**五个实体的数量必须与迁移前完全相同**，且每个项目恰好有一条集记录。任何数字不符，停止并报告。

### T2-A5 workflowReadiness 增加集级维度

这一步容易漏，而且**最容易做错方向**。

任务一 T1-A3 落地的 `workflowReadiness` 是一个**扁平**对象，其中的 `shots`、`preview_confirmed` 被 **3 条既有测试断言**引用：

- `backend/tests/test_creative.py:408`
- `backend/tests/test_creative_assets.py:248,257`

硬约束第 2 条禁止改既有断言。**所以不要把它重构成 `{project, episodes}` 那样的嵌套结构**——那会让这 3 条断言失效，而你又不被允许改它们，任务会卡在自相矛盾里。

正确做法是**只增不改**：保留全部既有键（语义改为作用于 `activeEpisodeId` 那一集），新增 `episodes` 数组，并在响应顶层新增 `activeEpisodeId`。Spec §T2-A5 给了完整方案与 `materials_confirmed` 这个混合键的处理说明。

`stageStates` 同样只增不改，并与 `workflowReadiness` 共用同一数据来源。

> 这是**新增**，不是结构修改。注意 T2-0 授权表第 5 项的措辞已按此调整。

### T2-B 后端接口

五个集管理端点（Spec §T2-B1）；`confirm/plan` 与 `confirm/shots` 改为集级并保留旧路径一个版本作为别名；生成端点区分作用域。

**最容易出错的是 `T2-B4 剧情记忆`。** 这是分集结构最关键的生成侧改动，不是可选优化。生成第 N 集时，prompt 里必须带上前面各集的上下文：全季主线、各集 `synopsis`、上一集结尾镜头、全剧角色表。注入长度上限由 `EPISODE_MEMORY_MAX_CHARS` 控制，默认 4000，超出时保留最近三集与第 1 集。

验证方式是把实际发送给模型的 prompt 抓出来看，不要只断言代码里有拼接逻辑。

### T2-C 生成与失效传播

三件事：`dependency_stamp` 从单字段改为 `{"characters": {...}, "locations": {...}}` 集合结构；`init_project` 与 `PATCH /narrator` 都写入 `tts_model`；新增集不得使已有集失效。

`dependency_stamp` 的结构变更会级联影响 `review_fingerprint`、`preview_fingerprint`、`render_fingerprint` 三个指纹函数。三个都要同步修改，并迁移旧格式。

> 这是对 `scene.creative` 结构的**修改**，已在 Spec §T2-0 授权表第 2 项列明。除 `dependency_stamp` 外，`scene.creative` 的其它既有键一律不动。

### T2-D 前端分集界面

集选择器；阶段作用域可视化（项目级阶段标注「全剧共享」）；分集管理页；导出作用域选择。

**`T2-D2` 不是装饰性改动。** 五个阶段中 `01 故事方案` 与 `04 分镜创作` 是集级的，`02 角色形象与声音` 与 `03 环境素材` 是项目级的。不在界面上区分，用户会误以为换集后角色也要重做。必须用视觉差异明确表达。

## 硬约束

1. **不删除数据，但允许改结构。** 不删除列、不删除行。删除唯一约束、把列从可空改为非空、建新表与索引，都是本任务必需的结构操作，在授权范围内。`downgrade` 需要还原的是**表结构与 JSON 键的形状**，不是第 2 集及以后的内容——那些在降级时会被删除，这一点必须写进降级脚本的文件头注释。
2. **不改既有测试的断言。** 失效的断言按任务一的规则单独列出。
3. **保持现有 API 契约，除 Spec §T2-0 的授权清单。** 任务二的本质是拆分项目级与集级状态，必然改变若干既有响应结构。`design/specs/优化与能力扩展Spec-CineAI-Studio.md` 的 **`§T2-0 契约变更授权`** 一次性列出了全部 5 项授权变更（含删除 `project.creative` 的 6 个键、修改 `scene.creative.dependency_stamp` 结构、新增 `workflowReadiness.episodes` 与 `activeEpisodeId`）、授权的新增端点、授权的旧端点行为变更、授权的新错误码与配置。**该清单之外的任何既有字段增删或结构改动，都命中停止条件。** 旧路径至少保留一个版本作为别名。

   > 注意第 5 项是**新增**而非重构。`workflowReadiness` 的既有键被 3 条测试断言引用，改成嵌套结构会让它们失效且你无权修改——详见 T2-A5。
4. **所有新文案进 `copy.ts`。** 不新建第二个文案文件。
5. **能力通过 `capabilities` 声明。** 前端不得根据环境变量或硬编码判断能力。
6. **不动 Spec §7 的范围内事项。** 特别是：不做投放排期、不做剪辑格式导出、不做转场库、不做认证授权。
7. **不新增依赖**，除任务一已授权的 `vitest` 与 `@testing-library/react`。
8. **不要顺手重构无关代码。**
9. **新建或修改客户端组件时，`"use client"` 必须是文件的首条语句。** 任何 `import` 出现在它前面都会让该指令失效，模块被当成服务端组件处理，Turbopack 直接报 `The "use client" directive must be placed before other expressions`，构建失败且页面返回 500。**本仓库已经因为这一条栽过一次**（`src/lib/remote-store.ts`，T1-B 阶段）。添加 import 时把它们放在指令之后，不要放在文件顶部之前。每次提交前跑 `npm run build` 确认。

## 完成定义

**命令级验证，全部要有实际输出：**

```bash
npm run typecheck
npm run build
npm run test:web
backend/.venv/bin/python -m pytest backend/tests -q
backend/.venv/bin/python -m pytest backend/tests/test_episodes.py -q   # 你新增的
```

**迁移验证：**

```bash
# 升级 → 降级 → 再升级，三轮全过
backend/.venv/bin/python -m alembic upgrade head
backend/.venv/bin/python -m alembic downgrade -1
backend/.venv/bin/python -m alembic upgrade head
```

**数据完整性验证（必须与迁移前基线逐项对比）：**

五个实体的行数不变；每个项目恰好一条集记录；每个场景的 `episode_id` 非空；每个项目的第 1 集 `creative.plan` 与原 `Project.creative.plan` 深度相等；`project.creative` 中不再包含那 6 个已搬移的键。

**workflowReadiness 验证（T2-A5，容易做错方向）：**

```bash
curl -s http://127.0.0.1:8001/api/creative/projects/<id> | python3 -c \
  "import json,sys; d=json.load(sys.stdin); w=d['workflowReadiness']; \
   print('has all legacy keys:', all(k in w for k in ['plan','cast','locations','shots','export','structure_ready','preview_confirmed','video_accepted'])); \
   print('episodes:', w.get('episodes')); print('activeEpisodeId:', d.get('activeEpisodeId'))"
```

三项必须同时成立：

1. `has all legacy keys: True` —— **既有 11 个键一个都不能少、类型不能变**。
2. `episodes` 存在，每个元素含 `id`、`orderIndex`、`plan`、`shots`、`preview`。
3. 顶层存在 `activeEpisodeId`。

**另外必须确认没有破坏这 3 条既有断言**（它们不在你的测试文件里，但会被 `pytest backend/tests -q` 跑到）：

```bash
backend/.venv/bin/python -m pytest backend/tests/test_creative.py backend/tests/test_creative_assets.py -q
```

切换集后，页头计数与阶段标签随之变化（它们读的是当前集），项目级的 `cast`/`locations` 状态不变。

**行为级验证，每条附截图或命令输出：**

1. `GET /api/creative/projects/{id}/episodes` 对每一个既有项目各返回一条集记录。
2. 新建一集，在其下生成分镜，第 1 集的场景不受影响。
3. 抓取第 2 集 `plan` 生成时实际发送的 prompt，其中包含第 1 集的 `synopsis`。
4. 旧路径 `POST /api/creative/projects/{id}/confirm/plan` 仍可用，作用在第 1 集，响应头含 `Deprecation`。
5. 多集项目切换集后，分镜列表变化，角色与环境阶段状态不变。
6. 项目级阶段标签下显示「全剧共享」。
7. 导出页可选「本集」与「全季合辑」，全季产物时长等于各集之和。
8. 修改 `MINIMAX_TTS_MODEL` 后，旁白与人物对白**同时**被标记需要更新。

截图存放于 `design/reviews/2026-10-01-flow-ux-audit/shots/after-t2/`。

## 完成报告格式

```
## 执行摘要
## 数据安全准备
（基线查询输出、pg_dump 结果）
## 迁移验证
（三轮 alembic 输出）
## 数据完整性对比
（迁移前后逐项数字对比表）
## 阶段完成情况
### T2-A … ### T2-D
（每阶段：状态、改动文件、commit、验收输出、偏差）
## 命令级验证结果
## 行为级验证结果
## 发现但未处理
## 需要人工决策的事项
```

## 停止并报告的条件

出现以下任一情况，**立即停止**，保留现场，输出当前进度：

1. **迁移前后任何一个实体的行数不一致。**
2. `downgrade` 执行失败，或降级后无法再次 `upgrade`。
3. 迁移过程中出现异常，事务未按预期回滚。
4. 任务一的前置条件不满足（`copy.ts`、`TechnicalDetails.tsx`、`test:web`、`workflowReadiness` 五字段）。
5. 你发现某个既有项目的 `Project.creative` 结构与 Spec 描述不符到无法确定搬移规则的程度（例如某个项目缺少 `plan` 键）。
6. 连续三次尝试仍无法通过某个阶段的验收。
7. 需要新增除已授权依赖之外的任何依赖。
8. 你需要修改一个**未列入 Spec §T2-0 授权清单**的既有 API 字段或 JSON 键结构。

**以下情况不构成停止条件，按本文档执行即可：**

- 「保持现有 API 契约」与「拆分项目级/集级状态」看起来冲突。Spec §T2-0 已经列出全部授权变更，按那张表执行。
- `downgrade` 会丢弃第 2 集以后的数据。这是降级的固有代价，不是矛盾——它还原的是表结构与 JSON 键的形状，已写入降级脚本注释要求。
- Spec 的行号与实际代码有偏移。任务一刚落地，偏移是预期的，以实际代码为准并在报告中记录。
- 某个既有项目的场景数或候选数与你预期不同。以第二步记录的基线为准，不看文档里的示例数字。
- 实现方式需要你自行设计（例如全季合辑的 compose 编排）。这是设计自由度，不是冲突。

**数据安全高于任务完成度。** 如果迁移有疑问，宁可停下报告，也不要带着不确定继续。报告「迁移未执行，原因是 X」远好于「迁移已执行，数据可能有损」。

但「数据安全」不是停止一切的借口——契约授权、行号偏移、实现自由度这些都不涉及数据安全，属于可自行裁决的范围。
