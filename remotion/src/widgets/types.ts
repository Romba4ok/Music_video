import type { Tween } from "./anim";

// Contract with pipeline/widgets_plan.py (it resolves kinds, defaults, notifications and cleans drawn SVG; this side only draws).
export type Notify = { app: string; text: string; icon: string; glyph?: string };
export type Widget = Record<string, any> & { kind?: string; frames?: string[]; tw?: Tween[]; anim?: boolean };
export type Scene = {
  i: number; role: "lyric" | "outro"; start: number; end: number; text: string;
  kind: string; w: Widget; app: string; icon: string; cat: string; notify: Notify | null;
};
export type Pal = { b: [string, string, string]; alt: [string, string, string]; acc: string; ta: string; tb: string; taReadable: string };
export type WidgetsProps = {
  fps: number; width: number; height: number; duration: number;
  dark: boolean; alternate: boolean; pal: Pal;
  artist: string; title: string; credit: string; hook: string; hookD: number; ostart: number; nCards: number; hasCap: boolean;
  scenes: Scene[];
};
