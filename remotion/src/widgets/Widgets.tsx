import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { loadFont } from "@remotion/google-fonts/Montserrat";
import { Body } from "./Bodies";
import { ft, pr, yoyo } from "./anim";
import type { Scene, WidgetsProps } from "./types";

const { fontFamily } = loadFont("normal", { weights: ["600", "700", "800", "900"], subsets: ["cyrillic", "latin"] });

// The phone-UI "widgets" edit: 1080x1080 stage in the middle of 1080x1920, black bars are TikTok safe zones.
// Layout numbers mirror the retired HyperFrames template, so docs/widgets-template.md still describes what is on screen.
const INK = "#14141f";
const COLS = ["#ff6b9d", "#6aa8ff", "#7be0a8", "#ffc15a", "#b58cff"];
const CARD_TOP = 180, CARD_ZOOM = 1.04, CAP_H = 84, CARD_H = 478;
const BODY_X = 130;
const ANCH: Record<string, [number, number]> = { pair: [410, 150], pulse: [190, 110], route: [660, 60], venn: [410, 170], ring: [410, 150], thermo: [241, 272], alert: [410, 190], target: [410, 170], polaroid: [165, 150], versus: [200, 130], counter: [170, 170], search: [410, 45], camera: [410, 170], chat: [200, 170], dots: [410, 88], scene: [410, 170], draw: [410, 170] };
const GLYPH: Record<string, string> = {
  bubble: "M4 5h16v11H9l-5 4z", heart: "M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z",
  pin: "M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5z", lines: "M5 6h14M5 12h14M5 18h9", bell: "M12 3a6 6 0 0 0-6 6v4l-2 3h16l-2-3V9a6 6 0 0 0-6-6zm-2 15a2 2 0 0 0 4 0z",
};
// a "pop" every 1.1 s of the card's life: popAge = seconds since the last one (-1 before the first), pop = its size 0..1
const PERIOD = 1.1;
const popAge = (u: number, from: number) => (u < from ? -1 : (u - from) % PERIOD);
const pop = (u: number, from: number) => { const k = popAge(u, from); return k < 0 || k > 0.3 ? 0 : Math.sin((Math.PI * k) / 0.3); };
const rnd = (i: number, k = 0) => { const x = Math.sin(i * 127.1 + k * 311.7) * 43758.5453; return x - Math.floor(x); };
const ri = (i: number, k: number, a: number, b: number) => a + rnd(i, k) * (b - a);

const Note: React.FC<{ size: number }> = ({ size }) => (
  <svg viewBox="0 0 24 24" width={size} height={size}><path d="M9 18V6l10-2v12" stroke="#fff" strokeWidth={2} fill="none" strokeLinecap="round" /><circle cx={7} cy={18} r={3} fill="#fff" /><circle cx={17} cy={16} r={3} fill="#fff" /></svg>
);
const Cross: React.FC<{ x: number; y: number; s: number; col: string; o: number; rot: number }> = ({ x, y, s, col, o, rot }) => (
  <svg viewBox="0 0 10 10" style={{ position: "absolute", left: x, top: y, width: s, height: s, opacity: o, transform: `rotate(${rot}deg)` }}><path d="M5 1v8M1 5h8" stroke={col} strokeWidth={2} strokeLinecap="round" /></svg>
);

