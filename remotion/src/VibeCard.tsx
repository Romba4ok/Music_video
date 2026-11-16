import React from "react";
import { AbsoluteFill, Easing, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Audio } from "@remotion/media";
import { loadFont } from "@remotion/google-fonts/Manrope";
import { INK, lin, rnd, seg } from "./Sansara";

const { fontFamily } = loadFont("normal", { weights: ["500", "700", "800"], subsets: ["cyrillic", "latin"] });

// "Уматурман — Просковья" in the project's card format with the dark flat "night room" style of the studied author:
// one white tilted card per lyric line, a new metaphor with props in each card, snow/dust particles, author pill, title, progress.
// NO subtitles: lyrics are never drawn, they only time the cards. Times are SONG seconds (whisper large-v3 pass on the supplied mp3):
//   52.8 "Ночь, луны обвалятся, пропадётся с небес" · 56.5 "В окно уставится, останется смотреть" · 59.3 "В твоём сердце нет свободных мест"
//   62.7 "И снова ты должна любовь свою стереть" · 68.3 "Девушка Просковья… снова одна" · 74.2 "…плачет у окна"
const S = 52.4;
const AUDIO_END = 81.6;
export const VIBECARD_DURATION = Math.round((AUDIO_END - S + 2.4) * 30);
const TITLE = "Просковья";
const ARTIST = "Уматурман";
const HANDLE = "vybex";
const HOOK = "КАК РАЗЛЮБИТЬ ТОГО, КОГО ЛЮБИШЬ?";

const W = 902, H = 972;
const WARM = "#ffcf8a", COOL = "#8fd0ff", ROSE = "#ef5a7a", NAVY = "#0d1230", INKD = "#07080f";
const clamp01 = (x: number) => Math.max(0, Math.min(1, x));
const back = Easing.out(Easing.back(1.6));
type P = { u: number; d: number };

// ---------- shared pieces ----------
const Snow: React.FC<{ u: number; n?: number; x0?: number; x1?: number; y0?: number; y1?: number; op?: number }> = ({ u, n = 60, x0 = 0, x1 = W, y0 = 0, y1 = H, op = 0.8 }) => (
  <>{Array.from({ length: n }, (_, i) => {
    const sp = 40 + rnd(i, 3) * 60, h = y1 - y0;
    const y = y0 + (((rnd(i, 2) * h + u * sp) % h) + h) % h;
    return <circle key={i} cx={x0 + ((rnd(i, 1) * (x1 - x0) + Math.sin(u * 0.8 + i) * 18 + (x1 - x0)) % (x1 - x0))} cy={y} r={2 + rnd(i, 4) * 3.2} fill="#fff" opacity={op * (0.5 + 0.5 * rnd(i, 5))} />;
  })}</>
);

