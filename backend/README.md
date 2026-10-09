# CineAI Studio 后端

本目录在 Phase B1 基础上实现角色资产创作流程。新增
[流程与数据契约](../design/specs/创作流程改造与验收.md)与
[真实验收记录](../design/specs/创作流程实际验收记录.md)。

基础技术栈：FastAPI、PostgreSQL、Celery/Redis、DeepSeek、图片中转、
MiniMax TTS、本地文件存储、七牛临时素材传输和 ffmpeg 合成。前端可通过 `remote` 模式使用这些接口。
视频模型默认关闭；启用 CompShare MiniMax H3 后支持真实动态镜头与本地成片。
导出记录按所用素材标注“AI 视频成片”“混合视频成片”或“分镜动态预演成片”。

## 本机启动

推荐从仓库根目录使用一键脚本。它在后台启动前端、API、五类 Worker 和 Beat，
先检查配置并执行数据库迁移。重复启动复用已有进程。

```bash
./start.sh                 # 启动全部服务
./start.sh --open          # 启动并打开浏览器
./start.sh restart         # 重启本脚本管理的服务
./start.sh stop            # 停止本脚本管理的服务
./start.sh status          # 显示地址及前后端访问状态
```

客户端的启动命令填写 `./start.sh`，工作目录选择本项目即可。
macOS Finder 也可双击根目录的 `start.command`。
服务在后台运行，关闭启动终端不会停止；使用 `./start.sh stop` 停止。

前端优先使用 3000，后端优先使用 8001，避开其他项目常用的 8000。
端口占用时自动寻找空闲端口，实际地址以启动输出为准。
脚本同时设置前端 API 地址与后端 CORS，不修改 `.env.local` 中的密钥，
也不启动、关闭或重建 PostgreSQL / Redis。
可通过 `CINEAI_WEB_PORT=3002 CINEAI_API_PORT=8100 ./start.sh` 指定优先端口。
已有实例运行时需先停止，新的端口参数才生效。

运行记录与日志在 `.runtime/launcher/`：`state.json` 保存本脚本的进程和端口；
`frontend.log`、`backend.log`、`launcher.log` 保存启动日志。
停止和重启只操作该脚本创建的进程，不会根据端口杀掉其他项目。
首次切换到一键脚本前，需先停止之前手动启动的本项目进程，避免重复 Worker。

若尚未安装依赖，先执行 `uv sync --project backend` 和 `npm ci`。
原手动启动方式继续可用：

```bash
backend/.venv/bin/python backend/scripts/check_config.py
backend/.venv/bin/python backend/scripts/dev.py
# 另一终端启动前端；默认直连 8000，或自行设置 NEXT_PUBLIC_API_BASE_URL
npm run dev
```

配置校验失败会直接退出，禁止用 `TESTING=true` 绕过生产启动器。

本机已建立 `cineai` 数据库并执行初始迁移。Redis 使用现有 `local-redis`
容器暴露的 `127.0.0.1:6379`，逻辑库为 4；所有队列和缓存带 `cineai` 前缀。
没有修改其他项目的 Redis、PostgreSQL 数据或容器。

## 配置

配置优先级由低到高为根目录 `.env.example`、`.env`、`.env.local`、进程环境变量。
七牛密钥仅填写 `.env.local`，不要放入 `NEXT_PUBLIC_*` 或 Next.js `env` 配置。
`.env.local`、本地素材目录和运行日志均已加入忽略规则。

关键运行配置如下。数据库账号应按部署环境修改，示例不包含密码。

