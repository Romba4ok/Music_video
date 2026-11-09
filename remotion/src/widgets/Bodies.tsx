import React, { useLayoutEffect, useRef } from "react";
import { applyTweens, fmtNum, ft, pr, yoyo } from "./anim";
import { ART_UID, ARTS, CAMERA_ART } from "../arts.generated";
import { SCENES } from "./Scenes";
import type { Widget } from "./types";

const INK = "#14141f";
const GREY = "#5f5a7c";
const HEART = "M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z";
export const DARK_ARTS = new Set(["rain", "moon", "city", "eye", "window", "flame"]);
const clip = (t: unknown, n: number) => {
  const s = String(t ?? "");
  return s.length <= n ? s : s.slice(0, n - 1).trimEnd() + "…";
};
const num = (v: unknown, def: number) => (Number.isFinite(Number(v)) && v !== "" && v !== null && v !== undefined ? Number(v) : def);
const rndn = (i: number, k = 0) => {
  const x = Math.sin(i * 127.1 + k * 311.7) * 43758.5453;
  return x - Math.floor(x);
};

type B = { w: Widget; i: number; u: number; d: number; text: string; ta: string; tb: string; acc: string; taReadable: string };

const W = 820, H = 340;
const wrap: React.CSSProperties = { position: "relative", width: W, height: H };
const abs: React.CSSProperties = { position: "absolute", left: 0, top: 0, width: W, height: H };

// ---------- DOM-driven bits (static SVG art, drawn pictures) ----------
const put = (el: Element | null, v: { x?: number; y?: number; scale?: number; sx?: number; sy?: number; rot?: number; o?: number; box?: boolean }) => {
  if (!el) return;
  const s = (el as HTMLElement).style;
  s.transform = `translate(${v.x ?? 0}px, ${v.y ?? 0}px) rotate(${v.rot ?? 0}deg) scale(${v.sx ?? v.scale ?? 1}, ${v.sy ?? v.scale ?? 1})`;
  if (v.box) { s.transformBox = "fill-box"; s.transformOrigin = "50% 50%"; }
  if (v.o !== undefined) s.opacity = String(v.o);
};

const artAnim = (r: SVGSVGElement | null, key: string, uid: number, u: number, d: number) => {
  if (!r) return;
  const q = (id: string) => r.querySelector(`#${id}`);
  if (key === "sunset") put(q(`sun${uid}`), { y: ft(u, 0, d, 50, -30) });
  else if (key === "map") { const e = "power1.out", dd = Math.min(d, 1.6); put(q(`rip${uid}`), { scale: ft(u, 0, dd, 0.5, 1.8, e), o: ft(u, 0, dd, 0.8, 0, e), box: true }); }
  else if (key === "pulse") put(q(`hb${uid}`), { scale: ft(u, 0, Math.min(d, 1.2), 0.92, 1.08, "sine.inOut") });
  else if (key === "clock") { put(q(`mh${uid}`), { rot: u * 60 }); put(q(`hh${uid}`), { rot: u * 5 }); }
  else if (key === "rain") for (let k = 0; k < 11; k++) put(q(`d${uid}_${k}`), { y: ft(u, (k % 4) * 0.15, 0.7, -40, 110), o: ft(u, (k % 4) * 0.15, 0.7, 0, 1) });
  else if (key === "eye") put(q(`iris${uid}`), { scale: ft(u, 0, Math.min(d, 1.8), 0.8, 1.12, "sine.inOut") });
  else if (key === "moon") put(q(`st${uid}_0`), { o: ft(u, 0, Math.min(d, 1.5), 0.2, 1, "sine.inOut") });
  else if (key === "phone") for (let k = 0; k < 3; k++) put(q(`pw${uid}_${k}`), { scale: ft(u, k * 0.2, Math.min(d, 1.2), 0.7, 1.15, "power1.out"), o: ft(u, k * 0.2, Math.min(d, 1.2), 0.7, 0, "power1.out"), box: true });
  else if (key === "window") for (let k = 0; k < 4; k++) put(q(`wl${uid}_${k}`), { o: ft(u, k * 0.15, Math.min(d, 1.4), 0.55, 1, "sine.inOut") });
  else if (key === "flame") put(q(`fl${uid}`), { sx: ft(u, 0, Math.min(d, 0.9), 1.04, 0.96, "sine.inOut"), sy: ft(u, 0, Math.min(d, 0.9), 0.9, 1.08, "sine.inOut") });
  else if (key === "lock") put(q(`lk${uid}`), { y: ft(u, 0.3, Math.min(d, 1), 0, -26, "back.out(2)"), rot: ft(u, 0.3, Math.min(d, 1), 0, -16, "back.out(2)") });
  else if (key === "bird") put(q(`bd${uid}`), { sy: 0.55 + 0.55 * yoyo(u, 0, 0.45) });
  else if (key === "wave") { put(q(`wv${uid}`), { x: ft(u, 0, d, -120, 0) }); put(q(`wu${uid}`), { x: ft(u, 0, d, 0, -120) }); }
};

