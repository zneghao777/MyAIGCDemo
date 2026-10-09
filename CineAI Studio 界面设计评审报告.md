# CineAI Studio 界面设计评审报告

> 评审对象：`/Users/zenghao/MyAIGCDemo`（Next.js 16 + React 19 前端，`src/features/*`、`src/components/*`、`src/app/globals.css`、`src/features/creative/workbench.css`）
> 评审方式：**实际启动服务并逐页渲染核验**（`next dev` @127.0.0.1:3000，Chrome 1440×900 / DPR 1，fullPage 截图 12 张），辅以 DOM 几何测量（boundingBox / computedStyle）与对比度计算，而非仅凭源码推导。
> 截图存档：`design/ui-review/shots/`
> 风格基线：`DESIGN.md`（Stitch 原型 `CineAI Studio Web Workbench`）
> 说明：本次评审聚焦**视觉与界面设计**，不重复已有 `短剧生成流程与交互体验评估报告.md` 的流程/工程结论。

---

## 一、总体结论

| 维度 | 评分 | 一句话结论 |
| --- | --- | --- |
| 视觉语言与美观度 | **7.5 / 10** | 暗色电影感克制、专业，色彩角色分工清晰；但字号体系整体偏小，削弱了"专业工具"的质感。 |
| 布局与排版 | **6.0 / 10** | 三栏工作台布局成熟，但**卡片内容长度未受控**导致高度不齐、**空状态大面积留白**，是当前最明显的视觉瑕疵。 |
| 信息架构 | **6.5 / 10** | 顶栏与侧栏**双重导航**重复度高（4/5 项重复），占用 64px 却没提供新信息。 |
| 交互完整性 | **7.0 / 10** | 状态反馈、生成态、失败重试、弹窗焦点约束都到位；但输入框聚焦反馈弱、Toast 与底部操作栏空间冲突。 |
| 可访问性 | **5.5 / 10** | 焦点可见性与 reduced-motion 已做，但 **7–9px 字号 + 2.9–3.7:1 对比度** 不满足 WCAG AA。 |
| **综合** | **6.5 / 10** | **骨架和气质都对了，失分集中在"排版控制力"和"小字体系"两件事上——这两块的修复成本很低，收益却很高。** |

**一句话总结**：这不是一个"设计不行"的项目，恰恰相反，它的视觉基调、组件体系、暗色层次都在水准之上；问题几乎全部来自**内容长度失控 + 字号/对比度不足 + 空状态欠设计**这三类可量化的排版工程问题。

---

## 二、做得好的地方（请保持）

1. **色彩角色分工严谨且已 Token 化**
   `--gold #F5B942`（用户主动操作/选中/时间轴）· `--purple #A293EE`（AI 入口）· `--green #75C9A1`（完成）· `--red #EF8385`（失败）。
   `.btn.ai` 确实用了紫色描边（`globals.css:245-249`），`.btn.primary` 金色实心 + 深色字（对比度 **7.98:1**，优秀），与 `DESIGN.md` 完全一致，没有出现"AI 按钮被金色污染"的常见错误。

2. **全局交互基线干净**
   `globals.css:68-79` 对 `button/a/input/textarea/select` 统一挂了 150ms 过渡；`80-84` 提供 `:focus-visible` 金色 outline；`4971` 有 `prefers-reduced-motion` 兜底。这是很多同规模项目会漏掉的部分。

3. **三栏专业工作台的信息密度控制得当**
   创作工作台（`studio-data.png`）与 3D 导演台（`director-data.png`）在 1440 宽下**真实占满可用宽度**（实测 `.main-content` 1224px → 内容至 x≈1408），没有出现"内容挤在左边、右边一大片空"的常见问题。

4. **3D 导演台的完成度明显高于同类原型**
   视口 + 场景模板网格 + 对象属性（变换/位置 XYZ/朝向/缩放/动作）+ 多轨道时间轴（ACTOR/CAMERA 分层、金色播放头、菱形关键帧）四区协作，已经具备真实生产力工具的骨架。

5. **状态表达不依赖颜色单通道**——生成态、失败态均带文字标签，符合无障碍要求。

---

## 三、问题清单

### 🔴 P0-1 · 项目卡片高度不齐（最显眼的排版缺陷）

**现象**：首页同屏卡片高度实测 **428px vs 496px**，相差 68px，网格出现锯齿状错位。见 `shots/home.png`。

**根因（DOM 实测）**：不是封面或标题，而是 `.project-meta` 高度失控。

