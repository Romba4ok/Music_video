import React from "react";
import { AbsoluteFill, Easing, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Audio } from "@remotion/media";
import { loadFont } from "@remotion/google-fonts/Manrope";
import { lin, rnd, seg } from "./Sansara";

const { fontFamily } = loadFont("normal", { weights: ["500", "700", "800"], subsets: ["cyrillic", "latin"] });

// Style study of a TikTok author's clips, WITHOUT any subtitles: one fixed cinematic angle (night room), props that tell each line,
// a new metaphor per lyric line, drifting particles, author pill. Lyrics are never drawn, they only time the scenes.
// "Сплин — Романс", fragment 92.4–123.6 s, line times = whisper (large-v3 pass) on the supplied mp3:
//   92.9 "На площади полки" (ranks in the square) · 98.5 "Темно в конце строки" (lights go out) · 103.3 "И в телефонной трубке" (handset lifts)
//   106.8 "Эти много лет спустя" (clock, calendar sheets) · 109.2 "Одни гудки" (beep rings) · 111.5 "И где-то хлопнет дверь" (door slams at 116.3)
//   119.6 "И дрогнут провода" (wires tremble, birds fly)
const S = 92.4;
const AUDIO_END = 123.6;
export const VIBE_DURATION = Math.round((AUDIO_END - S + 2.4) * 30);
const TITLE = "Романс";
const ARTIST = "Сплин";
const HANDLE = "vybex";
const SLAM = 116.3;

const clamp01 = (x: number) => Math.max(0, Math.min(1, x));
const WALL = "#171a30", WARM = "#ffcf8a", COOL = "#8fd0ff", RED = "#b3263e";
const back = Easing.out(Easing.back(1.6));

