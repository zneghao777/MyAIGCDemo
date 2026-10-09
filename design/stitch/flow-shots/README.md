# 创作工作台全流程截图（供 Stitch 重设计布局）

这 29 张截图覆盖创作工作台从入口到导出的完整流程，拍摄时按"截到位"处理：
**凡是内部滚动的内容都展开到全高再截**，不会出现只截到可视区、下半截丢掉的情况。

## 拍摄参数

| 项 | 值 |
| --- | --- |
| 数据项目 | `给夜晚留一盏灯`（5 个分镜、5 个阶段全部已确认、角色与配音就绪） |
| 视口宽度 | 固定 1440px |
| 视口高度 | 真实态 1000px；整页与全展开态按内容高度动态设置，最高 5167px |
| 数据来源 | 后端真实数据（非 mock），页面显示「已连接工作台 · 已同步」 |

**为什么分镜阶段要特殊处理：** 分镜是固定高度的三栏工作台
（`height: calc(100dvh - 64px)` + `overflow: hidden`），用普通整页截图
或 fullPage 都只会得到 1000px 的可视区。它的右栏检视面板内容高达 **4647px**，
可视区只有 587px——也就是说有 **87% 的字段在默认视图里根本看不到**。
因此 `10-storyboard-full.png` 是把视口高度增加到 5167px，让三栏同时完整展开后
截取的；`13/13b/13c` 则是把右栏单独整块截下来，用于清点字段。

## 文件清单

### 流程主干

| 文件 | 尺寸 | 内容 |
| --- | --- | --- |
| `00-new-project.png` | 1440x1000 | 入口 · 新建项目 |
| `01-story-plan.png` | 1440x2060 | 阶段 01 故事方案（整页） |
| `02-characters-overview.png` | 1440x1119 | 阶段 02 角色总览 |
| `02a-character-persona.png` | 1440x1857 | 角色编辑 · 人物设定 |
| `02b-character-image.png` | 1440x3673 | 角色编辑 · 形象 |
| `02c-character-voice.png` | 1440x1857 | 角色编辑 · 声音 |
| `03-locations.png` | 1440x2604 | 阶段 03 环境素材（整页） |
| `05-generation-review.png` | 1440x1955 | 阶段 05 预览与导出（整页） |
| `06-export-page.png` | 1440x1743 | `/export` 导出页（流程终点） |
| `07-characters-route.png` | 1440x1119 | `/characters` 本片角色独立路由 |

### 阶段 04 分镜工作台

| 文件 | 尺寸 | 内容 |
| --- | --- | --- |
| `10-storyboard-full.png` | 1440x5167 | **三栏全展开，一切可见**（布局主参考） |
| `10f-storyboard-board-wide.png` | 1440x2400 | **最可读的一张**：5 个分镜卡 + 长右栏 |
| `10a-storyboard-viewport.png` | 1440x1000 | 真实视口下的默认样子 |
| `10d-viewport-image.png` | 1440x1000 | 右栏「画面」页签 |
| `10b-viewport-frames.png` | 1440x1000 | 右栏「起止画面」页签 |
| `10c-viewport-dialogue.png` | 1440x1000 | 右栏「台词与声音」页签 |
| `10e-viewport-outline-cast.png` | 1440x1000 | 左栏「角色」页签 |
| `10g-viewport-outline-collapsed.png` | 1440x1000 | 左栏收起态 |
| `10h-viewport-inspector-collapsed.png` | 1440x1000 | 右栏收起态 |

### 单面板整块截取（用于清点字段，不含外壳）

| 文件 | 尺寸 | 内容 |
| --- | --- | --- |
| `11-board-all-shots.png` | 709x4754 | 中栏画板，全部 5 个分镜卡 |
| `12-outline-story.png` | 210x4812 | 左栏「大纲」 |
| `12b-outline-cast.png` | 210x4812 | 左栏「角色」 |
| `13-inspector-image.png` | 300x4812 | 右栏「画面」全部字段 |
| `13b-inspector-frames.png` | 300x4812 | 右栏「起止画面」全部字段 |
| `13c-inspector-dialogue.png` | 300x4812 | 右栏「台词与声音」全部字段 |

### 关键弹窗