| 卡片 | `.project-meta` 实测高度 | 卡片总高 |
| --- | --- | --- |
| 古老茶馆… | 13px | 428 |
| 给夜晚留一盏灯 | 49px | 428 |
| 宿舍八卦风暴 | 26px | 428 |
| 罗峰 · 我为宇宙 | 52px | 496 |
| **大运撞上我** | **117px** | 496 |
| 雨停之前 | 49px | 496 |

`.project-meta` 渲染的是 `风格 · N个分镜 · 时长`，其中 `p.style` 会存入完整风格句（如"真实写实，自然光与手机屏幕光，手持镜头"），而 `.project-meta`（`globals.css:1337-1343`）是 `display:flex` 且**未给子项任何收缩/省略约束**，于是长文本撑爆一行 → 换行 → 高度从 13px 涨到 117px。

**修复**（`globals.css`，`.project-meta` 段后追加）：

```css
/* 约束元信息：风格串必须单行省略，避免撑高卡片 */
.project-meta > span {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.project-meta > span:first-child {   /* 风格是唯一可变长项，给它收缩权 */
  flex: 0 1 auto;
}
.project-meta > span:not(:first-child) { flex: 0 0 auto; }
.project-meta > i { flex: 0 0 auto; }

/* 兜底：同排等高，标题最多两行 */
.project-card { display: flex; flex-direction: column; }
.project-body { flex: 1; }
.project-title-row h3 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.project-progress { margin-top: auto; }   /* 进度条贴底，视觉对齐 */
```

---

### 🔴 P0-2 · 卡片标题与描述内容完全重复

**现象**：`shots/home.png` 首张卡片中，同一句"古老茶馆的掌柜，每晚都为过路的神仙泡一壶忘忧茶。"出现了**两次**——一次作 16px 标题（折两行），一次作 10px 描述（被省略号截断）。

**根因**：从首页 Hero 输入创意创建项目时，`name` 被直接赋为整句创意，`description` 也是同一句。DOM 实测确认：
- `h3.innerText` = `古老茶馆的掌柜，每晚都为过路的神仙泡一壶忘忧茶。`
- `.project-description.innerText` = 同一句

**连带影响**：顶栏项目切换器 `.project-switch select` 的 `max-width:120px`（`globals.css:731-739`）被这句长文本撑爆，`shots/home.png` 顶部下拉里只能看到尾部文字碎片（"…有"），用户完全无法辨识当前项目。

**修复（分两层）**：

1. **数据层（推荐，治本）**：创建项目时派生短标题，`name` 与 `description` 不要同源。
```
name        = 创意摘要（≤14 字，或让模型输出标题）
description = 完整创意
```

2. **UI 层（治标，立即生效）**：
```css
/* 下拉框给了固定宽度，就要保证内容和箭头不互相挤压 */
.project-switch select {
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.project-switch { max-width: 200px; }
/* 描述行允许两行，避免"截断到只剩半个字" */
.project-description {
  white-space: normal;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
```

---

### 🔴 P0-3 · 导出页「分辨率」选项在 6 列下文字崩坏

**现象**：`shots/export-data.png` 中，分辨率 6 个选项卡在 497px 宽的容器里均分，**每个仅约 44px 宽**：
- 「保留原片尺寸」被硬拆成 4 行：保留／原片／尺寸
- 480P 的说明"标准输出可快速查看"被拆成 4 行
- 红色「推荐」badge 压在标题上
- 4K / 720P 同样局促

这已经不是"紧凑"，而是**标签不可读**。

**修复**：从 6 列纵向卡改为 **3×2 横向 chip**（图标/分辨率值在左，说明在右），或改为单行等宽分段控件：

```css
/* 方案 A：3 列 2 行的横向卡片 */
.resolution-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}
.resolution-grid > * {
  flex-direction: row;
  text-align: left;
  padding: 10px 12px;
  min-height: 56px;
}
/* 说明文字单行省略，杜绝逐字换行 */
.resolution-grid small {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* 推荐角标改为内联 chip，不再绝对定位压字 */
.resolution-grid .recommend {
  position: static;
  margin-left: auto;
  order: -1;
}
```

若不想改结构，最低成本兜底是 `--line-clamp` + `word-break: keep-all`，但**强烈建议缩短选项文案**：`480P / 1080P / 2K / 4K`，把说明移到选中后的下方提示区。

---

### 🟠 P1-1 · 空状态"大面积留白"（影响第一印象）

三处最明显：

