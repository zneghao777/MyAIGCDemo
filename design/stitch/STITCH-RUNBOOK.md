# Stitch 重设计操作手册

本手册说明如何在 Google Stitch 网页版里，用 `DESIGN-v2.md` 与
`SCREEN-PROMPTS.md` 重做 CineAI Studio 的前端，并把结果落回本仓库。

配套文件：

- `DESIGN-v2.md`：设计契约，也是要上传给 Stitch 生成设计系统的输入文件。
- `SCREEN-PROMPTS.md`：12 条可直接粘贴的屏幕提示词与迭代提示词。
- `current-ui/`：**当前代码**实拍的 8 张界面截图，用于在 Stitch 里做图片参考。

## 一、开始前必须知道的五件事

**1. Stitch 不会改你的代码。** 它输出的是单文件静态 HTML，内部用
`https://cdn.tailwindcss.com` 的 CDN Tailwind、一套 Material 3 命名的颜色令牌
（`surface`、`on-surface`、`primary-container` 等）、Google Fonts 的 Inter，
以及 Material Symbols 图标字体。这是一个设计稿，不是可以合并的代码。
落地见第六章。

**2. 通过 MCP 只能文生界面，不能传图。** Stitch 的 MCP 端点共 15 个工具，
全部是文本驱动（`generate_screen_from_text`、`edit_screens`、`generate_variants`），
没有任何图片上传工具。**图片转 UI 只能在网页版手动上传**，这正是你要自己跑
网页版的原因。

**3. 你已有的审计截图是过期的，不要拿去当参考图。** `design/reviews/2026-10-01-flow-ux-audit/shots/`
拍于 2026-10-01，而代码在 10-02 之后有多次改动。实测差异：

| 旧截图 | 当前代码 |
| --- | --- |
| 阶段导航为 `01 / 02 / 环境素材 / 03 / 04`，环境素材无编号 | 已是 `01`–`05` 全部编号（`StageNavigation.tsx:9-13`） |
| 进度显示 `3 / 3 阶段已确认` | 已是 `5 / 5 阶段已确认`（`Creative.tsx:299`） |
| 分镜检视面板 5 个生成按钮平铺 | 已按「画面 / 声音」分组（`Creative.tsx:661-665`） |
| 弹窗标题 `MiniMax H3 · 并发分镜视频` | 已是「生成分镜视频」（`VideoGeneration.tsx:73`） |
| 暖金混色 `--cw-gold: #e2bd75` | 已统一为 `var(--gold)`（`globals.css:13`） |

`current-ui/` 里的截图已按当前代码重新实拍，请用它做参考图。若界面又有改动，
按第七章重新拍。

**4. 先定设计系统，再生成屏幕。** `generate_screen_from_text` 的 `designSystem`
参数说明写着"should always be configured for design consistency"。不先播种，
12 张屏会互相不像。

**5. 一次只做一屏。** 在一个提示词里要求多个页面，产出质量会明显下降。

## 二、当前界面截图

`current-ui/` 目录内容（1440×1000，实拍于运行中的开发服务器）：

| 文件 | 路由 | 说明 |
| --- | --- | --- |
| `01-home.png` | `/` | 项目工作台首页，含 6 个真实项目 |
| `02-new.png` | `/new` | 新建项目，远程模式形态 |
| `03-studio-plan.png` | `/studio` | 工作台，故事方案阶段 |
| `03b-studio-storyboard.png` | `/studio` | 工作台，分镜创作阶段，5 个镜头有画面 |
| `04-director.png` | `/director` | 3D 导演台 |
| `05-queue.png` | `/queue` | 生成任务队列 |
| `06-export.png` | `/export` | 预览与导出 |
| `07-characters.png` | `/characters` | 本片角色 |

## 三、步骤

### 步骤 1 · 决定在哪个项目里做

不要直接在 v1 项目 `15607036117323851681`（CineAI Studio Web Workbench）上改，
那样会丢掉 v1 作为对照的价值。新建一个项目，命名建议
`CineAI Studio Web Workbench v2`。