| 文件 | 尺寸 | 内容 |
| --- | --- | --- |
| `14-modal-video-generation.png` | 1440x1000 | 生成分镜视频 |
| `15-modal-cost-quote.png` | 1440x1000 | 生成范围与费用（付费前确认） |
| `16-modal-candidates.png` | 1440x1000 | 候选与历史 |
| `17-modal-story-compare.png` | 1440x1000 | 比较故事方案 |

## 建议的上传方式

Stitch 一次处理一张图效果最好。按用途分三类用：

**第一类 · 定布局**（一次一张，重点让它重排结构）
`10f-storyboard-board-wide.png` → `01-story-plan.png` →
`03-locations.png` → `02b-character-image.png` → `05-generation-review.png` →
`06-export-page.png`

**第二类 · 定字段清单**（配合第一类，让它不要漏字段）
`13-inspector-image.png`、`13b-inspector-frames.png`、`13c-inspector-dialogue.png`、
`11-board-all-shots.png`、`12-outline-story.png`、`12b-outline-cast.png`

**第三类 · 定状态与弹窗**
`10a/10b/10c/10d/10e/10g/10h`、`14`–`17`

配套的设计契约是 `../DESIGN-v2.md`，可以直接作为文字约束一起给 Stitch。
提示词可直接取用 `../SCREEN-PROMPTS.md` 里对应屏幕的段落，不用另写。

## 交给 Stitch 时建议明确提出的问题

这些都能在截图里直接看到，也是本次重设计真正要解决的：

**1. 可读性（最高优先级）。** 全站 `globals.css` 有 385 处字号声明，
其中 82% ≤12px、47% ≤10px，最小 6px。截图里大量 8–10px 文字。
要求：正文 14px 起，任何文字不得小于 11px。

**2. 分镜右栏是"藏在滚动条里的表单"。** 内容 4647px、可视 587px，
用户要滚 8 屏才能看完一个镜头的字段。建议重排为分组折叠或分区导航，
而不是一条长表单。

**3. 镜头编号重复。** 左栏场景列表渲染成 `01 01 · 再试一次`（截图可见），
生成阶段的缩略图是 `01 · 01 · 再试一次`，同一编号在卡片、面板头、标题、
时间轴共出现 4 次。

**4. ID 与哈希泄漏在主表单里**（不在折叠区）：
`绑定环境版本 → 已绑定历史环境版本 · 5ccd88a3`、
`出场角色与固定版本 → 许小禾 · e91d820f`。
这类内部标识应删除或收进「技术详情」。

**5. 状态无法区分。** 分镜卡上三个就绪点（视频/画面/声音）都是同样的绿勾样式，
「已过期待更新」与「未生成」缺少明显差异。

**6. 中英标签混排。** `STORY OVERVIEW`、`SCENE LIST`、`SCENE TEMPLATES`、
`INSPECTOR`、`TRANSFORM`、`CAM`、`ACTOR` 与中文标签同屏并列。

**7. 主色语义被稀释。** 导出页动作面板整块用金色渐变边框；
3D 导演台的人物默认色就是操作金 `#F5B942`。

## 复现方法

前提：开发服务器在 `127.0.0.1:3000`，且 `/` 页面显示「已连接工作台」并列出真实项目
（否则截到的是错误态）。

```bash
playwright-cli -s=cap open http://127.0.0.1:3000/
playwright-cli -s=cap resize 1440 1000
```

整页截取的关键是**按内容高度动态设置视口**，而不是用 `fullPage`——
因为底部动作条是 `position: fixed`，用 `fullPage` 会把它渲染到页面中段。

```js
const h = await page.evaluate(() => Math.max(
  document.documentElement.scrollHeight, document.body.scrollHeight));
await page.setViewportSize({ width: 1440, height: Math.min(h, 5000) });
await page.screenshot({ path: 'out.png' });
```

分镜阶段额外需要：先选中有分镜数据的项目，再点开「04 分镜创作」，
然后把视口高度设到 `.cs-inspector-body` 的 `scrollHeight + 520`。

**注意不要用 `main *` 的 `scrollHeight` 最大值来算高度。** `/export` 页曾因此
被算成 69752px（真实值 1743px），因为它内部有嵌套滚动容器。

## 与 `../current-ui/` 的关系

`../current-ui/` 是更早一轮的 8 张真实视口截图，包含 `flow-shots` 没有的
`/` 首页、`/director` 3D 导演台、`/queue` 生成任务。两者互补：

- 要看某屏在真实视口下的样子 → `current-ui/`
- 要看完整内容与全部字段 → `flow-shots/`