```dotenv
DATABASE_URL=postgresql+asyncpg://zenghao@127.0.0.1:5432/cineai
REDIS_URL=redis://127.0.0.1:6379/4
NEXT_PUBLIC_API_MODE=remote
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
API_CORS_ORIGINS=http://127.0.0.1:3000,http://localhost:3000
FEATURE_VIDEO_GENERATION=false
LOCAL_MEDIA_ROOT=data/media
MEDIA_BASE_URL=http://127.0.0.1:8000/media
QINIU_S3_BUCKET=aigc2030
QINIU_S3_REGION=cn-east-1
QINIU_S3_ENDPOINT=https://s3.cn-east-1.qiniucs.com
QINIU_TEMP_PREFIX=cineai-tmp/
QINIU_TEMP_RETENTION_DAYS=3
QINIU_SIGNED_URL_TTL_SECONDS=86400
COST_HARD_LIMIT_CENTS=5000
COST_UNIT_PRICE_JSON={"llmPerMToken":0,"imagePerCall":0,"ttsPerKChar":0,"videoPerSec":0}
```

`COST_UNIT_PRICE_JSON` 的单价单位为“分”，不是元；费用均标记为估算，未对接
服务商账单。未填写单价时界面明确显示估算不可用，零值不代表免费。
任务在入队时预留估算预算，同一项目通过数据库行锁串行检查，防止并发超额。
失败请求是否由服务商收费无法由本地推断，真实账单以服务商为准。

模型服务必填项包括 `DEEPSEEK_API_KEY`、`IMAGE_API_KEY`，以及当前 TTS 服务的密钥。
视频使用独立的 `MINIMAX_VIDEO_API_KEY`，不复用 MiniMax TTS 密钥。
本地保存、预览、下载、复制和 ffmpeg 合成不需要对象存储连接。
七牛仅在外部 API 要求公网素材 URL 时使用；此时需要 `QINIU_ACCESS_KEY`、
`QINIU_SECRET_KEY` 和 `QINIU_S3_BUCKET`。空间名填写控制台的 S3 空间名。

## 本地素材与七牛临时传输

`data/media/` 是主存储，路径相对于项目根目录，也可配置绝对路径。
API 和所有 Worker 必须使用同一目录；容器部署需挂载同一个持久目录。
项目元数据继续保存在 PostgreSQL。备份时同时备份数据库与素材目录。

`GET /media/{key}` 和 `HEAD /media/{key}` 从本地返回素材，支持 Range、
ETag 与浏览器缓存。页面不再获取云端签名地址。
`MEDIA_BASE_URL` 必须指向浏览器能访问的本地 API，包含 `/media` 后缀。
一键启动器根据实际 API 端口自动设置这个地址。
`/api/health` 检查本地目录读写能力，不以七牛连接作为本地工作台的启动条件。

参考图生图使用 multipart 直接发送本地文件。CompShare H3 首帧使用 Data URL
直接发送，无需上传七牛；生成的视频下载到本地保存。其他外部 API 需要公网素材时，
七牛临时桥接支持同日复用、24 小时签名和到期清理，临时链接不作为长期资源地址。

执行以下命令配置并回读七牛生命周期，然后验证上传、签名下载和重复素材复用。
命令只更改名为 `CineAITemporaryMedia` 的规则，保留其他规则；测试文件验证后删除。
日志不输出密钥或签名 URL。

```bash
backend/.venv/bin/python backend/scripts/check_qiniu.py --configure-lifecycle
```

规则仅匹配 `QINIU_TEMP_PREFIX`，默认 3 天后过期。云端生命周期在本机停机时仍有效，
实际删除时间由七牛调度决定。Beat 每小时补充清理该前缀中超过 3 天的文件。
修改保留期或前缀后需再次执行上述配置命令；仅校验连接时省略该参数。
临时文件过期不会删除本地原件。普通浏览、生成结果保存和合成不会上传七牛。

2026-09-29 切换时，按用户要求清理旧 COS 关联的三个项目、全部关联记录与
旧的本地验收媒体文件，不迁移欠费 COS 素材。前端服务端模式不再持久化素材 URL，
已有 v1 缓存在升级后清除项目快照，重新从 API 获取数据。

## 任务与接口