另外注意：你的账号下已有一个空项目 `projects/4741441208992393473`
（2026-10-01 创建，无标题、无设计主题）。如果那是你之前的尝试，可以直接用它。

### 步骤 2 · 播种设计系统

Stitch 支持直接上传 `DESIGN.md` 来生成设计系统。两种做法二选一：

**做法 A（推荐）· 上传设计契约**

在 Stitch 的项目里找到设计系统 / 主题入口，上传 `design/stitch/DESIGN-v2.md`。
Stitch 会据此生成颜色、字体与圆角令牌。上传后进入步骤 3 核对。

**做法 B · 在界面上手动设置**

按下列确切取值填写。这些是 Stitch 后端枚举允许的值。

| 字段 | 取值 | 理由 |
| --- | --- | --- |
| 模式 | `Dark` | 保持 v1 的暗色电影感 |
| 主色 | `#F5B942` | 与 `DESIGN.md` 的电影暖金一致 |
| 圆角 | `ROUND_EIGHT` | 与 v1 相同，按钮与输入框的主导体感。想更柔和可改 `ROUND_TWELVE` |
| 标题字体 | `GEIST` | 干净的现代无衬线 |
| 正文字体 | `GEIST` | 同上 |
| 标签字体 | `GEIST` | 同上 |
| 色彩方案 | `TONAL_SPOT` | 默认，中性面为主 |
| 主色覆盖 | `#F5B942` | — |
| 次色覆盖 | `#A293EE` | 保留紫色 = AI 语义 |
| 第三色覆盖 | `#75C9A1` | 完成绿 |
| **中性色覆盖** | `#16181F` | **务必设置，见下方说明** |

关于字体，有一点必须知道：**Stitch 的字体枚举里没有任何中文字体**，
`GEIST`、`INTER`、`SORA` 都不含中文字形。所以字体选择实际只影响拉丁字母、
数字和标点，中文最终仍由系统字体渲染。这对你是好事——中文字体栈保持
`PingFang SC` / `Microsoft YaHei` 不动，只让数字与时间码变好看。

关于中性色：v1 项目用 `#F5B942` 做种子色，Stitch 生成的中性面是
`background: #11131a`，而你的应用用的是 `#0E0F13`，两者并不一致。
本次把 `overrideNeutralColor` 固定为 `#16181F`，可以避免 Stitch 的
Material 3 明度阶梯再次偏离你的 CSS 变量。

等宽字体没有对应的主题字段，只能在每条提示词里用文字要求（提示词包已包含）。

### 步骤 3 · 核对设计系统

保存后确认生成的令牌符合预期，重点看三处：

- 背景是不是接近 `#0E0F13`，面板是不是接近 `#16181F`；
- 主色是不是 `#F5B942`，而不是被 Material 3 调成 `#ffda9c` 这类浅金色；
- 圆角档位是不是 8px 左右的量级。

不对就调，不要带着错误的设计系统往下走。

### 步骤 4 · 生成锚点屏

按 `SCREEN-PROMPTS.md` 第四章的顺序，先生成**屏幕 1 · 分镜创作**。
原因：这一屏信息最密集，它决定整套面板宽度、卡片槽位、状态语言与密度基线。
后续所有屏幕都要向它对齐。

生成时：

1. 粘贴第二章的通用前缀；
2. 紧接着粘贴屏幕 1 的专属段落；
3. 确认设计系统已选中；
4. 设备类型选 Desktop；
5. 发送，等待数分钟。

### 步骤 5 · 用参考图做定向重设计

想针对现有界面改，而不是从零生成时，用网页版的图片上传功能：
把 `current-ui/` 里对应截图传上去，配合这样的提示词：

