import { Composition } from "remotion";
import { DURATION, Sansara } from "./Sansara";
import { T9, T9_DURATION } from "./T9";
import { Vibe, VIBE_DURATION } from "./Vibe";
import { VibeCard, VIBECARD_DURATION } from "./VibeCard";
import { Widgets } from "./widgets/Widgets";
import type { WidgetsProps } from "./widgets/types";

// Tiny sample so Studio opens; the pipeline always passes the real props (`--props=props.json`, see pipeline/render.py).
const sample: WidgetsProps = {
  fps: 30, width: 1080, height: 1920, duration: 6, dark: false, alternate: true,
  pal: { b: ["#ffe6f1", "#e9e2ff", "#dbeafe"], alt: ["#15102b", "#241a4a", "#1a1540"], acc: "#6a5cff", ta: "#ff4f8b", tb: "#a47bff", taReadable: "#c2255c" },
  artist: "Артист", title: "Песня", credit: "автор: vybex", hook: "О ЧЁМ ЭТА СТРОКА?", hookD: 1.9, ostart: 4, nCards: 1, hasCap: false,
  scenes: [
    { i: 0, role: "lyric", start: 0, end: 4, text: "строка", kind: "scene", w: { art: "sunset" }, app: "Закат", icon: "#ff9a6b", cat: "", notify: null },
    { i: 1, role: "outro", start: 4, end: 6, text: "", kind: "scene", w: {}, app: "", icon: "#000", cat: "", notify: null },
  ],
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition id="Widgets" component={Widgets} durationInFrames={180} fps={30} width={1080} height={1920} defaultProps={sample}
        calculateMetadata={({ props }) => ({ durationInFrames: Math.max(1, Math.round(props.duration * props.fps)), fps: props.fps, width: props.width, height: props.height })} />
      <Composition id="Sansara" component={Sansara} durationInFrames={DURATION} fps={30} width={1080} height={1920} />
      <Composition id="Vibe" component={Vibe} durationInFrames={VIBE_DURATION} fps={30} width={1080} height={1920} />
      <Composition id="VibeCard" component={VibeCard} durationInFrames={VIBECARD_DURATION} fps={30} width={1080} height={1920} />
      <Composition id="T9" component={T9} durationInFrames={T9_DURATION} fps={30} width={1080} height={1920} />
    </>
  );
};