[OpenAPI](http://127.0.0.1:8000/openapi.json) 是接口联调入口。
模型生成、AI 辅助和试听都进入 Celery，不阻塞 API 的事件循环。

- 项目、分镜、角色：创建、编辑、复制、删除与分镜排序。
- 剧本：`POST /api/projects/{id}/script/generate`，两段式 JSON 校验。
- 批量生图、配音：`POST /api/tasks`，`kind=image|tts`。
- AI 辅助：`POST /api/ai/optimize-prompt|camera-description|stage-layout`。
- 试听：`POST /api/tts/preview`，请求包含 `projectId/text/voiceId`。
- 导出：`POST /api/projects/{id}/exports`，返回 `taskId/exportJobId`。
- 进度：`GET /api/tasks/{id}`、项目 SSE、`GET /api/exports/{id}`。
- 上传：`POST /api/assets/upload`；也兼容 JSON DataURL 上传。

为遵循 Spec 的“长耗时任务一律入队”，TTS 与 AI 辅助统一返回 `202 + taskId`，
结果从任务详情的 `result` 获取；不采用文档个别示例中的同步返回 URL。
列表默认返回数组，分页游标在 `X-Next-Cursor` 响应头中，与资源数组约定兼容。
剧本 SSE 提供真实执行阶段事件，尚不逐 token 转发 LLM 文本。

项目级暂停只阻止该项目新任务开始，运行中的任务继续执行，不停止其他项目。
取消在 Provider 前后及 ffmpeg 运行期间检查；已发送的外部请求无法撤销收费。
重试创建新的任务 ID，避免 Celery revoked 缓存影响，旧任务保留历史。
数据库出站任务记录由 Beat 每 5 秒补投，不能只启动 API 而省略 Beat。
重复投递通过 Redis 执行锁防重；任务状态和结果以 PostgreSQL 为准。

旧接口编辑正在生成的分镜、导出中的项目以及删除含活动任务的项目会返回 409，
先取消或等待任务完成后再修改。成功结果按参数去重，重复生图复用原资产。
项目复制会复制本地文件，删除任一项目不影响另一个；项目删除后 Beat 清理本地文件。

## 媒体管线

新版首帧图使用风格、场景、明确出场角色版本及参考图编号。
参考图数量由 `IMAGE_MAX_REFERENCES=2` 控制，超出时显式记录降级。参考图接口明确不支持时才降级，
普通鉴权失败、限流或内容拒绝不会伪装为成功。新版 TTS 按台词发言人的已选音色逐句处理，旁白独立配置；长文本
按标点拆分，合成后测量时长并写回 `audioDurationMs`。

ffmpeg 支持 MP4/WebM、720p/1080p/2K、24/30fps、三个画幅、六种静帧运镜，
以及字幕、配音、BGM 闪避、片头与水印。没有视频模型时不会生成“AI 视频”。
音轨按镜头时间线排列，镜头自动延长以避免截断台词。
本机 macOS Worker 使用独立的 solo 进程，每个并发名额对应一个唯一名称的 Worker。
其他平台使用 prefork；不同队列独立运行。

本机 ffmpeg 不含 libass。后端检测到这一情况时，使用 Pillow 与中文字体
生成字幕透明层，再由 ffmpeg 按时间段烧录；有 libass 时使用 ASS 滤镜。
可用 `SUBTITLE_FONT_PATH` 指定字体。Docker 镜像安装 Noto CJK。

可选素材位置如下。缺少片头或水印时记录跳过。选择背景音乐但缺少素材时返回明确错误；
可在导出页上传 BGM 并选择，重新混音不再调用生成模型。

```text
public/assets/bgm/悬疑.mp3
public/assets/bgm/温情.mp3
public/assets/bgm/热血.mp3
public/assets/bgm/轻快.mp3
public/assets/watermark.png
public/assets/intro.mp4
```

`transition=fade` 为镜头首尾淡入淡出，默认硬切。当前不是跨镜头重叠的 xfade。
MiniMax H3 的配置与恢复方式见下一节。
音色设计使用 MiniMax `voice_design`；预设匹配查询账号实际 `get_voice` 目录。
新版不再默认取第一个角色音色；旧项目缺少音频时需升级并明确绑定发言人。

## CompShare MiniMax H3 视频

在根目录 `.env.local` 配置以下字段，并重启 API 与 Worker。真实密钥仅保存在
这个被忽略的本地文件中；参见[服务商 API 文档](https://www.compshare.cn/docs/minimax-h3/api/minimax-h3-video-api)。

```dotenv
FEATURE_VIDEO_GENERATION=true
MINIMAX_VIDEO_API_KEY=<你的专用密钥>
MINIMAX_VIDEO_BASE_URL=https://cp.compshare.cn
MINIMAX_VIDEO_MODEL=MiniMax-H3
MINIMAX_VIDEO_CREATE_PATH=/minimax/v2/video_generation
MINIMAX_VIDEO_QUERY_PATH=/minimax/v2/query/video_generation
MINIMAX_VIDEO_RESOLUTION=480P
MINIMAX_VIDEO_POLL_INTERVAL_MS=10000
VIDEO_CONCURRENCY_LIMIT=2
VIDEO_POINTS_HARD_LIMIT=2000
VIDEO_LEASE_SECONDS=1200
```

确认分镜与素材后，在分镜页选择 **生成视频** 查看实际输入、积分预估和余额，
再一次提交全部就绪镜头。后台按并发上限执行，页面关闭后仍继续生成；刷新可恢复观察。
默认 480P 为每秒 5 积分，单镜 4–30 秒，非整数秒向上取整。
积分单价根据文档估算，实际以服务商为准；积分与项目人民币估算分开显示。
`GET /api/projects/{id}/video-quote` 只查询余额和待生成镜头，不创建付费任务。

提交通过 `POST /api/tasks` 的 `kind=video` 完成。创作项目必须已确认分镜，
并选用未过期的首帧。每次创建携带稳定的 `Idempotency-Key`，立即保存平台任务 ID；
轮询解析 `task.status` 和 `task.content.url`。查询、下载或 Worker 中断后，
在生成队列重试原任务会保留平台任务 ID；已完成镜头不会再次生成。
平台返回失败或取消时不会自动新建付费任务。

`VIDEO_CONCURRENCY_LIMIT` 控制同一供应商账号的在途远端任务上限，默认 2。
所有 Worker 共用 Redis 租约，不能通过增加进程绕过上限。
macOS 启动器为视频启动对应数量的 solo 进程，名称包含启动进程和序号；
Linux 使用相同数量的 prefork 并发。生产环境可单独运行 Worker，另行启动 API 和 Beat：

```bash
backend/.venv/bin/python backend/scripts/workers.py
```

`VIDEO_POINTS_HARD_LIMIT` 是每项目 H3 积分硬上限，与人民币成本上限独立。
例如 30 秒、480P 的基础费用估计为 150 积分；可按实际修正预算设置较小上限。
短数据库事务原子预留项目预算，短 Redis 预算锁读取最新余额并计入正在提交的任务。
供应商确认提交前保留预留额；确认后通过下一次余额读取核对，避免再次扣除供应商已预留的积分。
长时间视频生成和轮询不持有预算锁。报价中的 `reservedPoints` 是本项目活动任务估算，
供应商余额可能已包含扣减，不能直接将两者再次相减作为真实账单。

`VIDEO_LEASE_SECONDS` 是 Worker 中断后的并发租约期限，默认 1200 秒，运行时持续续期。
Beat 自动恢复中断的视频任务，保留远端任务 ID 和幂等键；
POST 网络结果未知时只能恢复同一幂等提交，不能自动新建付费任务。
限流按退避时间重新排队；单镜失败保留记录，其他独立镜头继续完成。
完成顺序不改变分镜顺序。只有填写 `continuity_from` 的真实前镜尾帧依赖会等待：
前镜完成后，本地抽取尾帧并记录实际资产与源视频版本，再提交该镜。

`shot.video_input` 支持 `first_frame`、`first_last_frame`、`references` 三种模式。
首尾帧各最多 1 张，不能与参考素材混用；参考图最多 9 张、视频 3 个、音频 3 个，
合计最多 12 个。参考音频必须配合参考图片或视频。
图片、视频、音频的单文件上限分别为 30、50、15 MiB，请求体上限为 72 MiB。
提示词的 `<Picture N>`、`<Video N>`、`<Audio N>` 按各类实际素材分别编号，
标签与素材不匹配会在付费提交前拒绝。

默认关闭提示词优化并请求无声视频，合成时使用已绑定的对白、音效与字幕。
图片与成片继续保存在 `data/media/`。原生 480P 与 1080p 本地导出是不同规格，
本地放大不会增加画面细节，也不会调用付费超分。

## 测试与验收

运行测试需要本机 PostgreSQL 的独立 `cineai_test` 数据库、Redis 逻辑库 5
与 ffmpeg。测试仅重建该测试库中的表，不操作 `cineai`。
测试数据库 URL 可通过 `CINEAI_TEST_DATABASE_URL` 覆盖，库名必须以 `_test` 结尾。

```bash
cd backend
.venv/bin/python -m pytest -q
# 视频模式、原子预算、并发、幂等恢复的 mock 回归
.venv/bin/python -m pytest -q tests/test_minimax_video.py tests/test_video_pipeline.py
.venv/bin/ruff check app tests scripts --select F
```

测试覆盖 CRUD、外键隔离、排序、复制、重复入队、费用拦截、取消/重试、
实际 Celery/Redis 消费、SSE 上限与清理、模型 JSON 修复、参考图降级、
MiniMax hex 解码、长文本切分和真实 ffmpeg 合成。
新增覆盖本地素材读写、越界路径、缓存与视频 Range、资源绑定与复制、
七牛上传复用、3 天清理、生命周期规则保留、视频首帧直传及本地成片清理。
测试 Provider 使用 Fake，不消耗云模型额度。

2026-09-22 历史实测（以下项目和媒体已在本次存储切换时清理）：

- DeepSeek 真实调用成功，返回合法镜头描述。
- 图片中转真实调用成功，保存一张 PNG 首帧。
- 真实 ffmpeg 输出 32 秒、1920×1080、24fps 的 MP4，含音轨和中文字幕。
  该视频的画面与测试音是 Fake Provider 提供，不是真实 TTS 验收。
- 后续真实链路验收已完成：项目“末世信使 · 真实链路验收”，8 个真实生成分镜、
  8 张 AI 首帧、8 条 MiniMax 台词/旁白及 1 条试听音频，全部上传 COS。
- 成片为 41.291 秒、1920×1080、24fps、H.264/AAC 的 MP4，含真实配音和硬字幕。
  视频模型调用次数为 0；画面由真实首帧经 ffmpeg 静帧运镜合成。
- 项目 ID：`0db11a934e3f4bc98e7b8b67620443c6`。
  导出 ID：`4e5b011224a345d39eacd1d9cfe80a8e`。
  工作台导出页可在刷新后重新加载成片；Chrome 已验证播放推进、无解码错误。
  Codex 内嵌浏览器在点击播放时出现崩溃，建议用 Chrome 查看成片。
- macOS 启动器使用 Celery solo 池，避免默认进程池初始化失败。
  Linux 保持 prefork。

自动化测试产物在 `output/backend-verification/`，不进入版本控制。
历史真实成片已清理，原下载路径不再有效。
生产启动会在缺少上述必填配置时失败，不会自动降级到 Fake。


## 创作流程升级

启动器自动执行 `0003_creative_flow`。这是增量迁移，正常启动不清空项目或素材。
新版创作任务只保存候选，选用时检查输入版本；旧任务不能覆盖新修改。
编辑和候选操作进入 `/api/creative`，导出仍为 `/api/projects/{id}/exports`。
全局角色库保存不可变快照与媒体副本，项目复用后保持自己的版本。
新版生成遇到外部超时不自动重试付费请求，已完成的单句配音在重试时复用。

进入新建页输入创意；旧项目通过工作台中的“升级创作流程”显式补全。
旧验收项目已按本次存储切换要求清理；历史过程见真实验收记录。
