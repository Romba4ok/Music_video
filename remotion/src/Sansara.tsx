import React from "react";
import { AbsoluteFill, Easing, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Audio } from "@remotion/media";
import { ThreeCanvas } from "@remotion/three";
import { loadFont } from "@remotion/google-fonts/Manrope";

const { fontFamily } = loadFont("normal", { weights: ["500", "700", "800"], subsets: ["cyrillic", "latin"] });

// "widgets" card style of the pipeline (hook on top, phone square 1080x1080 at y=420, island, card per phrase,
// cap under the picture, author pill, title, progress bar, title end card) with every object built in Remotion.
// Fragment = chorus of "Баста — Сансара"; times are SONG seconds from whisper. Lyrics are never drawn, they only time the cards:
//   102.3 "Когда меня не станет" · 106.4 "Я буду петь голосами" · 111.5 "Моих детей и голосами их детей"
//   116.1 "Нас просто меняют местами" · 118.9 "Таков закон сансары" · 124.2 "Круговорот людей, ой, мама"
export const S = 102.1;
export const AUDIO_END = 128.6;
const TAIL = 2.5;
export const DURATION = Math.round((AUDIO_END - S + TAIL) * 30);
const TITLE = "Сансара";
const ARTIST = "Баста";
const HANDLE = "vybex";
const HOOK = "КТО ПОЁТ ПОСЛЕ НАС?";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
export const lin = (x: number) => x;
export const seg = (t: number, a: number, b: number, easing: (x: number) => number = Easing.inOut(Easing.cubic)) =>
  interpolate(t, [a, b], [0, 1], { ...clamp, easing });
export const rnd = (i: number, k = 0) => {
  const x = Math.sin(i * 127.1 + k * 311.7) * 43758.5453;
  return x - Math.floor(x);
};

export const INK = "#1d1b2e";
export const PURPLE = "#5b4b8a";
export const VIOLET = "#7a6be0";
export const WARM = "#f0a05a";
export const COOL = "#4aa8d8";
export const ROSE = "#ef8f9a";

// ---------- 2D objects ----------
export const Bust: React.FC<{ x: number; y: number; s: number; color: string; opacity?: number }> = ({ x, y, s, color, opacity = 1 }) => (
  <g transform={`translate(${x} ${y}) scale(${s})`} fill={color} opacity={opacity}>
    <circle cx={0} cy={-112} r={32} />
    <path d="M-62 0 C-62 -62 -36 -84 0 -84 C36 -84 62 -62 62 0 Z" />
  </g>
);
// full body, feet at (x,y), height h (px)
export const Person: React.FC<{ x: number; y: number; h: number; color: string; opacity?: number }> = ({ x, y, h, color, opacity = 1 }) => (
  <g transform={`translate(${x} ${y}) scale(${h})`} fill={color} opacity={opacity}>
    <circle cx={0} cy={-0.86} r={0.1} />
    <path d="M-0.15 -0.4 Q-0.15 -0.72 0 -0.72 Q0.15 -0.72 0.15 -0.4 L0.12 -0.4 L0.12 0 L0.02 0 L0.02 -0.3 L-0.02 -0.3 L-0.02 0 L-0.12 0 L-0.12 -0.4 Z" />
  </g>
);
const Ripples: React.FC<{ x: number; y: number; u: number; from: number; max: number; color: string }> = ({ x, y, u, from, max, color }) => {
  if (u < from) return null;
  return (
    <>
      {[0, 1, 2].map((k) => {
        const p = ((((u - from) / 1.5 + k / 3) % 1) + 1) % 1;
        return <circle key={k} cx={x} cy={y} r={20 + max * p} fill="none" stroke={color} strokeWidth={4} opacity={(1 - p) * 0.6} />;
      })}
    </>
  );
};

type PicProps = { u: number; d: number; t: number };