```text
这是当前已实现的分镜创作界面截图。请重新设计它，要求：
保留现有的全部信息与字段，以及三栏结构和底部时间轴的骨架；
重点解决这些问题：正文最小字号提高到 11px 以上、
分镜卡片建立明确的槽位顺序与主次、
同一镜头编号只出现一次（当前场景列表渲染成了「01 01 · 再试一次」）、
右侧检视栏的分段从 10 个收敛到 5 个。
不要改变暗色电影感的配色与金色语义。
详细约束见随附的设计契约。
```

这一步是 MCP 做不到的，也是网页版最大的价值。

### 步骤 6 · 逐屏推进并迭代

按第四章的 12 屏顺序推进。每一屏生成后，先用 `SCREEN-PROMPTS.md` 第八章的
自检清单核对，不通过就用第六章的迭代提示词定点修，不要重开一屏。

### 步骤 7 · 探索方向

主要屏幕定稿前，用变体功能做方向验证。选中一屏后按
`SCREEN-PROMPTS.md` 第七章的提示词生成 2–3 个变体。变体的
`creativeRange` 建议：布局探索用 `REIMAGINE`，配色微调用 `REFINE`。

### 步骤 8 · 回传到仓库

每屏定稿后，把两张东西存进仓库：

```text
design/stitch/v2/
  01-storyboard.png            截图（Stitch 直接下载）
  01-storyboard.html           Stitch 导出的 HTML
  01-storyboard.prompt.md      本条提示词的最终版本
```

HTML 一定要存。落地时需要的令牌名、间距节奏和组件边界都在里面，
只看截图会丢信息。提示词也要存，便于日后追溯某处设计为何如此。

## 四、回传后如何落地到 React

这是整件事里唯一需要写代码的部分，也是最容易做错的部分。

### 4.1 不要做的事

- **不要把 Stitch 的 HTML 复制进 `src/`。** 它依赖 CDN Tailwind、外部字体与
  Material Symbols，与你的构建方式不兼容。
- **不要顺手迁移到 Tailwind。** 你的项目现在没有 Tailwind，而 Stitch 输出的是
  Tailwind，看起来"顺理成章"。但代价是重写约 1.2 万行 TSX 的 className，
  而且对 `Creative.tsx`（955 行）、`Studio.tsx`（793 行）这类高密度编辑器，
  超长 class 串的可维护性比现在更差。本次重设计的靶子是视觉与层级，不是构建体系。
- **不要一次改完再验证。** 按 4.3 的顺序分批。

### 4.2 令牌映射

Stitch 输出 Material 3 命名的令牌，映射到你现有的 CSS 变量。落地时业务样式
只写你的变量名，不要写 M3 名字。

| Stitch / M3 令牌 | 你的变量 | 值 |
| --- | --- | --- |
| `background` / `surface-dim` | `--bg` | `#0E0F13` |
| `surface` | `--surface` | `#16181F` |
| `surface-container` | `--raised` | `#1E2129` |
| `outline-variant` | `--line` | `#2A2E38` |
| `on-surface` | `--text` | `#F2F3F5` |
| `on-surface-variant` | `--muted` | `#9298A5` |
| `outline` | `--faint` | `#5C6370` |
| `primary` / `primary-container` | `--gold` | `#F5B942` |
| `secondary` | `--purple` | `#A293EE` |
| `tertiary` | `--green` | `#75C9A1` |
| `error` | `--red` | `#EF8385` |

`globals.css:1-26` 已有这组变量，扩展而不是重建。

### 4.3 建议的实施顺序

**第一批 · 令牌层与排版阶梯（不改变布局，收益最大）**

1. 把 `DESIGN-v2.md` 第三、四、五章的令牌写成 `:root` 变量，补一个排版阶梯
   工具类集合。
2. **删除 `globals.css` 里全部 6px / 7px / 8px / 9px / 10px 字号声明。**
   这是本次改造单点收益最高的一步。实测当前 `globals.css` 有 385 处
   `font-size`，其中 316 处（82%）≤12px、207 处（47%）≤10px；而新的
   `workbench.css` 只有 52 处声明且最低 11px，本身健康，问题在于它覆盖不全，
   导致新流程大量文字继承了旧的小字号。删掉旧档位，字号问题就解决了大半。
