import React, { useLayoutEffect, useRef } from "react";
import { applyTweens, pr, yoyo } from "./anim";
import type { BodyProps } from "./types";

// Card picture: only `draw` (a picture Claude drew as SVG, its shapes moved by tweens). A line without a usable drawing gets a plain gradient panel.
// The old template cards (counter, search, chat, pair, ring ...) were removed on 2026-11-09 and the eight ready-made scenes on 2026-11-16: neither may come back.
const INK = "#14141f";
const clip = (t: unknown, n: number) => {
  const s = String(t ?? "");
  return s.length <= n ? s : s.slice(0, n - 1).trimEnd() + "…";
};
const put = (el: Element | null, v: { x?: number; y?: number; scale?: number; rot?: number; o?: number }) => {
  if (!el) return;
  const s = (el as HTMLElement).style;
  s.transform = `translate(${v.x ?? 0}px, ${v.y ?? 0}px) rotate(${v.rot ?? 0}deg) scale(${v.scale ?? 1})`;
  if (v.o !== undefined) s.opacity = String(v.o);
};

const Draw: React.FC<BodyProps> = ({ w, i, u, d, ta, tb }) => {
  const ref = useRef<SVGSVGElement>(null);
  const picture = ((w.frames as string[]) ?? [])[0] || `<rect width="800" height="420" fill="${ta}" opacity="0.22"/><rect width="800" height="420" fill="${tb}" opacity="0.12"/>`;
  const at = (f: number) => Math.min(f * d, Math.max(d - 0.35, 0.1));
  useLayoutEffect(() => {
    const r = ref.current;
    if (!r) return;
    if (w.anim) applyTweens(r as unknown as HTMLElement, `dr${i}_`, (w.tw as any) ?? [], u);
    else { // a drawing without (enough) tweens still floats, so nothing on a card stands still
      const p = yoyo(u, 0, 1.1), m = w.motion;
      put(r.querySelector(`#dr${i}`), m === "pulse" ? { scale: 0.97 + 0.07 * p } : m === "sway" ? { rot: -3 + 6 * p } : m === "drift" ? { x: -18 + 36 * p } : { y: 8 - 18 * p });
    }
  });
  const bp = pr(u, at(0.3), 0.4, "back.out(1.8)"), cp = pr(u, at(0.55), 0.4, "power2.out");
  return (
    <div style={{ position: "relative", width: 820, height: 340 }}>
      <svg ref={ref} viewBox="0 0 800 420" preserveAspectRatio="xMidYMid slice" style={{ width: 820, height: 340, display: "block", borderRadius: 30, overflow: "hidden" }}>
        <g id={`dr${i}`} style={{ transformOrigin: "400px 210px" }} dangerouslySetInnerHTML={{ __html: picture }} />
      </svg>
      {w.big && <div style={{ position: "absolute", right: 22, top: 18, padding: "6px 26px", borderRadius: 30, background: "#fff", fontSize: 54, fontWeight: 900, color: INK, whiteSpace: "nowrap", opacity: pr(u, at(0.3), 0.4, "power1.out"), transform: `translateY(${-20 * (1 - bp)}px) scale(${1 + 0.03 * Math.sin(u * 5) * bp})` }}>{clip(w.big, 12)}</div>}
      {(w.chips as string[] | undefined)?.length ? (
        <div style={{ position: "absolute", left: 22, bottom: 18, display: "flex", gap: 12, opacity: cp, transform: `translateY(${24 * (1 - cp)}px)` }}>
          {(w.chips as string[]).slice(0, 2).filter(Boolean).map((c, k) => <span key={k} style={{ padding: "8px 22px", borderRadius: 26, background: "#fff", fontSize: 28, fontWeight: 700, color: INK, whiteSpace: "nowrap" }}>{clip(c, 22)}</span>)}
        </div>
      ) : null}
    </div>
  );
};

export const Body: React.FC<BodyProps & { kind: string }> = (p) => <Draw {...p} />;
