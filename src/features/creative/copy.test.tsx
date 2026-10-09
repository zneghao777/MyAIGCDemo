import { expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { errorMessage, copy } from "./copy";
import { ApiError } from "@/lib/api";
import { ErrorNotice } from "./ErrorNotice";
import { TechnicalDetails } from "./TechnicalDetails";
const cases = [
 ["STALE_VERSION", "内容已更新"], ["STALE_CANDIDATE", "候选所依据"], ["STALE_TASK", "任务使用"], ["PRECHECK_FAILED", "未准备好"], ["REFERENCE_LIMIT", "超过当前上限"], ["REFERENCE_REQUIRED", "参考图尚未"], ["BGM_REQUIRED", "背景音乐尚未"], ["COST_LIMIT_EXCEEDED", "超过项目上限"], ["VIDEO_POINTS_LIMIT", "积分上限"], ["RATE_LIMITED", "正在稍作等待"], ["SCENE_HAS_RUNNING_TASK", "仍有任务"], ["AUDIO_EXCEEDS_VIDEO", "配音长度超过"], ["NETWORK_ERROR", "网络连接失败"],
];
it.each(cases)("B1: %s has Chinese context and recovery", (code, phrase) => { const message=errorMessage(new ApiError("raw English", 409, code)); expect(message.title).toContain(phrase); expect(message.detail).toBeTruthy(); expect(message.action).toBe("刷新页面"); expect(JSON.stringify(message)).not.toContain("raw English"); });
it("B1: unknown fetch error keeps raw details folded and offers recovery", () => {
 const markup=renderToStaticMarkup(<ErrorNotice error={new TypeError("Failed to fetch")} />);
 const visible=markup.replace(/<details[\s\S]*?<\/details>/g, ""); expect(visible).not.toContain("Failed to fetch"); expect(visible).toContain("重试"); expect(markup).toContain('role="alert"'); expect(markup).not.toContain('open=""');
 expect(errorMessage(new ApiError("raw", 502, "UNKNOWN")).title).toContain("502"); expect(errorMessage(null).title).toBe("操作未完成。");
});
it("internal details are omitted while product actions remain available", () => {
 const markup=renderToStaticMarkup(<TechnicalDetails data={{ model: "internal" }} extra={<button>保存到角色库</button>} />);
 expect(markup).not.toContain("internal"); expect(markup).not.toContain(copy.technicalDetails); expect(markup).toContain("保存到角色库");
 expect(renderToStaticMarkup(<TechnicalDetails data={{ model: "internal" }} />)).toBe("");
});