const Win: React.FC<{ x: number; y: number; w: number; h: number; u: number; moon?: { x: number; y: number; r: number }; id: string }> = ({ x, y, w, h, u, moon, id }) => (
  <g>
    <defs>
      <linearGradient id={`sk${id}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={NAVY} /><stop offset="1" stopColor="#3a2a55" /></linearGradient>
      <clipPath id={`wc${id}`}><rect x={x} y={y} width={w} height={h} /></clipPath>
    </defs>
    <g clipPath={`url(#wc${id})`}>
      <rect x={x} y={y} width={w} height={h} fill={`url(#sk${id})`} />
      {Array.from({ length: 16 }, (_, i) => <circle key={i} cx={x + rnd(i, 1) * w} cy={y + rnd(i, 2) * h * 0.5} r={1.5 + rnd(i, 3) * 1.5} fill="#fff" opacity={0.4 + 0.4 * Math.sin(u * 2 + i)} />)}
      {moon && <><circle cx={moon.x} cy={moon.y} r={moon.r * 1.9} fill="#fff6d8" opacity={0.1} /><circle cx={moon.x} cy={moon.y} r={moon.r} fill="#fff6d8" /></>}
      {Array.from({ length: 6 }, (_, i) => {
        const bw = w / 6, bh = 70 + rnd(i, 7) * 90;
        return <g key={i}><rect x={x + i * bw} y={y + h - bh} width={bw - 4} height={bh} fill="#0a0b16" />
          {rnd(i, 8) > 0.3 && <rect x={x + i * bw + 12} y={y + h - bh + 20} width={14} height={20} fill={WARM} opacity={0.85} />}</g>;
      })}
      <Snow u={u} n={34} x0={x} x1={x + w} y0={y} y1={y + h} />
    </g>
    <rect x={x} y={y} width={w} height={h} fill="none" stroke={INKD} strokeWidth={20} />
    <rect x={x + w / 2 - 7} y={y} width={14} height={h} fill={INKD} /><rect x={x} y={y + h * 0.55} width={w} height={14} fill={INKD} />
    <rect x={x - 24} y={y + h + 6} width={w + 48} height={20} rx={6} fill="#2a2038" /><rect x={x - 10} y={y + h - 4} width={w + 20} height={12} rx={6} fill="#fff" opacity={0.85} />
  </g>
);

const Curtains: React.FC<{ x: number; y: number; w: number; h: number; u: number }> = ({ x, y, w, h, u }) => (
  <g fill="#3b2147">
    <path d={`M${x - 70} ${y - 40} H${x + 70} Q${x + 40 + 8 * Math.sin(u)} ${y + h / 2} ${x + 80} ${y + h + 40} H${x - 70} Z`} />
    <path d={`M${x + w + 70} ${y - 40} H${x + w - 70} Q${x + w - 40 - 8 * Math.sin(u + 1)} ${y + h / 2} ${x + w - 80} ${y + h + 40} H${x + w + 70} Z`} />
  </g>
);

const Girl: React.FC<{ x: number; y: number; s: number; u: number; tilt?: number }> = ({ x, y, s, u, tilt = 0 }) => (
  <g transform={`translate(${x} ${y}) scale(${s})`}>
    <path d="M-62 0 Q-70 -70 -30 -88 H30 Q70 -70 62 0 Z" fill="#0b0c18" stroke={COOL} strokeWidth={3} opacity={1} strokeOpacity={0.5} />
    <g transform={`rotate(${tilt + 2 * Math.sin(u * 0.9)} 0 -92)`}>
      <path d="M-34 -150 Q-46 -80 -30 -62 H30 Q46 -80 34 -150 Q0 -190 -34 -150 Z" fill="#14101f" stroke={COOL} strokeWidth={3} strokeOpacity={0.45} />
      <circle cx={0} cy={-124} r={30} fill="#0b0c18" />
    </g>
  </g>
);

const Bg: React.FC<{ id: string }> = ({ id }) => (
  <>
    <defs><linearGradient id={`bg${id}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#141a3c" /><stop offset="1" stopColor="#0a0a18" /></linearGradient></defs>
    <rect width={W} height={H} fill={`url(#bg${id})`} />
  </>
);

// ---------- cards ----------
const C0: React.FC<P> = ({ u, d }) => {
  const f = Easing.in(Easing.quad)(seg(u, 0.4, d * 0.92, lin)), my = 270 + 330 * f;
  return (
    <svg width={W} height={H}>
      <Bg id="0" />
      <Win x={120} y={110} w={660} h={700} u={u} id="0" moon={{ x: 450, y: my, r: 70 }} />
      <Curtains x={120} y={110} w={660} h={700} u={u} />
      {/* trail + falling stars */}
      <g clipPath="url(#wc0)"><rect x={440} y={270} width={20} height={Math.max(0, my - 270)} fill="#fff6d8" opacity={0.18} /></g>
      {Array.from({ length: 7 }, (_, i) => { const p = ((u * 0.5 + rnd(i, 1)) % 1); return <line key={i} x1={160 + rnd(i, 2) * 580 - p * 60} y1={130 + p * 520} x2={160 + rnd(i, 2) * 580 - p * 60 - 14} y2={130 + p * 520 + 46} stroke="#fff" strokeWidth={3} opacity={(1 - p) * 0.7} />; })}
      <rect x={0} y={840} width={W} height={H - 840} fill="#1b1326" />
      <circle cx={450} cy={810} r={30 + 80 * f} fill={WARM} opacity={0.18 * f} />
    </svg>
  );
};

const C1: React.FC<P> = ({ u }) => {
  const pulse = 1 + 0.03 * Math.sin(u * 2.4), a = seg(u, 0, 0.8);
  return (
    <svg width={W} height={H}>
      <defs><linearGradient id="bm" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#fff6d8" stopOpacity=".42" /><stop offset="1" stopColor="#fff6d8" stopOpacity="0" /></linearGradient></defs>
      <Bg id="1" />
      <Win x={120} y={110} w={660} h={700} u={u} id="1" moon={{ x: 450, y: 560 - 20 * a, r: 120 * pulse }} />
      <Curtains x={120} y={110} w={660} h={700} u={u} />
      <polygon points={`190,826 710,826 900,${H} 0,${H}`} fill="url(#bm)" opacity={a} />
      <rect x={0} y={840} width={W} height={H - 840} fill="#1b1326" opacity={0.85} />
      <Girl x={330} y={960} s={1.8} u={u} tilt={5} />
      <Snow u={u} n={14} y0={826} y1={H} x0={150} x1={760} op={0.4} />
    </svg>
  );
};

const HEART = (x: number, y: number) => (x * x + y * y - 1) ** 3 - x * x * y ** 3 <= 0;
const C2: React.FC<P> = ({ u, d }) => {
  const cell = 34, cols = 17, rows = 15, ox = (W - cols * cell) / 2, oy = 190;
  const lock = seg(u, d * 0.6, d * 0.6 + 0.5, back);
  return (
    <svg width={W} height={H}>
      <Bg id="2" />
      <Snow u={u} n={36} op={0.5} />
      {Array.from({ length: cols * rows }, (_, k) => {
        const i = k % cols, j = Math.floor(k / cols), nx = ((i + 0.5) / cols - 0.5) * 3.1, ny = -(((j + 0.5) / rows - 0.42) * 3.0);
        if (!HEART(nx, ny)) return null;
        const dist = Math.hypot(nx, ny), on = seg(u, 0.15 + dist * 0.55 + rnd(k, 1) * 0.5, 0.15 + dist * 0.55 + rnd(k, 1) * 0.5 + 0.3);
        return <rect key={k} x={ox + i * cell + 3} y={oy + j * cell * 1.2 + 3} width={cell - 6} height={cell * 1.2 - 6} rx={7} fill={rnd(k, 2) > 0.3 ? WARM : ROSE} opacity={0.16 + 0.84 * on} />;
      })}
      <g transform={`translate(${W / 2} 560) scale(${lock})`}>
        <path d="M-50 -20 V-60 A50 50 0 0 1 50 -60 V-20" fill="none" stroke="#e8e1ff" strokeWidth={18} strokeLinecap="round" />
        <rect x={-72} y={-24} width={144} height={110} rx={20} fill="#e8e1ff" /><circle cx={0} cy={26} r={16} fill={INKD} /><rect x={-5} y={30} width={10} height={36} rx={4} fill={INKD} />
      </g>
    </svg>
  );
};

const C3: React.FC<P> = ({ u, d }) => {
  const cx = 451, cy = 480, hp = "M0 150 C-230 -10 -140 -190 0 -70 C140 -190 230 -10 0 150 Z";
  const sw = (a: number, b: number) => seg(u, a * d, b * d, Easing.inOut(Easing.quad));
  const s1 = sw(0.3, 0.58), s2 = sw(0.8, 0.97), redraw = seg(u, 0.6 * d, 0.72 * d);
  const sweepX = (s: number) => 70 + 760 * s;
  const e1 = s1 > 0 && s1 < 1, e2 = s2 > 0 && s2 < 1, ex = e2 ? sweepX(s2) : sweepX(s1);
  const clipStart = u < 0.6 * d ? sweepX(s1) : s2 > 0 ? sweepX(s2) : 0;
  return (
    <svg width={W} height={H}>
      <defs><clipPath id="er"><rect x={clipStart} y={0} width={W} height={H} /></clipPath></defs>
      <Bg id="3" />
      <Snow u={u} n={26} op={0.4} />
      <g transform={`translate(${cx} ${cy})`} clipPath="url(#er)" opacity={u < 0.6 * d ? 1 : redraw}>
        <path d={hp} fill={ROSE} opacity={0.9} stroke="#ffd0dc" strokeWidth={8} />
      </g>
      {(e1 || e2) && <g transform={`translate(${ex} ${cy + 50 + 20 * Math.sin(u * 18)}) rotate(-12)`}>
        <rect x={-70} y={-62} width={140} height={124} rx={18} fill="#f4b8c4" /><rect x={-70} y={-62} width={140} height={44} rx={18} fill="#4a6fd8" /><rect x={-70} y={-30} width={140} height={14} fill="#4a6fd8" />
      </g>}
      {(e1 || e2) && Array.from({ length: 18 }, (_, i) => { const p = ((u * 3 + rnd(i, 1)) % 1); return <circle key={i} cx={ex - 30 - p * 60} cy={cy + 120 + p * 220 + rnd(i, 2) * 60 - 80} r={3 + rnd(i, 3) * 4} fill="#f4b8c4" opacity={(1 - p) * 0.9} />; })}
      <rect x={0} y={840} width={W} height={H - 840} fill="#1b1326" />
    </svg>
  );
};

const Chair: React.FC<{ x: number; y: number }> = ({ x, y }) => (
  <g transform={`translate(${x} ${y})`} fill="#0b0c18" stroke="#3a2a55" strokeWidth={3}>
    <rect x={-50} y={-120} width={100} height={90} rx={10} /><rect x={-60} y={-34} width={120} height={22} rx={8} /><rect x={-48} y={-12} width={10} height={80} /><rect x={38} y={-12} width={10} height={80} />
  </g>
);

const C4: React.FC<P> = ({ u }) => (
  <svg width={W} height={H}>
    <defs><radialGradient id="pool"><stop offset="0" stopColor={WARM} stopOpacity=".5" /><stop offset="1" stopColor={WARM} stopOpacity="0" /></radialGradient></defs>
    <Bg id="4" />
    <Win x={70} y={130} w={380} h={440} u={u} id="4" moon={{ x: 330, y: 270, r: 34 }} />
    <Curtains x={70} y={130} w={380} h={440} u={u} />
    <rect x={0} y={700} width={W} height={H - 700} fill="#1b1326" /><rect x={0} y={700} width={W} height={6} fill="#4a3a5c" />
    <ellipse cx={230} cy={880} rx={230} ry={90} fill="url(#pool)" />
    <polygon points="260,860 700,900 740,940 230,925" fill="#000" opacity={0.35} />
    <Chair x={640} y={840} />
    <g transform="translate(790 800)"><rect x={-40} y={0} width={80} height={14} rx={6} fill="#2a2038" /><rect x={-5} y={14} width={10} height={80} fill="#2a2038" />
      <rect x={-18} y={-30} width={36} height={30} rx={8} fill="#e8e1ff" />
      {Array.from({ length: 3 }, (_, i) => { const p = ((u * 0.5 + i / 3) % 1); return <path key={i} d={`M${-8 + i * 8} -34 q${8 * Math.sin(u * 3 + i)} -20 0 -40`} stroke="#fff" strokeWidth={4} fill="none" opacity={(1 - p) * 0.5} strokeLinecap="round" transform={`translate(0 ${-p * 50})`} />; })}</g>
    <Girl x={220} y={850} s={1.35} u={u} tilt={-4} />
    <Snow u={u} n={16} y0={700} y1={H} op={0.25} />
  </svg>
);

const C5: React.FC<P> = ({ u }) => {
  const cyc = (u % 3.2) / 3.2, tearY = 220 + 600 * Easing.in(Easing.quad)(clamp01(cyc / 0.85)), splash = clamp01((cyc - 0.85) / 0.15);
  return (
    <svg width={W} height={H}>
      <defs>
        <filter id="bk"><feGaussianBlur stdDeviation="14" /></filter>
        <radialGradient id="fog"><stop offset="0.55" stopColor="#fff" stopOpacity="0" /><stop offset="1" stopColor="#fff" stopOpacity=".12" /></radialGradient>
      </defs>
      <Bg id="5" />
      <g filter="url(#bk)">{Array.from({ length: 16 }, (_, i) => <circle key={i} cx={rnd(i, 1) * W} cy={380 + rnd(i, 2) * 420} r={30 + rnd(i, 3) * 40} fill={i % 3 ? WARM : COOL} opacity={0.35 + 0.2 * Math.sin(u * 1.4 + i)} />)}</g>
      <g opacity={0.18}><Girl x={560} y={900} s={3.2} u={u} /></g>
      <rect width={W} height={H} fill="url(#fog)" />
      {Array.from({ length: 8 }, (_, i) => {
        const p = ((u * (0.12 + rnd(i, 1) * 0.1) + rnd(i, 2)) % 1), x = 60 + rnd(i, 3) * 780, y = 120 + p * 700;
        return <g key={i}><line x1={x} y1={y - 90 * p} x2={x} y2={y} stroke="#cfe6ff" strokeWidth={3} opacity={0.25} /><ellipse cx={x} cy={y} rx={7} ry={10} fill="#cfe6ff" opacity={0.6} /></g>;
      })}
      <g opacity={cyc < 0.85 ? 1 : 0}><line x1={450} y1={tearY - 130 * Easing.in(Easing.quad)(clamp01(cyc / 0.85))} x2={450} y2={tearY} stroke="#cfe6ff" strokeWidth={4} opacity={0.4} /><path d={`M450 ${tearY - 30} Q432 ${tearY + 4} 450 ${tearY + 14} Q468 ${tearY + 4} 450 ${tearY - 30} Z`} fill="#e8f4ff" /></g>
      <rect x={0} y={850} width={W} height={H - 850} fill="#2a2038" /><rect x={0} y={850} width={W} height={14} fill="#fff" opacity={0.8} />
      {splash > 0 && [0, 1].map((k) => <ellipse key={k} cx={450} cy={858} rx={20 + 120 * splash + k * 40} ry={5 + 16 * splash + k * 4} fill="none" stroke="#e8f4ff" strokeWidth={4 * (1 - splash)} opacity={1 - splash} />)}
      <Snow u={u} n={20} op={0.35} />
    </svg>
  );
};

const CARDS: { start: number; Pic: React.FC<P> }[] = [
  { start: S, Pic: C0 }, { start: 56.5, Pic: C1 }, { start: 59.3, Pic: C2 }, { start: 62.7, Pic: C3 }, { start: 68.3, Pic: C4 }, { start: 74.2, Pic: C5 },
];
const endOf = (i: number) => (i + 1 < CARDS.length ? CARDS[i + 1].start : AUDIO_END);
const mmss = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

export const VibeCard: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = S + frame / fps;
  const frag = AUDIO_END - S;
  const el = Math.min(t, AUDIO_END) - S;
  const uiOut = seg(t, AUDIO_END - 1.0, AUDIO_END - 0.35);
  const endIn = seg(t, AUDIO_END - 0.6, AUDIO_END + 0.2);
  const active = CARDS.reduce((m, c, i) => (t >= c.start ? i : m), 0);
  const vol = (f: number) => {
    const ts = S + f / fps;
    return Math.min(seg(ts, S, S + 0.12, lin), 1 - seg(ts, AUDIO_END - 0.6, AUDIO_END, lin));
  };
  return (
    <AbsoluteFill style={{ fontFamily, color: INK, background: "linear-gradient(160deg,#ffd9e6 0%,#eadcfb 50%,#d3e5ff 100%)" }}>
      <Audio src={staticFile("proskovya.mp3")} trimBefore={Math.round(S * fps)} volume={vol} />
      {[["#ffd7b8", 0.9], ["#d4f5e6", 0.7], ["#ffc6df", 0.8]].map(([c, o], i) => (
        <div key={i} style={{ position: "absolute", width: 900, height: 900, borderRadius: "50%", background: `radial-gradient(circle, ${c} 0%, transparent 65%)`, opacity: Number(o),
          left: 540 + 380 * Math.sin(t * 0.22 + i * 2.1) - 450, top: 400 + i * 420 + 220 * Math.cos(t * 0.19 + i * 1.7) - 450 }} />
      ))}
      <div style={{ position: "absolute", inset: 0, opacity: 1 - uiOut }}>
        <div style={{ position: "absolute", top: 90, left: 60, right: 60, textAlign: "center", fontSize: 58, fontWeight: 800, lineHeight: 1.08 }}>{HOOK}</div>

        {CARDS.map((c, i) => {
          const next = endOf(i), d = next - c.start, u = t - c.start;
          if (u < 0 || t > next + 0.6) return null;
          const a = i === 0 ? 1 : seg(u, 0, 0.38, Easing.out(Easing.cubic));
          const w = t > next && i < CARDS.length - 1 ? Math.min(1, (t - next) / 0.6) : 0;
          const idle = Math.sin((t * 2 * Math.PI) / 5.2) * 3 * (1 - w);
          const Pic = c.Pic;
          return (
            <div key={i} style={{ position: "absolute", left: 75, top: 290, width: 930, height: 1000, borderRadius: 56, background: "rgba(255,255,255,0.97)", zIndex: i,
              boxShadow: "0 28px 70px rgba(120,90,190,.28)", opacity: a * (w > 0 ? 0.5 * (1 - w) : 1), filter: `blur(${(1 - a) * 14 + 6 * w}px)`,
              transform: `translateY(${(1 - a) * 560 - 30 * w}px) perspective(1400px) rotateX(${(1 - a) * -10}deg) rotateY(${idle - (1 - a) * 8}deg) scale(${1.02 * (1 - 0.07 * w)})` }}>
              <div style={{ position: "absolute", left: 14, top: 14, width: W, height: H, borderRadius: 44, overflow: "hidden" }}>
                <div style={{ width: W, height: H, transform: `scale(${1 + 0.05 * clamp01(u / d)})`, transformOrigin: "50% 60%" }}><Pic u={u} d={d} /></div>
                <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 50%, transparent 55%, rgba(0,0,0,.45) 100%)" }} />
              </div>
            </div>
          );
        })}

        <div style={{ position: "absolute", top: 1320, left: 0, right: 0, display: "flex", justifyContent: "center", gap: 14 }}>
          {CARDS.map((_, i) => <div key={i} style={{ width: i === active ? 44 : 12, height: 12, borderRadius: 6, background: i === active ? INK : "rgba(29,27,46,.25)" }} />)}
        </div>
        <div style={{ position: "absolute", top: 1370, left: "50%", marginLeft: -170, width: 340, height: 56, borderRadius: 28, background: "rgba(255,255,255,.85)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 28, fontWeight: 800 }}>
          автор: {HANDLE}
        </div>
        <div style={{ position: "absolute", top: 1446, left: 0, right: 0, textAlign: "center", fontSize: 50, fontWeight: 800 }}>{TITLE}</div>
        <div style={{ position: "absolute", top: 1514, left: 0, right: 0, textAlign: "center", fontSize: 32, fontWeight: 500, opacity: 0.6 }}>{ARTIST}</div>
        <div style={{ position: "absolute", top: 1585, left: 165, width: 750, height: 7, borderRadius: 4, background: "rgba(29,27,46,.15)" }}>
          <div style={{ width: `${(el / frag) * 100}%`, height: "100%", borderRadius: 4, background: INK }} />
          <div style={{ position: "absolute", left: `${(el / frag) * 100}%`, top: -6, width: 19, height: 19, marginLeft: -9, borderRadius: "50%", background: INK }} />
        </div>
        <div style={{ position: "absolute", top: 1607, left: 165, fontSize: 24, opacity: 0.6 }}>{mmss(el)}</div>
        <div style={{ position: "absolute", top: 1607, right: 165, fontSize: 24, opacity: 0.6 }}>-{mmss(frag - el)}</div>
      </div>

      <div style={{ position: "absolute", inset: 0, opacity: endIn, transform: `scale(${0.92 + 0.08 * endIn})`, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <div style={{ fontSize: 112, fontWeight: 800, textAlign: "center", lineHeight: 1.05, padding: "0 60px" }}>{TITLE}</div>
        <div style={{ fontSize: 60, fontWeight: 700, opacity: 0.6, marginTop: 10 }}>{ARTIST}</div>
        <div style={{ marginTop: 36, padding: "10px 34px", borderRadius: 40, background: "rgba(255,255,255,.85)", fontSize: 32, fontWeight: 800 }}>автор: {HANDLE}</div>
      </div>
    </AbsoluteFill>
  );
};