| 页面 | 现状 | 截图 |
| --- | --- | --- |
| 本片角色 | 0 角色时只有一行 `0 位角色 · 0 位待选形象 · 0 位待选声音`，下方 ~80% 区域全空 | `characters.png` |
| 3D 导演台 | 屏幕正中一个图标 + 「先为故事添加一个镜头」+ 一个按钮，四周 ~90% 空白 | `director.png` |
| 导出/预览 | 预览框为纯黑占位，底部 3 个无标签空缩略图 | `export.png` |

**问题本质**：空状态只承担了"告知"，没有承担"引导"。

**修复模板**（建议做成统一 `<Empty>` 增强版，当前 `components/ui.tsx:18-35` 的 `Empty` 只有 icon/title/desc/action 四件套）：

空状态应包含 4 个层次：
1. **状态标题** — 现在就有
2. **价值说明（为什么值得做）** — "选定角色形象与声音后，分镜可保持跨镜头一致性"
3. **主行动 + 次行动** — 主按钮实心金色，次按钮描边（当前角色页的"独立新建角色/从跨项目角色库复用"是纯文字链，权重不够）
4. **示例/模板入口** — 给 2–3 个可直接套用的预设，让用户不必从零开始

```css
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  min-height: 380px;        /* 给定最小高度，避免被压扁 */
  padding: 48px 24px;
  border: 1px dashed #2b2f3a;   /* 用虚框界定"待填充区域" */
  border-radius: 12px;
  text-align: center;
}
.empty .empty-actions { display: flex; gap: 10px; }   /* 主次按钮成组 */
```

---

### 🟠 P1-2 · 顶栏与侧栏双重导航（信息架构冗余）

`AppShell.tsx:36-42` 定义了一个 `nav` 数组，同一份数据渲染了**两次导航**：

| 位置 | 渲染内容 | 代码 |
| --- | --- | --- |
| 顶栏 `top-nav` | 项目工作台 / 创作工作台 / 3D 导演台 / 预览与导出（过滤掉 `/queue`） | `AppShell.tsx:160-172` |
| 侧栏 `sidebar nav` | 同样 5 项 + 本片角色 + 使用指南 | `AppShell.tsx:214-244` |

**重复率 4/5**，且这是**唯一导致顶栏存在的理由**——但顶栏已经占用了宝贵的 64px 垂直空间（对 3D 导演台这种"视口 + 时间轴"的界面，64px 相当可观）。

**修复建议**：把顶栏从"导航容器"改为"上下文与全局动作容器"：

```
┌──────────────────────────────────────────────────────────────┐
│ [Logo] │ 项目▾ 古老茶馆… │  ←面包屑/当前位置→  │  状态 · 新建 · 🔔 · 头像 │
└──────────────────────────────────────────────────────────────┘
```

- 移除 `top-nav`
- 新增面包屑：`创作工作台 / 01 故事方案`，让用户知道"我在流程的第几步"（这个信息目前只散落在页面内的小步骤条里）
- 收益：导航单一入口不产生歧义；顶栏 64px 开始承载真实信息；页面内可用垂直空间不变，但**视觉噪音下降**

---

### 🟠 P1-3 · Toast 与底部固定操作栏空间冲突

`.toast` 定位 `right:24px; bottom:24px; z-index:200`（`globals.css:589-604`）
`.cw-actionbar` 定位 `bottom:0; height:82px; z-index:20`（`workbench.css:93-109`）

两者在创作工作台类页面会**重叠**：Toast 会正好压在右下角的「确认故事，进入角色 →」主按钮上。由于 z-index 更高，Toast 遮挡的是**页面唯一的主行动点**。

**修复**：
```css
/* Toast 在存在底部操作栏时上移 */
.creative-workbench ~ .toast,
:has(.cw-actionbar) .toast { bottom: 106px; }
```
（若不想用 `:has`，可给 AppShell 加 body class 统一处理。）

---

### 🟠 P1-4 · 输入框聚焦反馈偏弱

`globals.css:85-99` 中 `input/textarea/select` 被设了 `outline: none`，聚焦时只有 `border-color: var(--gold-muted)`。而 `--gold-muted` 是 `gold 65% + muted` 的混色，在深色面板上对比增益有限，同时 `:focus-visible` 的金色 outline 规则（`80-84`）只覆盖 `button/a`，**不覆盖表单元素**。

**修复**：
```css
input:focus-visible,
textarea:focus-visible,
select:focus-visible {
  outline: 2px solid var(--gold);
  outline-offset: 2px;
  border-color: var(--gold);
}
```
或给聚焦态加一层 halo：
```css
input:focus, textarea:focus, select:focus {
  border-color: var(--gold);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--gold) 14%, transparent);
}
```

---

