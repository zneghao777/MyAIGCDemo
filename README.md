# CineAI Studio

基于 Stitch 项目 **CineAI Studio Web Workbench** 实现的 AI 短剧前端工作台。
支持本地演示与服务端两种模式。Python 后端及启动、配置、验收边界见
[后端说明](backend/README.md)。下文的 Mock、本地存储和浏览器录制描述适用于
`NEXT_PUBLIC_API_MODE=local`；`remote` 模式使用 PostgreSQL、HTTP 与 SSE。
服务端模式的图片、视频、音频与成片保存到 `data/media/`，页面从本地 API 读取。
仅外部生成接口要求公网素材 URL 时使用七牛临时上传，默认保留 3 天。

## 启动

使用 Node.js 20.9 以上版本。推荐当前受支持的 Node.js LTS。

```bash
npm install
npm run dev
```

打开 [本地工作台](http://127.0.0.1:3000)。
生产验证使用以下命令：

```bash
npm run typecheck
npm run build
npm start
```

## 已实现的页面与交互

工作台包含七个入口，项目和分镜状态在页面之间共享。

| 路径          | 功能                                                                        |
| ------------- | --------------------------------------------------------------------------- |
| `/`           | 项目搜索、状态筛选、排序、网格/列表、重命名、复制、删除                     |
| `/new`        | 创意输入、TXT 导入、时长、分镜数、风格、比例、角色与生成演示                |
| `/studio`     | 分镜增删复制、拖拽排序、Prompt/台词/镜头编辑、面板折叠、时间轴与预演        |
| `/director`   | WebGL 灰盒场景、人物/道具、变换手柄、坐标、机位预览、关键帧、轨迹与分镜回写 |
| `/queue`      | 两并发 Mock 队列、进度、暂停/继续、取消、失败重试和任务详情                 |
| `/export`     | 静帧预演、导出设置、本地 WebM 录制、项目 JSON 与封面 PNG 下载               |
| `/characters` | 角色人设、年龄、服装、参考图上传和浏览器语音试听                            |

项目数据通过 Zustand 保存到当前浏览器的 localStorage，键名为
`cineai-studio-v1`。切换浏览器或清理网站数据不会自动迁移项目；可下载
`.cineai.json` 进行备份。当前没有项目导入入口。

3D 导演台的修改点击 **应用到分镜** 后写入项目。
人物动作选项是结构化标签，胶囊代理只演示关键帧位置变化。
主机位预览对准第一个人物，焦段预设改变 FOV；尚不支持完整相机姿态动画。

## 本地模式的演示范围

AI 剧本由前端模板构建；生图与视频任务通过定时器模拟，完成后使用原型素材。
队列首次打开为暂停状态，便于检查生成中、失败和完成的示例状态。
所有演示任务均无真实费用。

**导出分镜预演** 使用浏览器 MediaRecorder，生成长边约 720px 的无声 WebM，
每个已有画面的分镜录制一秒。录制包含字幕选项与所选帧率。
分辨率、目标格式、背景音乐、片头片尾及品牌水印设置随项目 JSON 导出，
不在本地预演中进行完整合成。MP4、AI 视频、TTS 管线和 ffmpeg 混音需要后端。
浏览器录制期间保持页面在前台；不支持 MediaRecorder 的浏览器可下载项目文件。

角色参考图上传限制为 1.2MB。本地存储空间不足时显示保存失败提示。
语音试听使用浏览器语音合成，实际音色取决于设备，不是真实云端 TTS。
3D 视图需要浏览器 WebGL 和硬件加速；不可用时显示替代提示。

## 代码结构

页面由 App Router 提供，数据及交互逻辑集中在对应模块。

```text
backend/               FastAPI、Celery、Provider、ffmpeg、迁移与测试
src/app/               路由、全局样式与布局
src/components/        导航壳层、弹窗、预演播放器
src/features/          首页、向导、分镜、导演台、队列、导出、角色
src/lib/types.ts       项目、角色、分镜、任务与导演数据类型
src/lib/data.ts        示例项目与场景模板
src/lib/store.ts       共享状态、本地持久化、Mock 队列
src/lib/export.ts      浏览器文件与 WebM 导出
public/assets/         从 Stitch 项目取得的本地素材
design/stitch/         原型截图、首页 HTML 和 MCP 清单
design/specs/          两份原始参考文档的副本
```

技术栈为 Next.js、React、TypeScript、Zustand、React Three Fiber、drei、Three.js
与 Lucide。3D 组件动态加载，其他页面不加载整个 WebGL 编辑器。
视觉约定见 [设计规范](DESIGN.md)。