export const Vibe: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = S + frame / fps;
  const el = Math.min(t, AUDIO_END) - S;
  const on = (a: number, b: number) => seg(t, a, a + 0.5) * (1 - seg(t, b - 0.4, b));

  const dark = seg(t, 98.4, 100.2);                       // "Темно": whole room dims
  const lamp = (1 - seg(t, 98.4, 98.9)) * (t > 98.4 && t < 98.9 ? 0.5 + 0.5 * Math.sin(t * 70) : 1);
  const lift = seg(t, 103.3, 104.2, back);                // handset lifts
  const slamT = t - SLAM;
  const theta = t < 115.7 ? 62 + 3 * Math.sin(t * 1.3)
    : t < SLAM ? 62 * (1 - Easing.in(Easing.cubic)(seg(t, 115.7, SLAM, lin)))
    : 3 * Math.exp(-slamT * 6) * Math.abs(Math.cos(slamT * 22));
  const flash = slamT > 0 ? 0.35 * Math.exp(-slamT * 14) : 0;
  const shake = slamT > 0 ? 24 * Math.exp(-slamT * 9) : 0;
  const trem = t > 119.6 ? 26 * Math.exp(-(t - 119.6) * 0.9) : slamT > 0 ? 5 * Math.exp(-slamT * 3) : 0;
  const fly = seg(t, 120.0, 122.4);
  const endIn = seg(t, AUDIO_END - 0.2, AUDIO_END + 0.7);
  const vol = (f: number) => {
    const ts = S + f / fps;
    return Math.min(seg(ts, S, S + 0.12, lin), 1 - seg(ts, AUDIO_END - 1.0, AUDIO_END, lin));
  };

  // ---- window pieces (window x60..700, y260..1000) ----
  const buildings = Array.from({ length: 9 }, (_, i) => ({ x: 60 + i * 74, w: 70, h: 150 + rnd(i, 1) * 260 }));
  const wireY = [430, 500, 570];
  const wire = (i: number, sag: number) => {
    const y0 = wireY[i], y1 = wireY[i] - 40 + i * 10;
    const cy = (y0 + y1) / 2 + sag + trem * Math.sin(t * 34 + i * 1.7);
    return { d: `M60 ${y0} Q380 ${cy} 700 ${y1}`, y0, y1, cy };
  };
  const onWire = (i: number, u: number) => { const w = wire(i, 70); const a = (1 - u) ** 2, b = 2 * u * (1 - u), c = u * u; return { x: 60 + 640 * u, y: a * w.y0 + b * w.cy + c * w.y1 }; };
  const birds = [[0, 0.22], [0, 0.31], [1, 0.62], [2, 0.45]];

  // ---- door (x780..1020, y220..1120), hinge on the right ----
  const c = Math.cos((theta * Math.PI) / 180), grow = 60 * (1 - c);
  const doorPts = `${1020 - 240 * c},${220 - grow} 1020,220 1020,1120 ${1020 - 240 * c},${1120 + grow}`;
  const spill = clamp01(theta / 62);

  // ---- phone (desk) ----
  const hy = 1330 - 130 * lift, hr = -9 * lift + (t > 109.1 && t < 111.6 ? 1.6 * Math.sin(t * 60) : 0);
  const cordSag = 40 + 30 * lift + 6 * Math.sin(t * 4);
  const dial = (seg(t, 103.9, 104.8) - seg(t, 105.0, 105.8)) * 150;

  return (
    <AbsoluteFill style={{ fontFamily, background: "#07080f" }}>
      <Audio src={staticFile("romans.mp3")} trimBefore={Math.round(S * fps)} volume={vol} />
      <div style={{ position: "absolute", inset: 0, transform: `translate(${Math.sin(t * 90) * shake}px, ${Math.cos(t * 77) * shake}px) scale(${1.02 + 0.07 * (el / (AUDIO_END - S))})` }}>
        <svg width={1080} height={1920} style={{ position: "absolute", inset: 0 }}>
          <defs>
            <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#0d1230" /><stop offset="1" stopColor="#3a2a55" /></linearGradient>
            <linearGradient id="desk" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#3a2620" /><stop offset="1" stopColor="#150d0b" /></linearGradient>
            <linearGradient id="hall" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#ffe3ae" /><stop offset="1" stopColor="#ffb866" /></linearGradient>
            <radialGradient id="glow"><stop offset="0" stopColor={COOL} stopOpacity=".55" /><stop offset="1" stopColor={COOL} stopOpacity="0" /></radialGradient>
            <linearGradient id="cone" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={WARM} stopOpacity=".5" /><stop offset="1" stopColor={WARM} stopOpacity="0" /></linearGradient>
            <clipPath id="win"><rect x={60} y={260} width={640} height={740} /></clipPath>
          </defs>

          {/* wall */}
          <rect width={1080} height={1920} fill={WALL} />
          {Array.from({ length: 13 }, (_, i) => <rect key={i} x={i * 90} y={0} width={4} height={1180} fill="#fff" opacity={0.035} />)}

          {/* window content */}
          <g clipPath="url(#win)">
            <rect x={60} y={260} width={640} height={740} fill="url(#sky)" />
            <circle cx={560} cy={380} r={90} fill="#fff6d8" opacity={0.12} /><circle cx={560} cy={380} r={46} fill="#fff6d8" opacity={0.9} />
            {buildings.map((b, i) => (
              <g key={i}>
                <rect x={b.x} y={1000 - b.h} width={b.w} height={b.h} fill="#0a0b16" />
                {Array.from({ length: Math.floor(b.h / 48) * 3 }, (_, k) => {
                  const col = k % 3, row = Math.floor(k / 3);
                  const lit = rnd(i * 40 + k, 1) < 0.55 && rnd(i * 40 + k, 2) > dark;
                  return lit ? <rect key={k} x={b.x + 8 + col * 21} y={1000 - b.h + 14 + row * 48} width={13} height={20} fill={WARM} opacity={0.85} /> : null;
                })}
              </g>
            ))}
            {/* 1. ranks on the square */}
            <g opacity={on(92.4, 98.4)}>
              <rect x={60} y={900} width={640} height={100} fill="#5a5388" opacity={0.9} />
              <rect x={60} y={900} width={640} height={6} fill="#c9c3ff" opacity={0.6} />
              {Array.from({ length: 13 }, (_, i) => {
                const x = 80 + i * 52 - ((t - 92.4) * 14) % 52, bob = Math.sin(t * 6.2 + i) * 3;
                return <g key={i} transform={`translate(${x} ${bob})`} fill="#05060c"><circle cx={0} cy={880} r={10} /><rect x={-10} y={890} width={20} height={52} rx={5} /><rect x={12} y={850} width={4} height={80} /></g>;
              })}
              {[0, 1].map((k) => <g key={k}><rect x={170 + k * 300} y={780} width={4} height={160} fill="#05060c" />
                <path d={`M174 784 Q${200 + 6 * Math.sin(t * 5 + k)} ${796} ${232} ${790 + 4 * Math.sin(t * 5 + k)} L232 830 Q${204} ${838} 174 826 Z`} fill={RED} /></g>)}
            </g>
            {/* 4. clock + calendar sheets */}
            <g opacity={on(106.7, 109.2)}>
              <circle cx={380} cy={620} r={190} fill="#0b0c18" opacity={0.85} stroke="#e8e1ff" strokeWidth={8} />
              {Array.from({ length: 12 }, (_, i) => <line key={i} x1={380} y1={450} x2={380} y2={i % 3 ? 466 : 480} stroke="#e8e1ff" strokeWidth={i % 3 ? 4 : 8} transform={`rotate(${i * 30} 380 620)`} />)}
              <line x1={380} y1={620} x2={380} y2={485} stroke="#e8e1ff" strokeWidth={9} strokeLinecap="round" transform={`rotate(${(t - 106.7) * 900} 380 620)`} />
              <line x1={380} y1={620} x2={380} y2={540} stroke={WARM} strokeWidth={13} strokeLinecap="round" transform={`rotate(${(t - 106.7) * 75} 380 620)`} />
              {Array.from({ length: 9 }, (_, i) => {
                const p = clamp01(((t - 106.7) * 0.8 + rnd(i, 4)) % 1);
                return <rect key={i} x={110 + rnd(i, 5) * 500} y={1000 - p * 760} width={44} height={56} rx={4} fill="#f3efe6" opacity={0.85 * (1 - p)} transform={`rotate(${p * 200 * (i % 2 ? 1 : -1)} ${132 + rnd(i, 5) * 500} ${1030 - p * 760})`} />;
              })}
            </g>
            {/* wires + birds */}
            {[0, 1, 2].map((i) => <path key={i} d={wire(i, 70).d} stroke="#05060c" strokeWidth={4} fill="none" />)}
            {birds.map(([wi, u], k) => {
              const p = onWire(wi, u), f = fly * (1 + 0.3 * k);
              const x = p.x + f * 260, y = p.y - 9 - f * 380 + Math.sin(t * 20 + k) * 6 * f;
              return <g key={k} transform={`translate(${x} ${y})`} opacity={1 - clamp01((f - 0.6) / 0.4)} fill="#05060c"><ellipse rx={13} ry={9} /><circle cx={11} cy={-6} r={6} /><path d={`M-10 0 L-24 ${-2 - f * 14 * Math.sin(t * 25)} L-10 6Z`} /></g>;
            })}
            {/* rain */}
            {Array.from({ length: 46 }, (_, i) => {
              const p = (t * (1.1 + rnd(i, 1) * 0.6) + rnd(i, 2)) % 1, x = 60 + rnd(i, 3) * 700 - p * 60, y = 260 + p * 800;
              return <line key={i} x1={x} y1={y} x2={x - 9} y2={y + 34} stroke="#bcd3ff" strokeWidth={2} opacity={0.3} />;
            })}
            <polygon points="60,260 260,260 60,700" fill="#fff" opacity={0.04} />
          </g>
          <rect x={60} y={260} width={640} height={740} fill="none" stroke="#06070f" strokeWidth={26} />
          <rect x={373} y={260} width={14} height={740} fill="#06070f" /><rect x={60} y={620} width={640} height={14} fill="#06070f" />

          {/* door + hallway light */}
          <rect x={780} y={220} width={240} height={900} fill="#0a0b14" />
          <rect x={780} y={220} width={240} height={900} fill="url(#hall)" opacity={spill * (0.85 + 0.1 * Math.sin(t * 9))} />
          <polygon points={doorPts} fill="#2b2d52" stroke="#05060c" strokeWidth={8} />
          <polygon points={`${1020 - 240 * c + 30 * c},${300} ${1000},300 ${1000},560 ${1020 - 240 * c + 30 * c},${560 + grow * 0.3}`} fill="none" stroke="#3d4075" strokeWidth={6} opacity={0.8} />
          <circle cx={1020 - 240 * c + 26 * c} cy={700} r={10} fill={WARM} />
          <polygon points={`780,1120 1020,1120 ${1020 + 160 * spill},1330 ${700 - 40 * spill},1330`} fill={WARM} opacity={0.22 * spill} />

          {/* desk */}
          <rect x={0} y={1150} width={1080} height={770} fill="url(#desk)" />
          <rect x={0} y={1150} width={1080} height={8} fill="#7a5848" opacity={0.7} />
          {/* lamp */}
          <g opacity={1}>
            <polygon points="220,1190 60,1500 420,1500" fill="url(#cone)" opacity={lamp * (1 - 0.8 * dark)} />
            <ellipse cx={140} cy={1180} rx={70} ry={14} fill="#0a0a10" />
            <path d="M140 1180 L170 1010 L270 940" stroke="#0a0a10" strokeWidth={12} fill="none" strokeLinecap="round" />
            <path d="M230 930 L310 920 L290 980 Z" fill="#14141f" /><circle cx={265} cy={968} r={10} fill={WARM} opacity={lamp} />
          </g>
          {/* room dims, the window stays lit so its scenes stay readable */}
          <path d="M0 0H1080V1920H0Z M60 260H700V1000H60Z" fillRule="evenodd" fill="#02030a" opacity={0.6 * dark} />

          {/* phone, scaled up */}
          <g transform="translate(540 1560) scale(1.4) translate(-480 -1450)">
          <circle cx={480} cy={1400} r={360} fill="url(#glow)" opacity={seg(t, 102.8, 104) * (1 - seg(t, 119.6, 121.5) * 0.7)} />
          <g>
            <path d={`M290 1400 Q${200 - cordSag * 0.3} ${1380 + cordSag} 320 ${hy + 10}`} stroke="#0a0a10" strokeWidth={7} fill="none" strokeDasharray="2 9" strokeLinecap="round" />
            <path d="M270 1560 Q480 1380 690 1560 L690 1640 Q480 1690 270 1640 Z" fill={RED} stroke="#05060c" strokeWidth={6} />
            <circle cx={480} cy={1520} r={84} fill="#0c0c14" />
            <g transform={`rotate(${dial} 480 1520)`}>{Array.from({ length: 10 }, (_, i) => <circle key={i} cx={480 + 54 * Math.cos(-0.5 - i * 0.5)} cy={1520 + 54 * Math.sin(-0.5 - i * 0.5)} r={11} fill="#e9e4d6" />)}</g>
            <circle cx={480} cy={1520} r={18} fill="#cfc8b4" />
            <rect x={395} y={1362} width={22} height={34} rx={6} fill="#05060c" /><rect x={543} y={1362} width={22} height={34} rx={6} fill="#05060c" />
            <g transform={`rotate(${hr} 480 ${hy})`}>
              <rect x={330} y={hy - 20} width={300} height={40} rx={20} fill="#0c0c14" stroke={RED} strokeWidth={4} />
              <rect x={312} y={hy - 34} width={72} height={68} rx={26} fill="#0c0c14" stroke={RED} strokeWidth={4} /><rect x={576} y={hy - 34} width={72} height={68} rx={26} fill="#0c0c14" stroke={RED} strokeWidth={4} />
            </g>
            {Array.from({ length: 3 }, (_, k) => {
              const p = (((t - 109.16) / 0.8 + k / 3) % 1 + 1) % 1;
              return <circle key={k} cx={480} cy={hy} r={60 + 280 * p} fill="none" stroke={COOL} strokeWidth={6 * (1 - p)} opacity={(1 - p) * 0.7 * on(109.16, 111.6)} />;
            })}
          </g>
          </g>

          {/* particles: dust always, burst on slam */}
          {Array.from({ length: 44 }, (_, i) => {
            const y = (((rnd(i, 2) * 1920 - t * (10 + rnd(i, 3) * 22)) % 1920) + 1920) % 1920;
            return <circle key={i} cx={rnd(i, 1) * 1080 + Math.sin(t * 0.4 + i) * 30} cy={y} r={2 + rnd(i, 4) * 3} fill="#f6e2b8" opacity={0.18 + 0.12 * Math.sin(t + i)} />;
          })}
          {slamT > 0 && slamT < 1.6 && Array.from({ length: 26 }, (_, i) => {
            const a = rnd(i, 7) * Math.PI * 2, v = 160 + rnd(i, 8) * 420, p = Easing.out(Easing.cubic)(slamT / 1.6);
            return <circle key={i} cx={940 + Math.cos(a) * v * p} cy={700 + Math.sin(a) * v * p + 120 * p * p} r={4 + rnd(i, 9) * 8} fill={i % 3 ? "#f6e2b8" : "#05060c"} opacity={1 - p} />;
          })}
        </svg>
        <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 50%, transparent 45%, rgba(0,0,0,.55) 100%)" }} />
        <div style={{ position: "absolute", inset: 0, background: "#fff", opacity: flash }} />
      </div>

      {/* author pill (fixed, not part of the camera) */}
      <div style={{ position: "absolute", top: 96, right: 56, padding: "12px 28px", borderRadius: 40, background: "rgba(10,12,28,.6)", border: "2px solid rgba(143,208,255,.45)", color: "#fff", fontSize: 30, fontWeight: 800, opacity: 1 - endIn }}>
        автор: {HANDLE}
      </div>

      {/* end card */}
      <div style={{ position: "absolute", inset: 0, opacity: endIn, background: "#07080f", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", color: "#fff", transform: `scale(${0.94 + 0.06 * endIn})` }}>
        <div style={{ fontSize: 120, fontWeight: 800 }}>{TITLE}</div>
        <div style={{ fontSize: 60, fontWeight: 700, opacity: 0.6, marginTop: 10 }}>{ARTIST}</div>
        <div style={{ marginTop: 40, padding: "10px 34px", borderRadius: 40, background: "rgba(143,208,255,.18)", fontSize: 32, fontWeight: 800 }}>автор: {HANDLE}</div>
      </div>
    </AbsoluteFill>
  );
};