### 🟡 P2-1 · 字号体系整体偏小（影响可读性与专业感）

实测到的字号（`globals.css`）：

| 元素 | 字号 | 位置 |
| --- | --- | --- |
| `.brand small`（CREATIVE WORKSPACE） | **7px** | `696-702` |
| `.workspace-note > .tiny-label` | **7px** | `885-889` |
| `.sidebar nav small` | **8px** | `860-865` |
| `.project-meta` / `.project-card footer` | **9px** | `1337-1343` / `1371-1390` |
| `.home-kicker` / `.stat > div > span` | **9px** | `983-989` / `stats` |
| `.duration-widget small` / `.hero-bottom` | 9–10px | `916-921` |

**7–9px 的字号在 1440 分辨率下几乎不可读**，尤其配合下面 P2-2 的低对比度。项目定位是"专业剪辑工作台"，用户会长时间盯屏，小字会直接变成疲劳源。

**建议的字号阶梯**（保持现有视觉层级关系，整体抬升）：

```css
:root {
  --fs-overline: 11px;   /* 原 7–8px 的微型标签，如 CREATIVE WORKSPACE */
  --fs-caption:  12px;   /* 原 9–10px，如卡片 meta / footer / kicker */
  --fs-body:     14px;   /* 原 12–13px */
  --fs-title:    16px;
  --fs-h3:       20px;
  --fs-h2:       24px;
  --fs-h1:       32px;
  --fs-display:  44px;   /* 首页 hero h1 */
}
```

层级关系不变，但最底一档从 7px 抬到 11px——**这是本次评审中性价比最高的一条改动**。

---

### 🟡 P2-2 · 部分文字对比度不满足 WCAG AA

实测（相对亮度法计算）：

| 前景 / 背景 | 计算对比度 | 判定 |
| --- | --- | --- |
| `--faint #5c6370` on `--surface #16181f` | **3.03 : 1** | ✗ 需 4.5:1 |
| `#687180` on `#181a21`（卡片 footer） | **3.68 : 1** | ✗ |
| `#606b7a` on `#111217`（侧栏徽标） | **3.14 : 1** | ✗ |
| `--muted #9298a5` on `#16181f` | 6.33 : 1 | ✓ |
| `.btn.primary` 文字 `#33240e` on `#F5B942` | 7.98 : 1 | ✓ 优秀 |

**修复**：
```css
:root {
  --faint: #9aa1ae;   /* 3.03 → 7.05 : 1 ✓ */
}
.project-card footer { color: #98a0af; }        /* 3.68 → ~6.4 : 1 */
.sidebar nav small   { color: #8b93a2; }        /* 3.14 → ~5.6 : 1 */
```
注意这三处恰好都是 P2-1 里的小字——**字号与对比度同时不达标，是叠加伤害**。

---

### 🟡 P2-3 · 无封面项目的首字占位风格断裂

`shots/home.png` 中，"古""宿""大"三个无封面项目在 16:9 封面区里渲染了一个**巨大的单字**（约 90px），与相邻有实拍图的卡片（`给夜晚留一盏灯`、`雨停之前`）并排时，视觉重量完全失衡——大片纯黑 + 一个孤立汉字，看起来像加载失败的占位。

**修复**：给无封面卡片一套确定性视觉，让"缺图"变成"风格"：

```css
.project-cover-placeholder {
  display: grid;
  place-items: center;
  font-size: 40px;                 /* 降下来，不要 90px */
  font-weight: 700;
  color: color-mix(in srgb, var(--gold) 70%, transparent);
  background:
    radial-gradient(circle at 30% 25%, color-mix(in srgb, var(--gold) 9%, transparent), transparent 60%),
    repeating-linear-gradient(115deg, #1a1d25 0 12px, #171a21 12px 24px),
    #171a21;                        /* 斜向纹理，暗示"未开拍" */
  border-bottom: 1px solid color-mix(in srgb, var(--gold) 12%, transparent);
}
```
若要更精致，可按项目 id 做哈希取色，让不同项目自动获得不同色相的暗调渐变。

---

### 🟡 P2-4 · 零散细节