const Frame: React.FC<WidgetsProps & { t: number }> = (p) => {
  const t = p.t;
  const W = p.width, SQ = W, OY = (p.height - SQ) / 2;
  const { ta, tb, acc } = p.pal;
  const lyric = p.scenes.filter((s) => s.role !== "outro");
  const ost = p.ostart, dur = p.duration;
  const hasCap = p.hasCap;
  const cardH = CARD_H + (hasCap ? CAP_H : 0);

  // theme: base look, every second card flips light <-> dark (short cut, no cross-fade), the end card is back to the base
  const flips: [number, boolean][] = [];
  if (p.alternate) {
    let cur = false;
    lyric.forEach((s, k) => { const want = k % 2 === 1; if (want !== cur) { flips.push([s.start, want]); cur = want; } });
    if (cur) flips.push([ost, false]);
  }
  const alt = flips.reduce((m, [tf, on]) => (t >= Math.max(0, tf - 0.1) + 0.06 ? on : m), false);
  const lightText = p.dark !== alt; // true = light text on a dark stage
  const TX = lightText ? "#f6f2ff" : INK, TX2 = lightText ? "#cfc8ee" : "#5f5a7c", TRK = lightText ? "rgba(255,255,255,.28)" : "rgba(20,20,31,.15)";
  const TXF = p.dark ? "#ffffff" : p.pal.taReadable, TXS = p.dark ? `0 0 34px ${ta}` : "0 6px 24px rgba(255,255,255,.8)";
  const altOn = alt ? 1 : 0;

  // ---------- chrome ----------
  const cd = ost;
  const chromeY = t >= Math.max(0.5, ost - 0.3) ? ft(t, Math.max(0.5, ost - 0.3), 0.3, 0, -24, "power2.in") : ft(t, 0, 0.4, -24, 0, "power3.out");
  const chromeOn = t < Math.max(0.5, ost - 0.3) + 0.3;
  const clock = Math.min(t, cd);
  const mm = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
  const notifs = lyric.map((s) => {
    const bn = s.notify, tbn = s.start + 0.3, bdur = Math.min(1.9, s.end + 0.3 - tbn);
    if (!bn || bdur < 0.9) return null;
    const te2 = tbn + bdur - 0.5;
    const nc = ft(t, tbn + 0.3, 0.2, 0, 1) * (1 - pr(t, te2, 0.15));
    return t >= tbn && t < tbn + bdur + 0.2 ? { s, nc, isc: t < te2 + 0.3 ? 1 - pr(t, tbn, 0.15) : pr(t, te2 + 0.3, 0.2) } : null;
  }).filter(Boolean) as { s: Scene; nc: number; isc: number }[];
  const isc = notifs.length ? Math.min(...notifs.map((n) => n.isc)) : 1;

  // ---------- one card ----------
  const card = (s: Scene, idx: number) => {
    const beforeOutro = idx + 1 < p.scenes.length && p.scenes[idx + 1].role === "outro";
    const first = idx === 0, u = t - s.start + (first ? 0.9 : 0), d = s.end - s.start;
    const life = Math.min(d + 0.6, dur - s.start);
    if (t < s.start || u > life + (first ? 0.9 : 0) || d <= 0) return null;
    const e = first ? 1 : pr(t, s.start, 0.6, "power3.out");
    let op = 1, sc = 0.92 + 0.08 * e, y = 150 * (1 - e), x = -40 * (1 - e), rot = -5 * (1 - e), rx = -12 * (1 - e), blur = 10 * (1 - e);
    if (beforeOutro) {
      const te = Math.max(s.end - 0.35, s.start + 0.5), k = pr(t, te, 0.35, "power3.in");
      sc = sc * (1 - k) + 0.08 * k; op = 1 - k; blur = blur * (1 - k) + 6 * k;
    } else {
      const te = Math.max(s.end, s.start + 0.5), k = pr(t, te, 0.4, "power2.out");
      op = 1 - 0.5 * k; sc = sc * (1 - k) + 0.93 * k; y = y * (1 - k) + -18 * k; blur = blur * (1 - k) + 5 * k;
      if (t > te + 0.4) op = 0.5 * (1 - pr(t, te + 0.4, 0.2));
    }
    // slow sway of the whole card
    let cur = 0, sg = idx % 2 === 0 ? 1 : -1, tgt = 0, from = 0;
    if (t >= s.start + 0.6) {
      const n = Math.floor((t - s.start - 0.6) / 2.6);
      for (let k = 0; k <= n; k++) { from = cur; tgt = sg * (4 + (k % 3)); if (k < n) cur = tgt; sg = -sg; }
      cur = from + (tgt - from) * pr(t, s.start + 0.6 + n * 2.6, 2.6, "sine.inOut");
    }
    const sweepT = (() => { for (let ts = s.start + 0.7; ts < s.end - 0.3; ts += 2.2) if (t >= ts && t <= ts + 0.9) return t - ts; return -1; })();
    const text = s.text.length > 100 ? s.text.slice(0, 99) + "…" : s.text;
    const cap = s.w.cap ? String(s.w.cap).slice(0, 26) : "";
    return (
      <div key={`c${s.i}`} style={{ position: "absolute", left: 90, top: CARD_TOP, width: 900, height: cardH + 40, opacity: op, filter: `blur(${blur}px)`, zIndex: 3,
        transformOrigin: "50% 30%", transform: `perspective(900px) translate(${x}px, ${y}px) rotateX(${rx}deg) rotate(${rot}deg) scale(${sc})` }}>
        <div style={{ position: "absolute", left: 0, top: 0, width: 900, height: cardH + 40, transform: `scale(${CARD_ZOOM}) perspective(900px) rotateY(${cur}deg) rotate(${cur * 0.2}deg)` }}>
          <div style={{ position: "absolute", left: 0, top: 0, width: 900, height: cardH, boxSizing: "border-box", padding: "30px 40px", borderRadius: 60, background: "rgba(255,255,255,.96)", boxShadow: "0 24px 60px rgba(90,70,160,.22)", display: "flex", flexDirection: "column" }}>
            <div style={{ position: "absolute", inset: 0, borderRadius: 60, overflow: "hidden", pointerEvents: "none" }}>
              <i style={{ position: "absolute", top: -50, left: -260, width: 160, height: 760, background: "linear-gradient(90deg,rgba(255,255,255,0),rgba(190,170,255,.35),rgba(255,255,255,0))", transform: `translateX(${sweepT < 0 ? 0 : 1300 * pr(sweepT, 0, 0.9, "power1.inOut")}px) skewX(-20deg)`, opacity: sweepT < 0 ? 0 : 1 }} />
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 18, height: 64 }}>
              <span style={{ width: 56, height: 56, borderRadius: 16, background: s.icon, display: "inline-block", flex: "none" }} />
              <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.1 }}>
                <b style={{ fontSize: 36, fontWeight: 800, color: INK }}>{s.app.slice(0, 20)}</b>
                {s.cat && <em style={{ fontStyle: "normal", fontSize: 22, fontWeight: 700, color: "#7a5cff" }}>{s.cat.slice(0, 22)}</em>}
              </div>
            </div>
            <div style={{ position: "relative", width: 820, height: 340, marginTop: 14, borderRadius: 36, overflow: "hidden",
              transform: `translateY(${6 * yoyo(t, s.start + 0.5, 1.1)}px) rotate(${0.9 * Math.sin(u * 1.7 + s.i)}deg) scale(${1 + 0.045 * pr(u, 0, d, "none") + pop(u, 0.6) * 0.04})` }}>
              <Body kind={s.kind} w={s.w} i={s.i} u={u} d={d} text={text} ta={ta} tb={tb} acc={acc} taReadable={p.pal.taReadable} />
            </div>
            {Array.from({ length: 6 }, (_, q) => { const k = popAge(u, 0.6); if (k < 0 || k > 0.5) return null; const a = (q / 6) * 6.283 + s.i; const r = 330 + 160 * (k / 0.5);
              return <Cross key={`p${q}`} x={410 + Math.cos(a) * r * 1.05} y={250 + Math.sin(a) * r * 0.45} s={26} col={COLS[(q + s.i) % 5]} o={1 - k / 0.5} rot={q * 40 + 160 * k} />; })}
            {hasCap && <div style={{ height: CAP_H - 14, marginTop: 14, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 42, fontWeight: 800, color: INK, whiteSpace: "nowrap", opacity: pr(u, 0.55, 0.4, "power2.out"), transform: `translateY(${12 * (1 - pr(u, 0.55, 0.4, "power2.out"))}px)` }}>{cap}</div>}
          </div>
          <div style={{ position: "absolute", left: 0, top: cardH + 16, width: 900, display: "flex", justifyContent: "center", gap: 14 }}>
            {Array.from({ length: p.nCards }, (_, q) => <i key={q} style={{ width: q === Math.min(s.i, p.nCards - 1) ? 34 : 14, height: 14, borderRadius: 7, background: q === Math.min(s.i, p.nCards - 1) ? TX : "#b9b4d6", display: "block" }} />)}
          </div>
        </div>
      </div>
    );
  };

  // glowing orbs that fly from the previous card's key object to this card's
  const bodyY = CARD_TOP + 30 + 64 + 14, cy0 = CARD_TOP + (cardH + 40) / 2;
  const anchor = (k: string) => { const [ax, ay] = ANCH[k] ?? [410, 170]; return [540 + (BODY_X + ax - 540) * CARD_ZOOM, cy0 + (bodyY + ay - cy0) * CARD_ZOOM] as const; };
  const orbs = lyric.flatMap((s, i) => {
    const prev = lyric[i - 1];
    if (!prev) return [];
    const [ax, ay] = anchor(prev.kind), [bx, by] = anchor(s.kind), top = Math.min(ay, by) - 80;
    return ([[0, 1], [0.05, 0.62], [0.1, 0.4]] as const).map(([dl, sz]) => {
      const r = 28 * sz, t0 = s.start - 0.05 + dl, u = t - t0;
      if (u < 0 || u > 0.7) return null;
      const px = ft(u, 0, 0.45, ax, bx, "power2.inOut") - r;
      const py = (u < 0.22 ? ft(u, 0, 0.22, ay, top, "power2.out") : ft(u, 0.22, 0.23, top, by, "power2.in")) - r;
      const gone = pr(u, 0.45, 0.2, "power2.out");
      const op = u < 0.45 ? (1 - dl * 2) * 0.65 * pr(u, 0, 0.1) : (1 - dl * 2) * 0.65 * (1 - gone);
      return <div key={`o${s.i}_${dl}`} style={{ position: "absolute", left: 0, top: 0, zIndex: 5, width: 2 * r, height: 2 * r, borderRadius: r, opacity: op, transform: `translate(${px}px, ${py}px) scale(${u < 0.45 ? 0.5 + 0.5 * pr(u, 0, 0.1) : 1 + 1.4 * gone})`,
        background: `radial-gradient(circle,#fff 0 22%,${s.icon} 40%,rgba(255,255,255,0) 72%)` }} />;
    });
  });

  // ---------- outro ----------
  const os = p.scenes.find((s) => s.role === "outro");
  const outro = os && t >= os.start ? (() => {
    const t0 = os.start, u = t - t0, ep = pr(t, t0 + 0.2, 0.5, "back.out(1.8)"), tp = pr(t, t0 + 0.45, 0.4, "power2.out");
    const fs2 = Math.max(60, Math.min(112, Math.trunc(900 / (0.78 * Math.max(Math.min(p.title.length, 24), 1)))));
    return (
      <>
        <svg viewBox="0 0 400 400" style={{ position: "absolute", left: 340, top: 240, width: 400, height: 400, opacity: pr(t, t0 + 0.2, 0.4, "power2.out"), transform: `scale(${0.6 + 0.4 * pr(t, t0 + 0.2, 0.4, "power2.out")}) rotate(${150 * (u / Math.max(dur - t0, 0.1))}deg)` }}>
          <circle cx={200} cy={200} r={180} fill="none" stroke={acc} strokeWidth={5} strokeDasharray="3 22" strokeLinecap="round" opacity={0.55} />
        </svg>
        <div style={{ position: "absolute", left: 430, top: 330, width: 220, height: 220, borderRadius: 54, background: `linear-gradient(135deg,${ta},${tb})`, boxShadow: "0 20px 50px rgba(90,70,160,.3)", display: "flex", alignItems: "center", justifyContent: "center",
          opacity: pr(t, t0 + 0.2, 0.5, "power1.out"), transform: `translateY(${t > t0 + 0.75 ? -10 * yoyo(t, t0 + 0.75, 0.8) : 0}px) scale(${0.2 + 0.8 * ep}) rotate(${-25 * (1 - ep)}deg)` }}><Note size={120} /></div>
        <div style={{ position: "absolute", left: 0, top: 585, width: W, display: "flex", flexDirection: "column", alignItems: "center", gap: 12, opacity: tp, transform: `translateY(${24 * (1 - tp)}px) scale(${1 + 0.04 * (t > t0 + 0.9 ? yoyo(t, t0 + 0.9, 0.9) : 0)})` }}>
          {p.series && <div style={{ textAlign: "center", fontWeight: 700, fontSize: 34, letterSpacing: 4, color: TX2, textTransform: "uppercase" }}>{p.series}</div>}
          <div style={{ textAlign: "center", fontWeight: 900, lineHeight: 1.05, letterSpacing: -1, color: TXF, textShadow: TXS, fontSize: fs2 }}>{p.title.slice(0, 24).toUpperCase()}</div>
          <div style={{ textAlign: "center", fontWeight: 700, fontSize: 40, color: TX2 }}>{p.artist.slice(0, 30)}</div>
          <div style={{ textAlign: "center", fontWeight: 900, fontSize: 46, color: TX }}>{p.credit}</div>
          <div style={{ textAlign: "center", fontWeight: 700, fontSize: 44, marginTop: 20, maxWidth: 900, color: TX2 }}>{p.hook}</div>
        </div>
        {Array.from({ length: 14 }, (_, q) => { const a = (q / 14) * 6.283, k = pr(t, t0 + 0.2, 0.9, "power2.out"); return t >= t0 + 0.2 ? <Cross key={q} x={525 + 110 * Math.cos(a) + 260 * Math.cos(a) * k} y={425 + 110 * Math.sin(a) + 260 * Math.sin(a) * k} s={30} col={COLS[q % 5]} o={0.95 * (1 - k)} rot={(120 + q * 17) * k} /> : null; })}
      </>
    );
  })() : null;
  const orbOut = os ? (() => { const a = pr(t, os.start - 0.2, 0.3, "power2.out"), b = pr(t, os.start + 0.15, 0.35, "power2.out"); return t >= os.start - 0.2 && t < os.start + 0.5 ? <div style={{ position: "absolute", left: 480, top: 403, width: 120, height: 120, borderRadius: 60, zIndex: 5, opacity: a * (1 - b), transform: `scale(${(0.2 + 0.8 * a) * (1 + 1.8 * b)})`, background: `radial-gradient(circle,#fff 0 20%,${ta} 42%,rgba(255,255,255,0) 72%)` }} /> : null; })() : null;

  // ---------- hook ----------
  const hfs = p.hook.length <= 14 ? 124 : p.hook.length <= 24 ? 100 : 80;
  const hookOp = 1 - pr(t, p.hookD - 0.27, 0.25, "power2.in");
  const hookSc = 1.12 - 0.12 * pr(t, 0, 0.4, "back.out(1.7)");

  return (
    <AbsoluteFill style={{ background: "#000", fontFamily, ["--ta" as any]: ta, ["--tb" as any]: tb }}>
      <div style={{ position: "absolute", left: 0, top: OY, width: W, height: SQ, overflow: "hidden", background: `linear-gradient(160deg,${p.pal.b[0]},${p.pal.b[1]} 55%,${p.pal.b[2]})` }}>
        {p.alternate && <div style={{ position: "absolute", inset: 0, opacity: altOn, background: `linear-gradient(160deg,${p.pal.alt[0]},${p.pal.alt[1]} 55%,${p.pal.alt[2]})` }} />}
        <div style={{ position: "absolute", left: -150, top: -100, width: 700, height: 700, borderRadius: 350, background: "radial-gradient(circle,rgba(255,150,190,.5),rgba(255,150,190,0) 70%)", transform: `translate(${ft(t, 0, dur, 0, 420, "sine.inOut")}px, ${ft(t, 0, dur, 0, 380, "sine.inOut")}px)` }} />
        <div style={{ position: "absolute", left: 520, top: 480, width: 700, height: 700, borderRadius: 350, background: "radial-gradient(circle,rgba(150,170,255,.45),rgba(150,170,255,0) 70%)", transform: `translate(${ft(t, 0, dur, 0, -420, "sine.inOut")}px, ${ft(t, 0, dur, 0, -380, "sine.inOut")}px)` }} />
        {Array.from({ length: 16 }, (_, i) => <Cross key={`x${i}`} x={ri(i, 1, 30, 1020) + ri(i, 5, -80, 80) * (t / dur)} y={ri(i, 2, 20, 1040) + ri(i, 6, -260, 260) * (t / dur)} s={ri(i, 3, 18, 42)} col={COLS[i % 5]} o={0.7} rot={ri(i, 4, -90, 90) * (t / dur)} />)}
        {Array.from({ length: 16 }, (_, k) => <i key={`d${k}`} style={{ position: "absolute", left: ri(k, 7, 20, 1040) + ri(k, 8, -100, 100) * (t / dur), top: ri(k, 9, 20, 1040) + ri(k, 10, -300, 300) * (t / dur), width: ri(k, 11, 10, 22), height: ri(k, 11, 10, 22), borderRadius: "50%", background: COLS[k % 5], opacity: 0.7 }} />)}

        {chromeOn && (
          <div style={{ position: "absolute", inset: 0, transform: `translateY(${chromeY}px)`, zIndex: 20 }}>
            <div style={{ position: "absolute", left: 110, top: 62, fontWeight: 800, fontSize: 34, color: TX }}>19<span style={{ opacity: Math.floor(t * 2) % 2 ? 0.15 : 1 }}>:</span>47</div>
            <div style={{ position: "absolute", left: 880, top: 70, width: 62, height: 28, boxSizing: "border-box", border: `3px solid ${TX}`, borderRadius: 9, overflow: "hidden" }}><i style={{ display: "block", height: "100%", width: `${ft(t, 0, cd, 70, 52)}%`, background: TX }} /></div>
            <div style={{ position: "absolute", left: 260, top: 44, width: 560, height: 96, borderRadius: 48, background: "#0b0b10", display: "flex", alignItems: "center", gap: 16, padding: "0 24px 0 20px", boxSizing: "border-box" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 16, flex: 1, minWidth: 0, height: "100%", opacity: isc }}>
                <div style={{ width: 60, height: 60, borderRadius: 14, background: "#2a2a38", display: "flex", alignItems: "center", justifyContent: "center", flex: "none", transform: `rotate(${-12 + 24 * yoyo(t, 0, 0.6)}deg)` }}><Note size={30} /></div>
                <div style={{ display: "flex", flexDirection: "column", flex: 1, minWidth: 0 }}>
                  <b style={{ color: "#fff", fontSize: 26, whiteSpace: "nowrap" }}>{p.title.slice(0, 17)}</b><span style={{ color: "#a4a4bb", fontSize: 21, fontWeight: 600, whiteSpace: "nowrap" }}>{p.artist.slice(0, 22)}</span>
                </div>
                <div style={{ position: "relative", width: 44, height: 44, flex: "none" }}>{[0, 1, 2, 3].map((k) => <div key={k} style={{ position: "absolute", bottom: 0, left: k * 12, width: 8, height: 44, borderRadius: 4, background: ta, transformOrigin: "50% 100%", transform: `scaleY(${0.3 + 0.7 * Math.abs(Math.sin(t * (2.2 + k * 0.7) + k))})` }} />)}</div>
              </div>
              {notifs.map(({ s, nc }) => (
                <div key={`n${s.i}`} style={{ position: "absolute", left: 0, top: 0, width: 560, height: 96, display: "flex", alignItems: "center", gap: 16, padding: "0 24px 0 20px", boxSizing: "border-box", opacity: nc }}>
                  <div style={{ width: 60, height: 60, borderRadius: 14, background: s.notify!.icon, display: "flex", alignItems: "center", justifyContent: "center", flex: "none" }}>
                    <svg viewBox="0 0 24 24" width={32} height={32}><path d={GLYPH[s.notify!.glyph ?? "bell"]} fill={s.notify!.glyph === "lines" ? "none" : "#fff"} stroke={s.notify!.glyph === "lines" ? "#fff" : "none"} strokeWidth={2.4} strokeLinecap="round" /></svg>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", flex: 1, minWidth: 0 }}>
                    <b style={{ color: "#fff", fontSize: 26, whiteSpace: "nowrap" }}>{s.notify!.app.slice(0, 18)}</b><span style={{ color: "#a4a4bb", fontSize: 21, fontWeight: 600, whiteSpace: "nowrap" }}>{s.notify!.text.slice(0, 36)}</span>
                  </div>
                  <span style={{ color: "#b9b6d0", fontSize: 18, fontWeight: 600, flex: "none" }}>сейчас</span>
                </div>
              ))}
            </div>
            <div style={{ position: "absolute", left: 370, top: 825, width: 340, height: 56, borderRadius: 28, background: "rgba(255,255,255,.92)", display: "flex", alignItems: "center", justifyContent: "center", gap: 12, fontSize: 28, fontWeight: 800, color: INK, boxShadow: "0 8px 24px rgba(90,70,160,.15)" }}>
              <i style={{ width: 30, height: 30, borderRadius: 15, background: `conic-gradient(${ta},${tb},${ta})`, display: "block", transform: `rotate(${(t / 3) * 360}deg)` }} />{p.credit}
            </div>
            <div style={{ position: "absolute", left: 60, top: 893, width: 960, textAlign: "center", whiteSpace: "nowrap", fontWeight: 800, fontSize: 44, color: TX, transform: `translateY(${-3 + 6 * yoyo(t, 0, 1.2)}px)` }}>
              {(p.artist ? `${p.artist} — ${p.title}` : p.title).length <= 32 ? (p.artist ? `${p.artist} — ${p.title}` : p.title) : p.title.slice(0, 31) + "…"}
            </div>
            <div style={{ position: "absolute", left: 160, top: 986, width: 760, height: 8, borderRadius: 4, background: TRK }}><div style={{ height: 8, borderRadius: 4, background: `linear-gradient(90deg,${ta},${tb})`, width: 760 * (clock / cd) }} /></div>
            <div style={{ position: "absolute", left: 150 + 760 * (clock / cd), top: 980, width: 20, height: 20, borderRadius: 10, background: "#fff", boxShadow: "0 2px 8px rgba(40,30,80,.3)" }} />
            <div style={{ position: "absolute", left: 160, top: 1004, fontSize: 26, fontWeight: 700, color: TX2 }}>{mm(Math.floor(clock))}</div>
            <div style={{ position: "absolute", right: 160, top: 1004, fontSize: 26, fontWeight: 700, color: TX2 }}>-{mm(Math.ceil(cd - clock))}</div>
          </div>
        )}

        {lyric.map((s, i) => card(s, i))}
        {orbs}
        {lyric.flatMap((s) => Array.from({ length: 8 }, (_, q) => {
          const a = (q / 8) * 6.283 + (s.i % 3) * 0.3, u = t - (s.start + 0.1);
          if (u < 0 || u > 0.8) return null;
          const k = pr(u, 0, 0.8, "power2.out");
          return <Cross key={`b${s.i}_${q}`} x={520 + 40 * Math.cos(a) + 330 * Math.cos(a) * k} y={460 + 40 * Math.sin(a) + 300 * Math.sin(a) * k} s={30} col={COLS[q % 5]} o={0.9 * (1 - k)} rot={(90 + q * 20) * k} />;
        }))}
        {orbOut}
        {outro}
      </div>
      <div style={{ position: "absolute", left: 60, top: 60, width: 960, height: 300, zIndex: 60, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", textAlign: "center", color: "#fff", fontWeight: 900, lineHeight: 1.08, overflowWrap: "anywhere",
        opacity: t < p.hookD ? hookOp : 0, transform: `scale(${hookSc})` }}>
        <div style={{ fontSize: hfs, textShadow: "0 0 18px #ff3d9a,0 0 46px #ff3d9a" }}>{p.hook}</div>
        {p.series && <div style={{ marginTop: 18, fontSize: 34, fontWeight: 700, letterSpacing: 4, color: "#ff9ec4", textTransform: "uppercase" }}>{p.series}</div>}
      </div>
    </AbsoluteFill>
  );
};

const LOOP_S = 0.5; // the last half second dissolves into the first frame, so a replay does not jump

export const Widgets: React.FC<WidgetsProps> = (p) => {
  const t = useCurrentFrame() / p.fps;
  const k = pr(t, p.duration - LOOP_S, LOOP_S, "power1.inOut");
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      <Frame {...p} t={t} />
      {k > 0 && <AbsoluteFill style={{ opacity: k }}><Frame {...p} t={0} /></AbsoluteFill>}
    </AbsoluteFill>
  );
};