export const ArtSvg: React.FC<{ art: string; uid: number; u: number; d: number; style?: React.CSSProperties; panel?: boolean }> = ({ art, uid, u, d, style }) => {
  const ref = useRef<SVGSVGElement>(null);
  useLayoutEffect(() => artAnim(ref.current, art, uid, u, d));
  const markup = (ARTS[art] ?? ARTS.sunset).split(String(ART_UID)).join(String(uid));
  return <svg ref={ref} viewBox="0 0 800 420" preserveAspectRatio="xMidYMid slice" style={{ display: "block", borderRadius: 30, overflow: "hidden", ...style }} dangerouslySetInnerHTML={{ __html: markup }} />;
};

const heart = (x: number, y: number, k: number, col = "#ff4f6d") => <g transform={`translate(${x} ${y}) scale(${k})`}><path d={HEART} fill={col} /></g>;
const Cap: React.FC<{ label?: string }> = ({ label }) =>
  label ? <div style={{ position: "absolute", left: 0, top: 296, width: W, textAlign: "center", fontWeight: 700, fontSize: 30, color: GREY }}>{clip(label, 36)}</div> : null;

// ---------- kinds ----------
const Counter: React.FC<B> = ({ w, i, u, d }) => {
  const art = ARTS[w.art] ? w.art : "map";
  const a = Math.trunc(num(w.from, 0)), b = Math.trunc(num(w.to, 100));
  const size = Math.max(54, Math.min(120, Math.trunc(400 / (0.62 * Math.max(fmtNum(a).length, fmtNum(b).length, 1)))));
  const v = ft(u, 0, d * 0.7, a, b, "power2.out");
  const at = (f: number) => Math.min(f * d, Math.max(d - 0.35, 0.1));
  const inf = w.inf ? pr(u, at(0.75), 0.3, "back.out(2)") : 0;
  return (
    <div style={{ display: "flex", gap: 30, alignItems: "center", height: H }}>
      <ArtSvg art={art} uid={i} u={u} d={d} style={{ width: 330, height: H }} />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 10, minWidth: 0 }}>
        <div style={{ fontSize: 30, fontWeight: 700, color: GREY }}>{clip(w.label, 26)}</div>
        <div style={{ position: "relative", fontWeight: 900, color: INK, lineHeight: 1, whiteSpace: "nowrap", fontSize: size }}>
          <span style={{ opacity: w.inf ? 1 - pr(u, at(0.75), 0.2) : 1 }}>{fmtNum(v)}</span>
          {w.inf && <span style={{ position: "absolute", left: 0, top: 0, opacity: inf, transform: `scale(${0.5 + 0.5 * inf})` }}>∞</span>}
          <small style={{ fontSize: 30, fontWeight: 800, color: "#8a6bff", marginLeft: 8 }}>{clip(w.unit, 6)}</small>
        </div>
        <div style={{ height: 14, borderRadius: 7, background: "rgba(20,20,31,.1)", overflow: "hidden" }}>
          <div style={{ height: 14, borderRadius: 7, width: `${ft(u, 0, d * 0.7, 0, Math.trunc(num(w.fill, 1) * 100), "power2.out")}%`, filter: `brightness(${1 + 0.12 * Math.sin(u * 5)})`, background: "linear-gradient(90deg,var(--ta),var(--tb))" }} />
        </div>
        {w.button && (
          <div style={{ alignSelf: "flex-start", marginTop: 12, padding: "14px 28px", borderRadius: 30, background: "#ff4f3d", color: "#fff", fontSize: 30, fontWeight: 800, whiteSpace: "nowrap",
            opacity: pr(u, at(0.55), 0.3), transform: `scale(${(0.7 + 0.3 * pr(u, at(0.55), 0.3, "back.out(2)")) * (1 + 0.04 * Math.sin(u * 6))})`, transformOrigin: "0% 50%" }}>{clip(w.button, 20)}</div>
        )}
      </div>
    </div>
  );
};

const Search: React.FC<B> = ({ w, u, d, text, acc, taReadable }) => {
  const q = String(w.query ?? text).slice(0, 34);
  const n = Math.floor(ft(u, 0.15, d * 0.5, 0, q.length));
  const at = (f: number) => Math.min(f * d, Math.max(d - 0.35, 0.1));
  const rb = pr(u, at(0.62), 0.35, "back.out(1.8)");
  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 16, height: 90, border: `4px solid ${acc}`, borderRadius: 45, padding: "0 30px", fontSize: 40, fontWeight: 700, color: INK, boxSizing: "border-box" }}>
        <span style={{ width: 26, height: 26, border: "5px solid #9a8fb5", borderRadius: "50%", flex: "none", boxSizing: "border-box", transform: `translate(${2 * Math.sin(u * 6)}px, ${2 * Math.cos(u * 6)}px)` }} />
        <span>{q.slice(0, n)}</span>
        <i style={{ width: 3, height: 44, background: acc, display: "block", opacity: Math.floor(u * 2) % 2 ? 0 : 1 }} />
      </div>
      <div style={{ marginTop: 44, textAlign: "center", fontSize: 96, fontWeight: 900, lineHeight: 1, color: taReadable, opacity: pr(u, at(0.62), 0.35), transform: `scale(${(0.8 + 0.2 * rb) * (1 + 0.03 * Math.sin(u * 5) * rb)})` }}>{clip(w.result ?? "0 результатов", 18)}</div>
      <div style={{ marginTop: 16, textAlign: "center", fontSize: 36, fontWeight: 700, color: GREY, opacity: pr(u, at(0.7), 0.3, "power1.out"), transform: `translateY(${14 * (1 - pr(u, at(0.7), 0.3, "power1.out"))}px)` }}>{clip(w.sub, 34)}</div>
    </>
  );
};