| # | 问题 | 位置 | 建议 |
| --- | --- | --- | --- |
| 1 | 队列页表格缩略图列过窄，占位符竖排显示成"分""图" | `queue.png` | 缩略图列设 `min-width: 56px`，占位显示图标而非文字 |
| 2 | 3D 导演台视口下方操作提示（"拖动旋转轮 滚轮缩放…"）字号约 9px、对比度低 | `director-data.png` | 并入 P2-1/P2-2 统一抬升 |
| 3 | 导出页底部 3 个空缩略图无标签、无说明 | `export.png` | 加 `figcaption`（如"首帧 / 尾帧 / 封面"）或删除未就绪的占位 |
| 4 | 「分镜准备进度 0%」与状态徽章「已导出」语义矛盾 | `home.png` 第 6 张卡 | 逻辑层：已导出应展示 100%；这是数据派生 bug |
| 5 | 控制台报 `An empty string ("") was passed to src`，`<img src="">` 触发多余请求 | 运行时 | `ProjectCover` / 任务缩略图在无图时应渲染占位元素而非空 `src` |

---

## 四、Design Tokens 建议（可直接替换 `:root`）

```css
:root {
  /* ---------- 色彩：保持不变 + 修对比度 ---------- */
  --bg: #0e0f13;
  --surface: #16181f;
  --raised: #1e2129;
  --line: #2a2e38;
  --text: #f2f3f5;
  --muted: #9298a5;          /* 6.33:1 ✓ */
  --faint: #9aa1ae;          /* 原 #5c6370 → 3.03:1 ✗，现 7.05:1 ✓ */

  --gold: #F5B942;           /* 用户主动操作 */
  --purple: #a293ee;         /* AI 入口 */
  --green: #75c9a1;          /* 完成 */
  --red: #ef8385;            /* 失败 */

  /* ---------- 字号阶梯：整体抬升，层级不变 ---------- */
  --fs-overline: 11px;       /* 原 7–8px */
  --fs-caption:  12px;       /* 原 9–10px */
  --fs-body:     14px;
  --fs-title:    16px;
  --fs-h3:       20px;
  --fs-h2:       24px;
  --fs-h1:       32px;
  --fs-display:  44px;

  /* ---------- 间距：已有 4px 基数为底，补齐 8 点节奏 ---------- */
  --space-1: 4px;  --space-2: 8px;  --space-3: 12px; --space-4: 16px;
  --space-5: 20px; --space-6: 24px; --space-8: 32px; --space-12: 48px;

  /* ---------- 圆角：与 DESIGN.md 对齐 ---------- */
  --radius-btn: 7px;
  --radius-card: 9px;
  --radius-modal: 13px;

  /* ---------- 层级 ---------- */
  --z-sidebar: 45;
  --z-header: 60;
  --z-actionbar: 20;
  --z-toast: 200;
}
```

---

## 五、落地优先级路线图

| 优先级 | 改动 | 影响面 | 成本 |
| --- | --- | --- | --- |
| **P0** | 卡片 `.project-meta` 收缩约束 + 同排等高（P0-1） | 首页 | 约 10 行 CSS |
| **P0** | 项目 `name`/`description` 去重 + 下拉截断（P0-2） | 首页 / 顶栏 / 数据层 | 1 处数据逻辑 + 5 行 CSS |
| **P0** | 分辨率选项改 3×2 或缩短文案（P0-3） | 导出页 | 局部重构 |
| **P1** | 字号阶梯抬升（P2-1 与 P2-2 一并做） | 全局 | Token 替换 |
| **P1** | 空状态四层结构（P1-1） | 角色页 / 导演台 / 导出页 | 组件增强 |
| **P1** | 顶栏去导航、改面包屑（P1-2） | 全局 | 中 |
| **P1** | Toast 避让底部操作栏 + 表单聚焦反馈（P1-3/1-4） | 全局 | 约 12 行 CSS |
| **P2** | 无封面占位视觉、队列缩略图列、零散文案 | 局部 | 低 |

---

## 六、复审结论

**"是否合理"** — 布局骨架、组件体系、色彩角色均合理，符合 `DESIGN.md` 定义，没有出现结构性问题。
**"是否美观"** — 美观度中上，暗色电影质感成立；扣分点集中在**内容长度失控导致的排版错位**，属于"设计稿没考虑极端数据"而非审美问题。
**"交互是否到位"** — 主要交互闭环完整（含生成态、失败重试、弹窗焦点约束、快捷键提示）；弱项是**表单聚焦反馈**与**Toast 空间冲突**两处细节。
**"排版是否合理"** — 三栏工作台与导出页的双列排版合理；首页卡片网格因 `.project-meta` 缺约束而失稳，是当前最该修的一处。

**建议的下一步**：先做 P0 三条（总计约半天），页面观感会有立竿见影的提升；随后做字号与对比度统一（一次 Token 替换），这两步完成后页面才真正"配得上"它已经具备的工程深度。

---

*UI Designer · 界面设计评审*
*评审日期：2026-10-02 · 基于 12 张实机截图与 DOM 几何测量*
