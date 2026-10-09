import { expect,it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { CurrentVoice } from "./CurrentVoice";
import { NarrowScreenNotice } from "./NarrowScreenNotice";
import { shotStatusClass } from "./ShotStatus";
it("B6: ready assets use helper and only stale assets use warning",()=> { expect(shotStatusClass({image_stale:false,audio_stale:false})).toBe("helper"); expect(shotStatusClass({image_stale:true,audio_stale:false})).toBe("creative-warning"); expect(shotStatusClass({image_stale:false,audio_stale:true})).toBe("creative-warning"); });
it.each([undefined,0])("B7: duration %s defers the audio player and offers audition",duration=>{ const html=renderToStaticMarkup(<CurrentVoice url="/voice.mp3" durationMs={duration}/>); expect(html).not.toContain("<audio"); expect(html).toContain("已有声音样本"); expect(html).toContain("试听"); });
it("known duration renders a metadata audio player",()=> { expect(renderToStaticMarkup(<CurrentVoice url="/voice.mp3" durationMs={600}/>)).toContain('<audio controls="" preload="metadata"'); });
it("B10: workbench notice has its own visible narrow-screen hook and dismissal button",()=> { const html=renderToStaticMarkup(<NarrowScreenNotice/>); expect(html).toContain('class="cw-narrow-notice"'); expect(html).toContain('role="status"'); expect(html).toContain("当前屏幕较窄"); expect(html).toContain("继续使用"); expect(html).not.toContain("hidden"); });