const Camera: React.FC<B> = ({ w, i, u, d }) => {
  const ref = useRef<HTMLDivElement>(null);
  const at = (f: number) => Math.min(f * d, Math.max(d - 0.35, 0.1));
  useLayoutEffect(() => {
    const r = ref.current;
    if (!r) return;
    const zoom = num(w.zoom, 4.6);
    const zt = r.querySelector(`#zt${i}`);
    if (zt) zt.textContent = ft(u, 0, d * 0.8, 1, zoom, "power2.inOut").toFixed(1) + "x";
    const vf = pr(u, 0.1, 0.4, "power3.out");
    put(r.querySelector(`#vf${i}`), { scale: 1.5 - 0.5 * vf, o: vf });
    const vfe = r.querySelector<SVGElement>(`#vf${i}`);
    if (vfe) { vfe.style.transformOrigin = "400px 190px"; }
    const rec = r.querySelector<SVGElement>(`#rec${i}`);
    if (rec) rec.style.opacity = String(1 - 0.8 * yoyo(u, 0, 0.25, "none"));
    for (let q = 0; q < 5; q++) {
      const h = r.querySelector<SVGElement>(`#ht${i}_${q}`);
      if (h) h.style.opacity = String(ft(u, at(0.6 + q * 0.05), 0.9, 0, 1, "power1.out") * (u >= at(0.6 + q * 0.05) ? 1 : 0));
    }
  });
  const markup = CAMERA_ART.split(String(ART_UID)).join(String(i)).replace("@F@", clip(String(w.focus ?? "ЦЕЛЬ"), 12).toUpperCase());
  const bub = clip(w.bubble ?? "", 10);
  const bp = pr(u, at(0.62), 0.35, "back.out(2)");
  return (
    <div ref={ref} style={wrap}>
      <svg viewBox="0 0 800 420" preserveAspectRatio="xMidYMid slice" style={{ ...abs, borderRadius: 30 }}>
        <g dangerouslySetInnerHTML={{ __html: markup.replace(/^<defs>.*?<\/defs>/, "").replace(/<rect width="800" height="420"[^>]*\/>/, "") }} />
      </svg>
      {bub && (
        <svg viewBox="0 0 800 420" preserveAspectRatio="xMidYMid slice" style={{ ...abs, opacity: bp, pointerEvents: "none" }}>
          <g style={{ transform: `scale(${0.5 + 0.5 * bp})`, transformOrigin: "470px 174px" }}>
            <rect x={470} y={110} width={60 + 22 * bub.length} height={64} rx={32} fill="#ff4f8b" />
            <text x={500 + 11 * bub.length} y={153} textAnchor="middle" fontSize={36} fontWeight={800} fill="#fff">{bub}</text>
          </g>
        </svg>
      )}
    </div>
  );
};

const Chat: React.FC<B> = ({ w, u, d, text }) => {
  const msgs = ((w.msgs as any[]) ?? [{ from: "her", text }]).slice(0, 3);
  const at = (f: number) => Math.min(f * d, Math.max(d - 0.35, 0.1));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20, justifyContent: "center", height: H }}>
      {msgs.map((m, k) => {
        const me = m.from === "me", p = pr(u, at(0.1 + k * 0.28), 0.3, "back.out(1.8)");
        return (
          <div key={k} style={{ maxWidth: 640, padding: "22px 32px", borderRadius: 38, fontSize: 38, fontWeight: 700, lineHeight: 1.2, alignSelf: me ? "flex-end" : "flex-start",
            background: me ? "linear-gradient(135deg,var(--ta),var(--tb))" : "#eceaf6", color: INK, [me ? "borderBottomRightRadius" : "borderBottomLeftRadius"]: 10,
            opacity: pr(u, at(0.1 + k * 0.28), 0.3, "power1.out"), transform: `translateY(${30 * (1 - p)}px) scale(${0.85 + 0.15 * p})`, transformOrigin: `${me ? "100%" : "0%"} 100%` }}>{clip(m.text, 46)}</div>
        );
      })}
      {msgs.length < 3 && u > at(0.1 + msgs.length * 0.28) + 0.4 && (
        <div style={{ alignSelf: msgs[msgs.length - 1]?.from === "me" ? "flex-start" : "flex-end", padding: "20px 30px", borderRadius: 34, background: "#eceaf6", display: "flex", gap: 8 }}>
          {[0, 1, 2].map((k) => <i key={k} style={{ width: 14, height: 14, borderRadius: 7, background: "#9a96b8", display: "block", transform: `translateY(${-6 * Math.max(0, Math.sin(u * 8 - k))}px)` }} />)}
        </div>
      )}
    </div>
  );
};