3. 顺手给 `globals.css` 按页面分区并加分区注释。这个文件 5187 行、
   全文件只有 3 处注释且都在末尾，不改结构没法安全地重写样式。

**第二批 · 组件原语**

按 `DESIGN-v2.md` 第六章重做 `src/components/ui.tsx` 里的
`Badge` / `Empty` / `Modal` / `Preview`，以及按钮、表单字段、状态徽标。
这五个组件覆盖了全站大部分视觉。

**第三批 · 逐屏落地**

按 `SCREEN-PROMPTS.md` 第四章的顺序逐屏改，先 `/studio` 分镜工作台。

### 4.4 顺手清掉的技术债

这些都已在本次盘点中核实，建议与重设计同批处理：

| 问题 | 证据 | 建议 |
| --- | --- | --- |
| 颜色未令牌化：`globals.css` 有 411 处硬编码色值，368 个不同值 | 深色区就有 148 个不同值，含 `#191b22` `#191b23` `#181a21` `#15171e` `#151820` 这类肉眼难辨的近似重复 | 第一批一并收敛到令牌 |
| `.cw-readiness-rows` 在两个文件里重复定义且取值不同 | `globals.css:5182-5186` 与 `workbench.css:942-945`，一处 `minmax(0,1fr)` 一处 `1fr`，一处 `--cw-success` 一处 `#8aa18c` | 保留一处 |
| `.cw-technical` 没有任何样式定义 | 全仓库只有 `TechnicalDetails.tsx:5` 引用，无 CSS 规则 | 补样式，否则技术详情是无样式裸元素 |
| `/export` 与 `/queue` 不加载 `workbench.css` | `workbench.css` 只在 `Creative.tsx:29` 被 import | 把跨页共用样式提到全局样式表 |
| 结算单位不统一 | 费用弹窗用人民币（`copy.ts:13`），视频生成弹窗用「积分」（`VideoGeneration.tsx:77-78`） | 统一为人民币 |
| 主页侧栏时长显示 `00:00:00` | `timecode()` 已返回 `mm:ss`，`AppShell.tsx:268` 又追加了 `:00` | 去掉重复拼接 |
| `.export-action-panel` 用金色渐变边框 | `globals.css:3231-3237` | 改普通描边，金色只留给主按钮 |
| 3D 人物默认色等于操作金色 | `Director.tsx:177` 使用 `#f5b942` | 改为中性灰，避免语义冲突 |
| local / remote 双轨界面 | `Studio.tsx:63` 与 `Characters.tsx:158` 按模式渲染两套 UI | 当前 `NEXT_PUBLIC_API_MODE=remote`，旧版组件是死代码；删掉可让重设计面积减半 |

### 4.5 字体落地

如果采用 Geist，用 `next/font` 自托管，保持 `DESIGN.md:33` 那条
"无需在线字体服务即可打开应用"的约束不被破坏。不要用 `<link>` 引 Google Fonts CDN。

```ts
// src/app/layout.tsx 示意
import { Geist, JetBrains_Mono } from "next/font/google";
const sans = Geist({ subsets: ["latin"], variable: "--font-sans" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono" });
```

中文字体栈保持不变，只把 `--font-sans` 插到中文回退之前：

```css
font-family: var(--font-sans), Arial, "PingFang SC", "Microsoft YaHei", sans-serif;
```

### 4.6 图标落地

Stitch 会用 Material Symbols，你的项目用 `lucide-react`。落地时按
`DESIGN-v2.md` 第九章的对照表替换，不要引入图标字体。

## 五、验收

设计阶段（每屏生成后）：用 `SCREEN-PROMPTS.md` 第八章的自检清单。

落地阶段：