// ---------- pictures (850x350), one per phrase ----------
const PicPhoto: React.FC<PicProps> = ({ u, d }) => {
  const dis = seg(u, 0.35 * d, 0.9 * d);
  return (
    <svg width={850} height={350}>
      <rect width={850} height={350} fill="#f1e6f7" />
      <circle cx={140} cy={90} r={46} fill="#fbd9a8" />
      <g transform="translate(425 175) rotate(-4)">
        <rect x={-150} y={-160} width={300} height={320} rx={14} fill="#fff" style={{ filter: "drop-shadow(0 10px 18px rgba(60,40,110,.25))" }} />
        <rect x={-125} y={-135} width={250} height={215} rx={6} fill="#cfe3ff" />
        <circle cx={70} cy={-95} r={22} fill="#fff6d6" />
        <Bust x={0} y={80} s={1.35} color={PURPLE} opacity={1 - dis} />
        {Array.from({ length: 22 }, (_, i) => {
          const k = dis * (1 - rnd(i) * 0.3);
          if (dis <= 0) return null;
          return <circle key={i} cx={(rnd(i, 1) - 0.5) * 140 + Math.sin(u * 2 + i) * 10} cy={30 - rnd(i, 2) * 90 - k * (80 + rnd(i, 3) * 90)}
            r={3 + rnd(i, 4) * 5} fill={PURPLE} opacity={Math.max(0, 1 - dis) * 0.9 + (dis > 0.2 ? 0.3 * (1 - dis) : 0)} />;
        })}
        <rect x={-110} y={104} width={170} height={10} rx={5} fill="#ded6ea" />
        <rect x={-110} y={126} width={110} height={10} rx={5} fill="#ded6ea" />
      </g>
    </svg>
  );
};

const PicVoice: React.FC<PicProps> = ({ u, d }) => {
  const reveal = seg(u, 0.1 * d, 0.7 * d);
  return (
    <svg width={850} height={350}>
      <rect width={850} height={350} fill="#fbe8de" />
      <Bust x={190} y={335} s={1.5} color={PURPLE} />
      <Ripples x={190} y={160} u={u} from={0.15} max={230} color={VIOLET} />
      {Array.from({ length: 24 }, (_, i) => {
        const x = 400 + i * 17.5;
        if ((x - 400) / 420 > reveal) return null;
        const h = 30 + 120 * Math.abs(Math.sin(u * 5 + i * 0.55)) * (0.55 + 0.45 * Math.sin(i * 0.4 + 1));
        return <rect key={i} x={x} y={175 - h / 2} width={11} height={h} rx={5.5} fill={i % 2 ? VIOLET : ROSE} />;
      })}
    </svg>
  );
};

const PicFamily: React.FC<PicProps> = ({ u, d }) => {
  const a1 = seg(u, 0.1 * d, 0.1 * d + 0.5, Easing.out(Easing.back(1.5)));
  const a2 = seg(u, 0.38 * d, 0.38 * d + 0.5, Easing.out(Easing.back(1.5)));
  return (
    <svg width={850} height={350}>
      <rect width={850} height={350} fill="#e3f3e8" />
      <rect x={0} y={318} width={850} height={32} fill="#cfe7d6" />
      <Bust x={150} y={325} s={1.45} color={PURPLE} opacity={0.38} />
      <path d="M215 150 Q290 70 365 150" fill="none" stroke={PURPLE} strokeWidth={4} strokeDasharray="4 12" strokeLinecap="round" opacity={a1} />
      <path d="M455 150 Q530 90 605 150" fill="none" stroke={PURPLE} strokeWidth={4} strokeDasharray="4 12" strokeLinecap="round" opacity={a2} />
      <Bust x={420} y={325} s={1.2 * a1} color={WARM} opacity={a1} />
      <Ripples x={420} y={205} u={u} from={0.1 * d} max={150} color={WARM} />
      <Bust x={690} y={325} s={0.95 * a2} color={COOL} opacity={a2} />
      <Ripples x={690} y={225} u={u} from={0.38 * d} max={130} color={COOL} />
    </svg>
  );
};

const PicSwap: React.FC<PicProps> = ({ u, d }) => {
  const p = seg(u, 0.25 * d, 0.85 * d);
  const x1 = 230 + 390 * p, x2 = 620 - 390 * p;
  return (
    <svg width={850} height={350}>
      <rect width={850} height={350} fill="#fde9ea" />
      <rect x={0} y={318} width={850} height={32} fill="#f6d3d6" />
      <path d="M260 120 Q425 20 590 120" fill="none" stroke={PURPLE} strokeWidth={4} strokeDasharray="4 12" strokeLinecap="round" />
      <path d="M590 250 Q425 330 260 250" fill="none" stroke={PURPLE} strokeWidth={4} strokeDasharray="4 12" strokeLinecap="round" />
      <Person x={x2} y={318 + 24 * Math.sin(Math.PI * p)} h={250} color={COOL} />
      <Person x={x1} y={318 - 60 * Math.sin(Math.PI * p)} h={250} color={WARM} />
    </svg>
  );
};