const Dots: React.FC<B> = ({ w, i, u, d }) => {
  const a = Math.trunc(num(w.from, 8000000000)), b = Math.trunc(num(w.to, 1));
  const at = (f: number) => Math.min(f * d, Math.max(d - 0.35, 0.1));
  const order = Array.from({ length: 144 }, (_, k) => k).sort((x, y) => rndn(x, i + 11) - rndn(y, i + 11));
  const rank = new Map(order.map((idx, n) => [idx, n]));
  const ch = pr(u, at(0.6), 0.45, "back.out(2)");
  return (
    <>
      <svg viewBox="0 0 800 210" style={{ width: W, height: 176, display: "block" }}>
        {Array.from({ length: 144 }, (_, k) => {
          const r = Math.floor(k / 24), c = k % 24;
          return <circle key={k} cx={20 + c * 33} cy={20 + r * 33} r={7} fill="#b9b4d6" opacity={(1 - pr(u, 0.25 + ((rank.get(k) ?? 0) / 144) * d * 0.5, 0.25, "power1.out")) * (0.8 + 0.2 * Math.sin(u * 3 + k))} />;
        })}
      </svg>
      <div style={{ position: "absolute", left: 350, top: 28, width: 120, height: 120, borderRadius: 60, background: "#ff6b9d", color: INK, fontSize: 36, fontWeight: 900, display: "flex", alignItems: "center", justifyContent: "center", opacity: ch, transform: `scale(${(0.3 + 0.7 * ch) * (1 + 0.07 * Math.sin(u * 5) * ch)})` }}>{clip(w.chosen ?? "Она", 8)}</div>
      <div style={{ textAlign: "center", fontSize: 28, fontWeight: 700, color: GREY, marginTop: 2 }}>{clip(w.label, 30)}</div>
      <div style={{ textAlign: "center", fontSize: 72, fontWeight: 900, color: INK, lineHeight: 1.05 }}>{fmtNum(ft(u, 0.2, d * 0.6, a, b, "power3.out"))}</div>
      <div style={{ textAlign: "center", fontSize: 28, fontWeight: 700, color: GREY }}>{clip(w.sub, 30)}</div>
    </>
  );
};

const Draw: React.FC<B & { motion?: string }> = ({ w, i, u, d }) => {
  const ref = useRef<SVGSVGElement>(null);
  const frames = (w.frames as string[]) ?? [];
  const step = Math.min(1.8, d / Math.max(frames.length, 1));
  const at = (f: number) => Math.min(f * d, Math.max(d - 0.35, 0.1));
  useLayoutEffect(() => {
    const r = ref.current;
    if (!r) return;
    frames.forEach((_, k) => {
      const t = k * step;
      const sc = ft(u, t, step + 0.3, 1, 1.06);
      const op = (k ? pr(u, t, 0.3, "power1.inOut") : 1) * (k + 1 < frames.length ? 1 - pr(u, (k + 1) * step, 0.3, "power1.inOut") : 1);
      put(r.querySelector(`#df${i}_${k}`), { scale: sc, o: op });
    });
    if (w.anim) applyTweens(r as unknown as HTMLElement, `dr${i}_`, (w.tw as any) ?? [], u);
    else {
      const e = r.querySelector<SVGElement>(`#dr${i}`);
      const p = yoyo(u, 0, 1.1);
      const m = w.motion;
      if (e) put(e, m === "pulse" ? { scale: 0.97 + 0.07 * p } : m === "sway" ? { rot: -3 + 6 * p } : m === "drift" ? { x: -18 + 36 * p } : { y: 8 - 18 * p });
    }
  });
  const markup = frames.map((m, k) => `<g id="df${i}_${k}" style="transform-origin:400px 210px">${m}</g>`).join("");
  return (
    <div style={wrap}>
      <svg ref={ref} viewBox="0 0 800 420" preserveAspectRatio="xMidYMid slice" style={{ width: W, height: H, display: "block", borderRadius: 30, overflow: "hidden" }}>
        <g id={`dr${i}`} style={{ transformOrigin: "400px 210px" }} dangerouslySetInnerHTML={{ __html: markup }} />
      </svg>
      {w.big && <div style={{ position: "absolute", right: 22, top: 18, padding: "6px 26px", borderRadius: 30, background: "#fff", fontSize: 54, fontWeight: 900, color: INK, whiteSpace: "nowrap", opacity: pr(u, at(0.3), 0.4, "back.out(1.8)"), transform: `translateY(${-20 * (1 - pr(u, at(0.3), 0.4, "back.out(1.8)"))}px)` }}>{clip(w.big, 12)}</div>}
      {(w.chips as string[] | undefined)?.length ? (
        <div style={{ position: "absolute", left: 22, bottom: 18, display: "flex", gap: 12, opacity: pr(u, at(0.55), 0.4, "power2.out"), transform: `translateY(${24 * (1 - pr(u, at(0.55), 0.4, "power2.out"))}px)` }}>
          {(w.chips as string[]).slice(0, 2).filter(Boolean).map((c, k) => <span key={k} style={{ padding: "8px 22px", borderRadius: 26, background: "#fff", fontSize: 28, fontWeight: 700, color: INK, whiteSpace: "nowrap" }}>{clip(c, 22)}</span>)}
        </div>
      ) : null}
    </div>
  );
};

