import type { Character, DirectorData, Project, Scene, Task } from "./types";
export const assets = [
  "/assets/stitch-2.jpg",
  "/assets/stitch-3.jpg",
  "/assets/stitch-4.jpg",
  "/assets/stitch-5.jpg",
  "/assets/stitch-6.jpg",
];
export const defaultCharacters: Character[] = [
  {
    id: "lin",
    name: "林夏",
    age: "26",
    description:
      "末世信使，冷静寡言。在荒芜的城市之间送件，始终相信每封信都有抵达的意义。",
    clothing: "深色机车夹克，磨旧的皮革挎包",
    voice: "女声 · 冷静",
    image: assets[0],
    consistency: "参考图模式",
  },
  {
    id: "zhou",
    name: "老周",
    age: "52",
    description: "废墟里的商人，粗犷外表下藏着一颗温柔的心。",
    clothing: "棕色旧大衣，灰色围巾",
    voice: "男声 · 沉稳",
    image: assets[4],
    consistency: "参考图模式",
  },
];
const descriptions = [
  "废土城市全景，沙尘弥漫。高楼之间，一位信使穿过雨后的街道，走向城市深处。",
  "林夏停在一间旧商店前，低头检查手中泛黄的信封。霓虹灯映在她的脸上。",
  "老周推开生锈的铁门，望向远方。门缝中透出温暖的光，与街道的冷色形成对比。",
  "信封上模糊的地址逐渐清晰。林夏的手指抚过字迹，迟疑片刻，重新握紧。",
  "两人在废墟边缘相遇，风吹动破旧的旗帜，镜头缓缓绕过人物肩膀。",
  "远处的广播塔忽然亮起。林夏抬头望去，一束光穿过厚重的云层。",
  "老周从抽屉里拿出一张旧照片，轻轻放到桌上。镜头推近照片上的笑脸。",
  "林夏跨上摩托，发动机在空旷街道上轰鸣。她回头向老周点头告别。",
  "摩托穿过废弃的隧道，明暗交替的灯光掠过人物的侧脸。",
  "城市的尽头，林夏终于找到信上的小屋。窗边有一盏依然亮着的灯。",
  "一双苍老的手接过信封。林夏站在门口，露出很久未有的微笑。",
  "镜头缓缓拉远，清晨的阳光照亮废土，新的旅程即将开始。",
];
export function makeScenes(
  prefix: string,
  cover = assets[0],
  count = 12,
  initial = false,
): Scene[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `${prefix}-s${i + 1}`,
    title: ["穿越废土", "迟来的信", "旧日的回声", "未完的约定"][i % 4],
    shotType: ["全景", "中景", "近景", "特写"][i % 4],
    cameraMove: ["缓慢横移", "缓推", "固定", "跟随"][i % 4],
    durationSec: 7,
    imagePrompt: descriptions[i % 12],
    dialogue: [
      "末世第三年，我依然在送件。",
      "你确定还要去找那个人吗？",
      "总有人，在等一封信。",
      "",
    ][i % 4],
    image: initial && i < 5 ? cover : "",
    status: initial
      ? i < 3
        ? "done"
        : i === 3
          ? "video_pending"
          : i === 4
            ? "failed"
            : "draft"
      : "draft",
    model: "CineAI · 电影写实",
    seed: String(420180 + i),
  }));
}
export const initialProjects: Project[] = [
  [
    "last-mail",
    "末世信使",
    "在世界的尽头，送达最后一封信。",
    "电影写实",
    "剪辑中",
    0,
  ],
  [
    "moon",
    "愿此，人间皆是你",
    "一场跨越时间的重逢，一段未完待续的故事。",
    "电影写实",
    "草稿",
    1,
  ],
  [
    "inn",
    "我在大宋当掌柜",
    "从一间小小客栈开始，写下属于自己的传奇。",
    "国风古韵",
    "剪辑中",
    2,
  ],
  [
    "neon",
    "长街：霓虹 2077",
    "在霓虹与代码之间，寻找真实自我的边界。",
    "赛博朋克",
    "已导出",
    3,
  ],
  [
    "gold",
    "锦绣千金暴富录",
    "重启人生，她选择亲手改写命运。",
    "电影写实",
    "草稿",
    4,
  ],
].map((v, i) => ({
  id: String(v[0]),
  name: String(v[1]),
  description: String(v[2]),
  style: String(v[3]),
  ratio: "9:16",
  status: v[4] as Project["status"],
  cover: assets[Number(v[5])],
  updatedAt: Date.now() - (i + 1) * 3600000,
  scenes: makeScenes(String(v[0]), assets[Number(v[5])], 12, true),
  characters: defaultCharacters.map((c) => ({ ...c, id: `${v[0]}-${c.id}` })),
}));
const primaryTasks: Task[] = [
  {
    id: "task-demo-1",
    projectId: "last-mail",
    sceneId: "last-mail-s4",
    type: "视频",
    status: "running",
    progress: 42,
    createdAt: 1790000000000,
  },
  {
    id: "task-demo-2",
    projectId: "last-mail",
    sceneId: "last-mail-s5",
    type: "视频",
    status: "failed",
    progress: 0,
    createdAt: 1790000000000,
    error: "演示异常：生成任务超时。可点击重试，查看恢复流程。",
  },
  ...[1, 2, 3].map((i) => ({
    id: `task-done-${i}`,
    projectId: "last-mail",
    sceneId: `last-mail-s${i}`,
    type: "视频" as const,
    status: "done" as const,
    progress: 100,
    createdAt: 1790000000000,
  })),
];
export const initialTasks: Task[] = [
  ...primaryTasks,
  ...initialProjects
    .slice(1)
    .flatMap((p) =>
      p.scenes
        .filter(
          (s) =>
            s.status === "video_pending" ||
            s.status === "failed" ||
            s.status === "done",
        )
        .map((s) => ({
          id: `task-${s.id}`,
          projectId: p.id,
          sceneId: s.id,
          type: "视频" as const,
          status:
            s.status === "video_pending"
              ? ("queued" as const)
              : s.status === "failed"
                ? ("failed" as const)
                : ("done" as const),
          progress: s.status === "done" ? 100 : 0,
          createdAt: p.updatedAt,
          ...(s.status === "failed"
            ? { error: "演示异常：任务超时，可重试。" }
            : {}),
        })),
    ),
];
export function defaultStage(): DirectorData {
  return {
    template: "街道",
    fov: 45,
    objects: [
      {
        id: "actor-1",
        name: "林夏",
        kind: "actor",
        position: [-1, 0, 0],
        rotation: [0, 0, 0],
        scale: 1,
        color: "#f5b942",
        action: "站立",
      },
      {
        id: "actor-2",
        name: "老周",
        kind: "actor",
        position: [1.8, 0, -1],
        rotation: [0, -0.6, 0],
        scale: 1,
        color: "#9c8be8",
        action: "站立",
      },
      {
        id: "camera-1",
        name: "主摄像机",
        kind: "camera",
        position: [0, 1.5, 5],
        rotation: [0, 0, 0],
        scale: 1,
        color: "#f5b942",
        action: "固定",
      },
    ],
    keyframes: [
      { id: "key-1", objectId: "actor-1", t: 0, position: [-1, 0, 0] },
      { id: "key-2", objectId: "actor-1", t: 7, position: [1, 0, -2] },
      { id: "key-3", objectId: "camera-1", t: 0, position: [0, 1.5, 5] },
      { id: "key-4", objectId: "camera-1", t: 7, position: [1, 1.5, 3] },
    ],
  };
}