const KnotColors = { knot: VIOLET, glow: "#5b3ee0" };
const PicWheel: React.FC<PicProps> = ({ u, d, t }) => {
  const pulse = Math.exp(-u * 4);
  const ang = 0.5 * u + 0.12 * u * u;
  const ring = (r: number, n: number, tilt: [number, number, number], dir: number) => (
    <group rotation={tilt}>
      {Array.from({ length: n }, (_, k) => {
        const a = (k / n) * Math.PI * 2 + dir * ang * 0.8;
        return (
          <mesh key={k} position={[Math.cos(a) * r, Math.sin(a) * r, 0]}>
            <sphereGeometry args={[k % 2 ? 0.11 : 0.16, 24, 24]} />
            <meshStandardMaterial color={k % 2 ? COOL : WARM} emissive={k % 2 ? "#3a8cff" : "#ff7a1a"} emissiveIntensity={0.5} />
          </mesh>
        );
      })}
      <mesh>
        <torusGeometry args={[r, 0.014, 12, 200]} />
        <meshStandardMaterial color="#9a8fdc" />
      </mesh>
    </group>
  );
  void t; void d;
  return (
    <div style={{ position: "relative", width: 850, height: 350, background: "#e6e1fb" }}>
      <ThreeCanvas width={850} height={350} camera={{ fov: 40, position: [0, 0, 9] }}>
        <ambientLight intensity={0.8} />
        <directionalLight position={[3, 4, 5]} intensity={2.2} color="#fff4e6" />
        <pointLight position={[-4, -2, 4]} intensity={50} color="#8fb8ff" />
        <group scale={1.25 * (1 + 0.07 * pulse)}>
          <mesh rotation={[ang * 0.6, ang, 0]}>
            <torusKnotGeometry args={[0.9, 0.27, 220, 24, 2, 3]} />
            <meshStandardMaterial color={KnotColors.knot} emissive={KnotColors.glow} emissiveIntensity={0.12 + 0.5 * pulse} metalness={0.3} roughness={0.35} />
          </mesh>
          {ring(1.9, 8, [Math.PI / 2.4, 0, ang * 0.5], 1)}
          {ring(2.45, 12, [-Math.PI / 3, Math.PI / 5, -ang * 0.4], -1)}
        </group>
      </ThreeCanvas>
    </div>
  );
};

const PicOrbit: React.FC<PicProps> = ({ u }) => {
  const CX = 425, CY = 235, RX = 320, RY = 62;
  const items = [
    { base: 0, h: 200, color: WARM },
    { base: Math.PI / 2, h: 140, color: WARM },
    { base: Math.PI, h: 200, color: COOL },
    { base: (3 * Math.PI) / 2, h: 140, color: COOL },
  ].map((o) => {
    const a = o.base + 0.55 * u;
    return { ...o, a, depth: (Math.sin(a) + 1) / 2, x: CX + RX * Math.cos(a), y: CY + RY * Math.sin(a) };
  }).sort((p, q) => Math.sin(p.a) - Math.sin(q.a));
  return (
    <svg width={850} height={350}>
      <rect width={850} height={350} fill="#def3f2" />
      <ellipse cx={CX} cy={CY} rx={RX} ry={RY} fill="rgba(74,168,216,0.10)" />
      <ellipse cx={CX} cy={CY} rx={RX} ry={RY} fill="none" stroke={PURPLE} strokeWidth={4} strokeDasharray="4 14" strokeLinecap="round" strokeDashoffset={-u * 40} />
      {items.map((o, i) => (
        <Person key={i} x={o.x} y={o.y} h={o.h * (0.62 + 0.38 * o.depth)} color={o.color} opacity={0.6 + 0.4 * o.depth} />
      ))}
    </svg>
  );
};