const Versus: React.FC<B> = ({ w, i, u, d }) => {
  const keys = [ARTS[w.art] ? w.art : "sunset", ARTS[w.art2] ? w.art2 : "rain"];
  const labs = [w.label ?? "", w.label2 ?? ""];
  const at = (f: number) => Math.min(f * d, Math.max(d - 0.35, 0.1));
  return (
    <div style={wrap}>
      {keys.map((key, side) => {
        const t0 = at(side ? 0.28 : 0.02), p = pr(u, t0, 0.4, "back.out(1.6)");
        return (
          <div key={side} style={{ position: "absolute", left: side * 420, top: 0, width: 400, height: H, opacity: pr(u, t0, 0.4, "power1.out"), transform: `translateX(${(side ? 60 : -60) * (1 - p)}px) scale(${0.92 + 0.08 * p})` }}>
            <ArtSvg art={key} uid={1000 + i * 2 + side} u={u} d={d} style={{ width: 400, height: 270, borderRadius: 26 }} />
            <div style={{ marginTop: 14, textAlign: "center", fontWeight: 800, fontSize: 30, color: INK }}>{clip(labs[side], 20)}</div>
          </div>
        );
      })}
    </div>
  );
};

const Scene: React.FC<B> = ({ w, i, u, d }) => {
  const art = ARTS[w.art] ? w.art : "sunset";
  const at = (f: number) => Math.min(f * d, Math.max(d - 0.35, 0.1));
  const big = w.big;
  const em = ["crown", "heart", "star"].includes(w.emblem) ? w.emblem : null;
  const ep = pr(u, at(0.18), 0.5, "bounce.out"), pp = pr(u, at(0.5), 0.35, "back.out(2)");
  return (
    <div style={wrap}>
      <ArtSvg art={art} uid={i} u={u} d={d} style={{ width: W, height: H, borderRadius: 30 }} />
      {big && <div style={{ position: "absolute", left: 30, top: 20, fontSize: 84, fontWeight: 900, textShadow: "0 4px 18px rgba(0,0,0,.35)", ...(DARK_ARTS.has(art) ? { color: "#fff" } : { color: INK, textShadow: "0 4px 18px rgba(255,255,255,.7)" }) }}>{clip(big, 8)}</div>}
      {em && (
        <svg viewBox="0 0 100 100" style={{ position: "absolute", left: big ? 600 : 310, top: big ? 70 : 50, width: big ? 170 : 200, height: big ? 170 : 200, opacity: pr(u, at(0.18), 0.1), transform: `translateY(${-60 * (1 - ep)}px) rotate(${-14 * (1 - ep)}deg) scale(${0.6 + 0.4 * ep})` }}>
          {em === "crown" ? <><path d="M10 78L16 30L38 52L50 18L62 52L84 30L90 78Z" fill="#ffc83d" stroke="#e59a00" strokeWidth={3} strokeLinejoin="round" /><circle cx={50} cy={62} r={6} fill="#ff4f6d" /><circle cx={28} cy={64} r={4.5} fill="#3b8bff" /><circle cx={72} cy={64} r={4.5} fill="#3bd18a" /></>
            : em === "heart" ? <path transform="translate(8 8) scale(3.5)" d={HEART} fill="#ff4f6d" />
            : <path d="M50 8l12 28 30 3-23 20 7 30-26-16-26 16 7-30L8 39l30-3z" fill="#ffc83d" stroke="#e59a00" strokeWidth={3} strokeLinejoin="round" />}
        </svg>
      )}
      {w.pill && (
        <div style={{ position: "absolute", left: "50%", bottom: 22, marginLeft: -190, width: 380, height: 64, borderRadius: 32, background: "#fff", display: "flex", alignItems: "center", justifyContent: "center", gap: 12, fontSize: 30, fontWeight: 800, color: INK, whiteSpace: "nowrap", opacity: pr(u, at(0.5), 0.35, "power1.out"), transform: `translateY(${30 * (1 - pp)}px) scale(${0.8 + 0.2 * pp})` }}>
          <i style={{ width: 14, height: 14, borderRadius: 7, background: "#ff4f6d", display: "block" }} />{clip(w.pill, 24)}
        </div>
      )}
    </div>
  );
};

const Pair: React.FC<B> = ({ w, i, u, d }) => {
  const at = (f: number) => Math.min(f * d, Math.max(d - 0.35, 0.1));
  const a = clip(w.a ?? "Я", 5), b = clip(w.b ?? "Ты", 5);
  const pa = pr(u, at(0.1), 0.35, "back.out(2)"), pb = pr(u, at(0.7), 0.35, "back.out(2)");
  const cyc = u < at(0.3) ? 0 : ((u - at(0.3)) / 1.4) % 1, hx = 240 * pr(cyc, 0, 1, "power1.inOut"), ho = u < at(0.3) ? 0 : 1 - pr(cyc, 0.88, 0.12), br = 0.04 * Math.sin(u * 4);
  return (
    <div style={wrap}>
      <svg viewBox="0 0 820 340" style={abs}>
        <defs>
          <radialGradient id={`pa${i}`}><stop offset="0" stopColor="#ffc79a" /><stop offset="1" stopColor="#ff7a3d" /></radialGradient>
          <radialGradient id={`pb${i}`}><stop offset="0" stopColor="#ffa6c4" /><stop offset="1" stopColor="#ff4f8b" /></radialGradient>
        </defs>
        <path d="M262 150H558" stroke="#8a6bff" strokeWidth={6} strokeDasharray="2 16" strokeLinecap="round" fill="none" />
        <g style={{ transformOrigin: "150px 150px", opacity: 0.4 + 0.6 * pa, transform: `scale(${0.88 + 0.17 * pa + br})` }}><circle cx={150} cy={150} r={100} fill={`url(#pa${i})`} /><text x={150} y={176} textAnchor="middle" fontSize={76} fontWeight={900} fill={INK}>{a}</text></g>
        <g style={{ transformOrigin: "670px 670px" }} />
        <g style={{ transformOrigin: "670px 150px", opacity: 0.4 + 0.6 * pb, transform: `scale(${0.88 + 0.17 * pb - br})` }}><circle cx={670} cy={150} r={100} fill={`url(#pb${i})`} /><text x={670} y={176} textAnchor="middle" fontSize={76} fontWeight={900} fill={INK}>{b}</text></g>
        <g opacity={ho} style={{ transform: `translateX(${hx}px)` }}>{heart(264, 124, 2.2)}</g>
      </svg>
      <Cap label={w.label} />
    </div>
  );
};