1. `npm run typecheck` 与 `npm run build` 通过。
2. `npm run test:web` 通过。注意 `Home.test.tsx` 已断言封面不出现英文标题，
   `copy.test.tsx` 已断言技术详情默认折叠，改动这两处相关 UI 时不要破坏断言。
3. 在 1440×1000 与 1920×1080 下截图对比设计稿。
4. 用以下脚本统计字号，确认没有小于 11px 的声明：

```bash
python3 - <<'PY'
import re
bad = []
for f in ["src/app/globals.css", "src/features/creative/workbench.css"]:
    for m in re.finditer(r'font-size:\s*([0-9.]+)px', open(f).read()):
        if float(m.group(1)) < 11:
            bad.append((f, m.group(1)))
print("小于 11px 的声明:", len(bad))
for f, v in bad[:20]:
    print(" ", f, v)
PY
```

5. 键盘 Tab 走一遍 `/studio` 全流程，确认焦点环可见且顺序合理。
6. 打开 `prefers-reduced-motion` 确认动效被关闭。

## 六、可选：用 MCP 自动化

网页版做视觉决策，MCP 适合批量重跑或把结果拉回仓库。

服务已在 `~/.codex/config.toml` 的 `[mcp_servers.mystitchdemo]` 配好，
端点为 `https://stitch.googleapis.com/mcp`，请求头 `X-Goog-Api-Key`。
实测为无状态服务，不需要会话 ID，每次直接 POST 即可。可用工具：

```text
create_project / get_project / delete_project / list_projects
list_screens / get_screen
generate_screen_from_text / edit_screens / generate_variants
create_design_system / create_design_system_from_design_md /
update_design_system / list_design_systems / apply_design_system
upload_design_md
```

生成一屏的调用形态：

```bash
curl -s -X POST https://stitch.googleapis.com/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Goog-Api-Key: $STITCH_API_KEY" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "generate_screen_from_text",
      "arguments": {
        "projectId": "<v2 项目 ID，不带 projects/ 前缀>",
        "prompt": "<通用前缀 + 屏幕提示词>",
        "deviceType": "DESKTOP",
        "modelId": "GEMINI_3_8_FLASH",
        "designSystem": "assets/<设计系统 ID>"
      }
    }
  }'
```

注意事项：

- 生成要几分钟，`generate_screen_from_text` 的说明明确写了超时不要重试，
  改用 `get_screen` 查结果。
- 可用模型只有 `GEMINI_3_8_FLASH` 与 `GEMINI_3_5_FLASH_LITE`。
- 设计系统 ID 通过 `get_project` 或 `list_design_systems` 获取，
  形如 `assets/15996705518239280238`。
- 让 MCP 和网页版同时操作同一个项目容易互相覆盖，二选一。

## 七、重新拍摄当前界面截图

界面改动后按下列步骤重拍，保持与设计稿对照的有效性。

前提：开发服务器在 `127.0.0.1:3000` 运行，后端可达（`/` 页面必须显示
「已连接工作台」并列出真实项目，否则截到的是错误态）。

```bash
playwright-cli -s=stitchcap resize 1440 1000
playwright-cli -s=stitchcap goto http://127.0.0.1:3000/
playwright-cli -s=stitchcap screenshot
```

截图默认落在 `.playwright-cli/page-<时间戳>.png`，移动到
`design/stitch/current-ui/` 并按第二章的表命名。

分镜阶段需要额外一步：先切到有分镜数据的项目，再点开「04 分镜创作」阶段。
默认落在故事方案阶段，直接截会得到空态。

```js
await page.goto('http://127.0.0.1:3000/');
await page.waitForTimeout(3500);
await page.locator('select[aria-label="切换项目"]')
          .selectOption({ label: '给夜晚留一盏灯' });
await page.goto('http://127.0.0.1:3000/studio');
await page.waitForTimeout(3500);
await page.getByRole('button', { name: /04 分镜创作/ }).first().click();
await page.waitForTimeout(3000);
await page.screenshot({ path: 'design/stitch/current-ui/03b-studio-storyboard.png' });
```