type Card = { start: number; app: string; cat: string; color: string; notify: string; Pic: React.FC<PicProps> };
const CARDS: Card[] = [
  { start: 102.1, app: "Галерея", cat: "старая фотография", color: ROSE, notify: "фото выцветает", Pic: PicPhoto },
  { start: 106.4, app: "Музыка", cat: "остаётся в эфире", color: WARM, notify: "голос звучит дальше", Pic: PicVoice },
  { start: 111.5, app: "Семья", cat: "дети и внуки", color: "#5fbf7f", notify: "поют уже они", Pic: PicFamily },
  { start: 116.1, app: "Смена", cat: "меняемся местами", color: "#e0575b", notify: "места заняты другими", Pic: PicSwap },
  { start: 118.9, app: "Круг", cat: "закон сансары", color: VIOLET, notify: "всё повторяется", Pic: PicWheel },
  { start: 124.2, app: "Карты", cat: "маршрут по кругу", color: "#3fb7c4", notify: "маршрут по кругу", Pic: PicOrbit },
];
const endOf = (i: number) => (i + 1 < CARDS.length ? CARDS[i + 1].start : AUDIO_END);

const mmss = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

// ---------- the video ----------
export const Sansara: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = S + frame / fps;
  const el = Math.min(t, AUDIO_END) - S;
  const frag = AUDIO_END - S;

  const uiOut = seg(t, 126.8, 127.5);
  const endIn = seg(t, 127.2, 128.1);
  const active = CARDS.reduce((m, c, i) => (t >= c.start ? i : m), 0);
  const notif = CARDS.map((c, i) => ({ i, n: seg(t - c.start, 0.5, 0.65) * (1 - seg(t - c.start, 1.9, 2.05)) })).reduce((m, x) => (x.n > m.n ? x : m), { i: 0, n: 0 });
  const vol = (f: number) => {
    const ts = S + f / fps;
    return Math.min(seg(ts, S, S + 0.25, lin), 1 - seg(ts, 127.4, AUDIO_END, lin));
  };
  const hookOp = seg(t, S, S + 0.3) * (1 - seg(t, S + 2.0, S + 2.4));

  return (
    <AbsoluteFill style={{ background: "#000", fontFamily, color: "#fff" }}>
      <Audio src={staticFile("sansara.mp3")} trimBefore={Math.round(S * fps)} volume={vol} />

      {/* hook in the black top field */}
      <div style={{ position: "absolute", top: 60, left: 60, right: 60, height: 300, display: "flex", alignItems: "center", justifyContent: "center", textAlign: "center",
        fontSize: 96, fontWeight: 800, lineHeight: 1.08, opacity: hookOp, transform: `translateY(${(1 - seg(t, S, S + 0.3)) * 20}px)`,
        textShadow: "0 0 10px #ff3d9a, 0 0 30px #ff3d9a, 0 0 60px rgba(255,61,154,.6)" }}>
        {HOOK}
      </div>

      {/* phone square */}
      <div style={{ position: "absolute", top: 420, left: 0, width: 1080, height: 1080, overflow: "hidden",
        background: "linear-gradient(160deg,#241552 0%,#14103a 55%,#0d0b28 100%)" }}>
        {[["#ff4fa3", 0.3], ["#4a7bff", 0.28], ["#9b5bff", 0.25]].map(([c, o], i) => (
          <div key={i} style={{ position: "absolute", width: 620, height: 620, borderRadius: "50%", background: `radial-gradient(circle, ${c} 0%, transparent 65%)`, opacity: Number(o),
            left: 100 + 360 * Math.sin(t * 0.25 + i * 2.1) + i * 80 - 300, top: 120 + 300 * Math.cos(t * 0.21 + i * 1.7) + i * 120 - 200 }} />
        ))}
        <svg width={1080} height={1080} style={{ position: "absolute", inset: 0 }}>
          {Array.from({ length: 40 }, (_, i) => {
            const x = rnd(i) * 1080, y = (((rnd(i, 1) * 1080 - t * (14 + rnd(i, 2) * 26)) % 1080) + 1080) % 1080;
            const c = ["#ff6fb5", "#6fa8ff", "#ffd166", "#7be0a5", "#b48cff"][i % 5];
            return i % 3 === 0 ? <circle key={i} cx={x} cy={y} r={4} fill={c} opacity={0.7} />
              : <g key={i} transform={`translate(${x} ${y}) rotate(${t * 40 + i * 30})`} stroke={c} strokeWidth={4} strokeLinecap="round" opacity={0.7}><path d="M-9 0H9M0 -9V9" /></g>;
          })}
        </svg>

        <div style={{ position: "absolute", inset: 0, opacity: 1 - uiOut, transform: `scale(${1 - 0.08 * uiOut})` }}>
          {/* status bar */}
          <div style={{ position: "absolute", left: 76, top: 62, fontSize: 34, fontWeight: 700 }}>
            19<span style={{ opacity: Math.floor(t * 2) % 2 ? 0.2 : 1 }}>:</span>47
          </div>
          <div style={{ position: "absolute", right: 76, top: 66, width: 62, height: 30, borderRadius: 15, border: "3px solid #fff", boxSizing: "border-box", padding: 3 }}>
            <div style={{ width: `${80 - el * 0.4}%`, height: "100%", borderRadius: 10, background: "#fff" }} />
          </div>

          {/* island: music <-> notification */}
          <div style={{ position: "absolute", left: "50%", top: 45, width: 560 + 40 * notif.n, height: 92, marginLeft: -(280 + 20 * notif.n), borderRadius: 46, background: "#08080d" }}>
            <div style={{ position: "absolute", inset: 0, opacity: 1 - notif.n, display: "flex", alignItems: "center", padding: "0 26px", gap: 16 }}>
              <div style={{ width: 54, height: 54, borderRadius: 14, background: "#23232c", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 30 }}>♪</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 28, fontWeight: 700 }}>{TITLE}</div>
                <div style={{ fontSize: 20, opacity: 0.55 }}>{ARTIST}</div>
              </div>
              <div style={{ display: "flex", alignItems: "flex-end", gap: 5, height: 36 }}>
                {[0, 1, 2, 3, 4].map((k) => <div key={k} style={{ width: 7, borderRadius: 3, background: "#34d17b", height: 10 + 24 * Math.abs(Math.sin(t * (3 + k) + k * 1.3)) }} />)}
              </div>
            </div>
            <div style={{ position: "absolute", inset: 0, opacity: notif.n, display: "flex", alignItems: "center", padding: "0 26px", gap: 16 }}>
              <div style={{ width: 54, height: 54, borderRadius: 14, background: CARDS[notif.i].color }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 26, fontWeight: 700 }}>{CARDS[notif.i].app}</div>
                <div style={{ fontSize: 21, opacity: 0.7 }}>{CARDS[notif.i].notify}</div>
              </div>
              <div style={{ fontSize: 18, opacity: 0.5 }}>сейчас</div>
            </div>
          </div>

          {/* cards */}
          {CARDS.map((c, i) => {
            const next = endOf(i), d = next - c.start, u = t - c.start;
            if (u < 0 || t > next + 0.6) return null;
            const a = seg(u, 0, 0.38, Easing.out(Easing.cubic));
            const w = t > next && i < CARDS.length - 1 ? Math.min(1, (t - next) / 0.6) : 0;
            const idle = Math.sin((t * 2 * Math.PI) / 5.2) * 4 * (1 - w);
            const Pic = c.Pic;
            return (
              <div key={i} style={{ position: "absolute", left: 75, top: 190, width: 930, height: 500, borderRadius: 56, background: "rgba(255,255,255,0.97)", zIndex: i,
                boxShadow: "0 24px 60px rgba(0,0,0,.35)", color: INK, opacity: a * (w > 0 ? 0.5 * (1 - w) : 1), filter: `blur(${(1 - a) * 14 + 6 * w}px)`,
                transform: `translateY(${(1 - a) * 520 - 30 * w}px) perspective(1400px) rotateX(${(1 - a) * -10}deg) rotateY(${idle - (1 - a) * 8}deg) scale(${1.04 * (1 - 0.07 * w)})` }}>
                <div style={{ position: "absolute", left: 40, top: 26, display: "flex", alignItems: "center", gap: 18 }}>
                  <div style={{ width: 56, height: 56, borderRadius: 15, background: c.color, transform: `scale(${1 + 0.05 * Math.sin(t * 5)})` }} />
                  <div>
                    <div style={{ fontSize: 36, fontWeight: 800, lineHeight: 1.05 }}>{c.app}</div>
                    <div style={{ fontSize: 22, fontWeight: 700, color: VIOLET }}>{c.cat}</div>
                  </div>
                </div>
                <div style={{ position: "absolute", left: 40, top: 110, width: 850, height: 350, borderRadius: 30, overflow: "hidden" }}>
                  <Pic u={u} d={d} t={t} />
                  <div style={{ position: "absolute", inset: 0, background: `linear-gradient(105deg, transparent ${((u * 0.5) % 1.6) * 100 - 30}%, rgba(255,255,255,.35) ${((u * 0.5) % 1.6) * 100}%, transparent ${((u * 0.5) % 1.6) * 100 + 12}%)` }} />
                </div>
              </div>
            );
          })}

          {/* dots */}
          <div style={{ position: "absolute", top: 777, left: 0, right: 0, display: "flex", justifyContent: "center", gap: 14 }}>
            {CARDS.map((_, i) => <div key={i} style={{ width: i === active ? 44 : 12, height: 12, borderRadius: 6, background: i === active ? "#fff" : "rgba(255,255,255,.35)" }} />)}
          </div>

          {/* author pill, title, progress */}
          <div style={{ position: "absolute", top: 822, left: "50%", marginLeft: -170, width: 340, height: 56, borderRadius: 28, background: "rgba(255,255,255,.92)", color: INK,
            display: "flex", alignItems: "center", justifyContent: "center", fontSize: 28, fontWeight: 800 }}>
            автор: {HANDLE}
          </div>
          <div style={{ position: "absolute", top: 898, left: 0, right: 0, textAlign: "center", fontSize: 46, fontWeight: 800, transform: `translateY(${Math.sin(t * 1.5) * 3}px)` }}>
            {ARTIST} — {TITLE}
          </div>
          <div style={{ position: "absolute", top: 985, left: 165, width: 750, height: 7, borderRadius: 4, background: "rgba(255,255,255,.3)" }}>
            <div style={{ width: `${(el / frag) * 100}%`, height: "100%", borderRadius: 4, background: "#fff" }} />
            <div style={{ position: "absolute", left: `${(el / frag) * 100}%`, top: -6, width: 19, height: 19, marginLeft: -9, borderRadius: "50%", background: "#fff" }} />
          </div>
          <div style={{ position: "absolute", top: 1008, left: 165, fontSize: 24, opacity: 0.7 }}>{mmss(el)}</div>
          <div style={{ position: "absolute", top: 1008, right: 165, fontSize: 24, opacity: 0.7 }}>-{mmss(frag - el)}</div>
        </div>

        {/* title end card */}
        <div style={{ position: "absolute", inset: 0, opacity: endIn, transform: `scale(${0.92 + 0.08 * endIn})`, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
          <div style={{ position: "relative", width: 240, height: 240, marginBottom: 40 }}>
            <svg width={240} height={240} style={{ position: "absolute", inset: 0, overflow: "visible" }}>
              {Array.from({ length: 28 }, (_, i) => {
                const a = (i / 28) * Math.PI * 2 + t * 0.6;
                const c = ["#ff6fb5", "#6fa8ff", "#ffd166", "#7be0a5", "#b48cff"][i % 5];
                return <circle key={i} cx={120 + Math.cos(a) * 170} cy={120 + Math.sin(a) * 170} r={i % 2 ? 6 : 4} fill={c} />;
              })}
            </svg>
            <div style={{ position: "absolute", inset: 20, borderRadius: 52, background: `linear-gradient(135deg, ${VIOLET}, #ff6fb5)`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 110 }}>♪</div>
          </div>
          <div style={{ fontSize: 140, fontWeight: 800 }}>{TITLE}</div>
          <div style={{ fontSize: 60, fontWeight: 700, opacity: 0.8, marginTop: 6 }}>{ARTIST}</div>
          <div style={{ marginTop: 36, padding: "10px 34px", borderRadius: 40, background: "rgba(255,255,255,.92)", color: INK, fontSize: 32, fontWeight: 800 }}>автор: {HANDLE}</div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