const Pulse: React.FC<B> = ({ w, i, u, d }) => {
  const a = num(w.from, 70), b = num(w.to, 130);
  const ecg = "M0 250H150L185 250L215 215L250 285L285 228L310 250H470L505 250L535 215L570 285L605 228L630 250H820";
  return (
    <div style={wrap}>
      <svg viewBox="0 0 820 340" style={abs}>
        <path d={ecg} pathLength={1} stroke="#ff4f6d" strokeWidth={9} fill="none" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="1" strokeDashoffset={ft(u, 0.05, d * 0.6, 1, 0)} />
        <path d={ecg} pathLength={1} stroke="#fff" strokeWidth={9} fill="none" strokeLinecap="round" strokeDasharray="0.1 1" strokeDashoffset={-((u * 0.8) % 1) + 0.1} opacity={0.85 * pr(u, d * 0.6, 0.3)} />
        <g style={{ transformOrigin: "190px 110px", transform: `scale(${1 + 0.16 * yoyo(u, 0, 0.2)})` }}>{heart(106, 26, 7)}</g>
      </svg>
      <div style={{ position: "absolute", left: 420, top: 26, fontSize: 140, fontWeight: 900, lineHeight: 1, color: INK }}>{Math.round(ft(u, 0, d * 0.85, Math.trunc(a), Math.trunc(b), "power2.out"))}</div>
      <div style={{ position: "absolute", left: 428, top: 176, fontSize: 34, fontWeight: 800, color: "#8a6bff" }}>{clip(w.unit ?? "уд/мин", 8)}</div>
      <Cap label={w.label} />
      <i style={{ display: "none" }}>{i}</i>
    </div>
  );
};

const Route: React.FC<B> = ({ w, i, u, d }) => {
  const at = (f: number) => Math.min(f * d, Math.max(d - 0.35, 0.1));
  const path = useRef<SVGPathElement>(null), dot = useRef<SVGCircleElement>(null);
  useLayoutEffect(() => { // a car keeps driving the finished route, there and again
    const p = path.current, c = dot.current;
    if (!p || !c) return;
    const k = u < at(0.62) ? 0 : ((u - at(0.62)) * 0.45) % 1, pt = p.getPointAtLength(p.getTotalLength() * k);
    c.setAttribute("cx", String(pt.x)); c.setAttribute("cy", String(pt.y)); c.style.opacity = u < at(0.62) ? "0" : "1";
  });
  const A = clip(w.from ?? "Старт", 12), Bn = clip(w.to ?? "Цель", 12);
  const wa = 34 + 17 * A.length, wb = 34 + 17 * Bn.length;
  const pin = (x: number, y: number, col: string, p: number) => (
    <g opacity={p} transform={`translate(${x} ${y - 60 * (1 - p)})`}><path d="M0 0C-28 -36 -28 -76 0 -76C28 -76 28 -36 0 0Z" fill={col} /><circle cx={0} cy={-50} r={11} fill="#fff" /></g>
  );
  const lab = (x: number, y: number, wd: number, txt: string, p: number) => (
    <g opacity={p} transform={`translate(0 ${10 * (1 - p)})`}><rect x={x - Math.floor(wd / 2)} y={y} width={wd} height={46} rx={23} fill="#fff" stroke="#dcd8ee" strokeWidth={2} /><text x={x} y={y + 32} textAnchor="middle" fontSize={26} fontWeight={800} fill={INK}>{txt}</text></g>
  );
  return (
    <div style={wrap}>
      <svg viewBox="0 0 820 340" style={abs}>
        <rect width={820} height={340} fill="#e8eefc" /><path d="M0 225C200 180 400 265 820 190" stroke="#bcd4f5" strokeWidth={46} fill="none" />
        <rect x={470} y={232} width={150} height={80} rx={22} fill="#cdecd0" />
        {["M0 96H820", "M0 312H820", "M205 0V340", "M565 0V340"].map((p) => <path key={p} d={p} stroke="#fff" strokeWidth={10} />)}
        <path ref={path} d="M130 252C250 252 300 130 440 150S600 122 660 112" pathLength={1} stroke="#3b82f6" strokeWidth={13} fill="none" strokeLinecap="round" strokeDasharray="1" strokeDashoffset={ft(u, at(0.12), d * 0.5, 1, 0, "power1.inOut")} />
        <circle ref={dot} r={13} fill="#fff" stroke="#3b82f6" strokeWidth={6} />
        {pin(130, 252, "#ff4f6d", pr(u, 0.05, 0.45, "bounce.out"))}{lab(130, 128, wa, A, pr(u, 0.2, 0.3, "power1.out"))}
        {pin(660, 112, "#ff8a2d", pr(u, at(0.62), 0.45, "bounce.out"))}{lab(660, 128, wb, Bn, pr(u, at(0.7), 0.3, "power1.out"))}
      </svg>
      <i style={{ display: "none" }}>{i}</i>
    </div>
  );
};

const Venn: React.FC<B> = ({ w, u, d }) => {
  const at = (f: number) => Math.min(f * d, Math.max(d - 0.35, 0.1));
  const a = Math.trunc(num(w.from, 1)), b = Math.trunc(num(w.to, 3)), sh = Math.trunc(num(w.shift, 110));
  const hp = pr(u, at(0.62), 0.4, "back.out(2.2)");
  const k = ft(u, at(0.5), d * 0.35, a, b);
  return (
    <div style={wrap}>
      <svg viewBox="0 0 820 340" style={abs}>
        <g style={{ transform: `translateX(${ft(u, 0.15, d * 0.5, 0, sh, "power2.inOut") + 12 * Math.sin(u * 2.2)}px)` }}><circle cx={230} cy={170} r={120} fill="#ff9a6b" opacity={0.92} /></g>
        <g style={{ transform: `translateX(${ft(u, 0.15, d * 0.5, 0, -sh, "power2.inOut") - 12 * Math.sin(u * 2.2)}px)` }}><circle cx={590} cy={170} r={120} fill="#ff4f8b" opacity={0.82} /></g>
        <g style={{ transformOrigin: "410px 170px", opacity: hp, transform: `scale(${(0.3 + 0.7 * hp) * (1 + 0.08 * Math.sin(u * 6) * hp)})` }}>{heart(366, 126, 3.7, "#fff")}</g>
      </svg>
      <div style={{ position: "absolute", right: 24, top: 10, fontSize: 64, fontWeight: 900, color: "#ff4f6d", lineHeight: 1 }}>×{Math.round(k)}</div>
      <Cap label={w.label} />
    </div>
  );
};

const Ring: React.FC<B> = ({ w, u, d }) => {
  const a = num(w.from, 0), b = num(w.to, 100);
  const v = ft(u, 0.1, d * 0.7, a, b, "power2.out");
  return (
    <div style={wrap}>
      <svg viewBox="0 0 820 340" style={abs}>
        <g transform="rotate(-90 410 150)" style={{ transformOrigin: "410px 150px", transform: `rotate(-90deg) scale(${1 + 0.035 * Math.sin(u * 4)})` }}>
          <circle cx={410} cy={150} r={115} pathLength={100} fill="none" stroke="#f1e6d6" strokeWidth={30} />
          <circle cx={410} cy={150} r={115} pathLength={100} fill="none" stroke="#ff9f1a" strokeWidth={30} strokeLinecap="round" strokeDasharray="100" strokeDashoffset={100 - v} />
        </g>
      </svg>
      <div style={{ position: "absolute", left: 0, top: 96, width: W, textAlign: "center", fontSize: 84, fontWeight: 900, lineHeight: 1, color: INK }}>{Math.round(v)}%</div>
      <Cap label={w.label} />
    </div>
  );
};

const Thermo: React.FC<B> = ({ w, u, d }) => {
  const a = num(w.from, 36.6), b = num(w.to, 38.9);
  return (
    <div style={wrap}>
      <svg viewBox="0 0 820 340" style={abs}>
        <rect x={212} y={18} width={58} height={236} rx={29} fill="#ece6f7" /><circle cx={241} cy={272} r={44 + 3 * Math.sin(u * 6)} fill="#ff4f6d" />
        <rect x={223} y={52} width={36} height={220} rx={18} fill="#ff4f6d" style={{ transformOrigin: "241px 270px", transform: `scaleY(${ft(u, 0.1, d * 0.7, 0.25, 1, "power2.out") * (1 + 0.012 * Math.sin(u * 9))})` }} />
        {[0, 1, 2, 3].map((k) => <path key={k} d={`M${440 + k * 52} 270v22M${429 + k * 52} 281h22`} stroke="#4a8bff" strokeWidth={5} strokeLinecap="round" transform={`translate(0 ${-8 * Math.abs(Math.sin(u * 2.4 + k))})`} />)}
      </svg>
      <div style={{ position: "absolute", left: 330, top: 70, fontSize: 132, fontWeight: 900, lineHeight: 1, color: INK }}>
        <span>{ft(u, 0.1, d * 0.7, a, b, "power2.out").toFixed(1)}</span><small style={{ fontSize: 60, color: "#ff4f6d" }}>{clip(w.unit ?? "°", 3)}</small>
      </div>
      <Cap label={w.label} />
    </div>
  );
};

const Alert: React.FC<B> = ({ w, u, d }) => {
  const at = (f: number) => Math.min(f * d, Math.max(d - 0.35, 0.1));
  const word = clip(String(w.word ?? "ОПАСНО").toUpperCase(), 14);
  const p = pr(u, at(0.25), 0.4, "back.out(2)");
  const shake = -7 + 14 * yoyo(u, 0.1, 0.07, "none");
  const g = 0.8 + 0.8 * yoyo(u, 0, 0.5);
  return (
    <div style={wrap}>
      <div style={{ position: "absolute", left: 0, top: 10, width: W, textAlign: "center", fontSize: 68, fontWeight: 900, lineHeight: 1.1, color: "#ff3b3b", opacity: pr(u, at(0.25), 0.4, "power1.out"), transform: `scale(${1.9 - 0.9 * p})` }}>{word}</div>
      <svg viewBox="0 0 820 340" style={abs}>
        <circle cx={410} cy={200} r={90} fill="#ff4f3d" opacity={0.16} style={{ transformOrigin: "410px 200px", transform: `scale(${g})` }} />
        <g style={{ transformOrigin: "410px 200px", transform: `translateX(${shake}px)` }}>
          <path d="M410 118L486 244H334Z" fill="#ff4f3d" stroke="#ff4f3d" strokeWidth={16} strokeLinejoin="round" />
          <text x={410} y={230} textAnchor="middle" fontSize={80} fontWeight={900} fill="#fff">!</text>
        </g>
      </svg>
      <div style={{ position: "absolute", left: 0, top: 284, width: W, height: 36, borderRadius: 18, background: "repeating-linear-gradient(-45deg,#14141f 0 18px,#ffd400 18px 36px)" }} />
    </div>
  );
};

const Target: React.FC<B> = ({ w, u, d }) => {
  const at = (f: number) => Math.min(f * d, Math.max(d - 0.35, 0.1));
  const lab = clip(String(w.label ?? "ЦЕЛЬ НАЙДЕНА").toUpperCase(), 20);
  const p = pr(u, 0.1, 0.55, "power3.out");
  return (
    <div style={wrap}>
      <div style={{ ...abs, background: "#15111f" }} /><div style={{ ...abs, background: "#ff1744", opacity: 0.4 * pr(u, at(0.6), 0.4) + 0.25 * Math.max(0, Math.sin(u * 5)) * p }} />
      <svg viewBox="0 0 820 340" style={abs}>
        <g style={{ transformOrigin: "410px 170px", opacity: p, transform: `scale(${2.4 - 1.4 * p}) rotate(${120 * (1 - p) + u * 25 * p}deg)` }}>
          <circle cx={410} cy={170} r={96} fill="none" stroke="#fff" strokeWidth={6} />
          {["M410 36V104", "M410 236V304", "M276 170H344", "M476 170H544"].map((q) => <path key={q} d={q} stroke="#fff" strokeWidth={6} strokeLinecap="round" />)}
        </g>
        <g style={{ transformOrigin: "410px 170px", transform: `scale(${1 + 0.18 * yoyo(u, 0.3, 0.18)})` }}><circle cx={410} cy={170} r={30} fill="#ff1744" /><circle cx={410} cy={170} r={11} fill="#fff" /></g>
      </svg>
      <div style={{ position: "absolute", left: 28, bottom: 22, fontSize: 28, fontWeight: 800, color: "#fff", letterSpacing: 1 }}>{lab}</div>
    </div>
  );
};

const Polaroid: React.FC<B> = ({ w, u, d }) => {
  const a = Math.trunc(num(w.from, 2023)), b = Math.trunc(num(w.to, 2026));
  const p = pr(u, 0.05, 0.5, "back.out(1.6)");
  return (
    <div style={wrap}>
      <svg viewBox="0 0 820 340" style={abs}>
        <g style={{ transformOrigin: "165px 170px", opacity: pr(u, 0.05, 0.5, "power1.out"), transform: `rotate(${-14 + 9 * p + 4 * Math.sin(u * 2.2) * p}deg) scale(${0.8 + 0.2 * p})` }}>
          <rect x={40} y={16} width={250} height={308} rx={16} fill="#fff" stroke="#e6e1f5" strokeWidth={3} />
          <rect x={58} y={34} width={214} height={226} rx={9} fill="#2b2b4a" /><circle cx={165} cy={124} r={40} fill="#8c8cb8" /><path d="M92 260Q165 160 238 260Z" fill="#8c8cb8" />
        </g>
      </svg>
      <div style={{ position: "absolute", left: 360, top: 70, fontSize: 124, fontWeight: 900, lineHeight: 1, color: "#c2410c" }}>{Math.round(ft(u, 0.15, d * 0.7, a, b, "power1.inOut"))}</div>
      <div style={{ position: "absolute", left: 368, top: 206, fontSize: 38, fontWeight: 700, color: GREY }}>{clip(w.label ?? "", 22)}</div>
    </div>
  );
};

const KINDS: Record<string, React.FC<B>> = { counter: Counter, search: Search, camera: Camera, chat: Chat, dots: Dots, draw: Draw, versus: Versus, scene: Scene, pair: Pair, pulse: Pulse, route: Route, venn: Venn, ring: Ring, thermo: Thermo, alert: Alert, target: Target, polaroid: Polaroid, ...SCENES };

export const Body: React.FC<B & { kind: string }> = ({ kind, ...p }) => {
  const K = KINDS[kind] ?? Scene;
  return <K {...p} />;
};
