import React from "react";
import { AbsoluteFill, Easing, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Audio } from "@remotion/media";
import { ThreeCanvas } from "@remotion/three";
import { loadFont } from "@remotion/google-fonts/Manrope";
import { Bust, COOL, INK, lin, Person, ROSE, rnd, seg, VIOLET, WARM } from "./Sansara";

const { fontFamily } = loadFont("normal", { weights: ["500", "700", "800"], subsets: ["cyrillic", "latin"] });

// "Т9 — Ода нашей любви", fragment 92.2–118.5 s (declaration + chorus). Times are SONG seconds, large-v3 whisper on the supplied mp3.
// Style idea from the two reference clips only (light pastel gradient full-bleed, island with the song, white tilted card per phrase,
// UI details inside the card); all scenes and objects are our own. Lyrics are not drawn, they only time the cards.
//   92.2 "Ты любовь моя, ты печаль моя" · 95.5 "И если вдруг исчезнешь…" · 98.6 "…как первый лучик солнца весной"
//   102.3 "И я люблю тебя, и я весь твой" · 105.4 "Вдох, выдох, и мы опять играем в любимых" · 109.0 "Пропадаем и тонем в нежности"
//   112.0 "Не боясь и не тая этих чувств сильных" · 115.3 "Ловим сладкие грёзы на сказочных склонах"
const S = 92.2;
const AUDIO_END = 118.5;
export const T9_DURATION = Math.round((AUDIO_END - S + 2.5) * 30);
const TITLE = "Ода нашей любви";
const ARTIST = "Т9";
const HANDLE = "vybex";
const HOOK = "ПОЧЕМУ ЛЮБОВЬ — ЭТО ВДОХ И ВЫДОХ?";

const PINK = "#ff5d8f";
const heart = (x: number, y: number, s: number) => `translate(${x} ${y}) scale(${s})`;
const HEART = "M0 0.6 C-1 -0.1 -0.6 -0.9 0 -0.35 C0.6 -0.9 1 -0.1 0 0.6 Z";

type PicProps = { u: number; d: number };

// ---------- pictures (850x350) ----------
const PicWeather: React.FC<PicProps> = ({ u, d }) => {
  const sun = 1, cloud = seg(u, 0.15 * d, 0.4 * d);
  const beat = 1 + 0.07 * Math.sin(u * 7);
  return (
    <svg width={850} height={350}>
      <defs>
        <linearGradient id="wx" x1="0" x2="1"><stop offset="0.35" stopColor="#fff0c9" /><stop offset="0.65" stopColor="#d6e3fa" /></linearGradient>
      </defs>
      <rect width={850} height={350} fill="url(#wx)" />
      <g transform="translate(170 110)" opacity={sun}>
        {Array.from({ length: 10 }, (_, i) => <line key={i} x1={0} y1={-62} x2={0} y2={-86} stroke="#ffc94d" strokeWidth={8} strokeLinecap="round" transform={`rotate(${i * 36 + u * 20})`} />)}
        <circle r={46} fill="#ffc94d" />
      </g>
      <g transform="translate(690 100)" opacity={cloud}>
        <circle cx={-40} cy={10} r={34} fill="#9db4dc" /><circle cx={0} cy={-8} r={44} fill="#9db4dc" /><circle cx={44} cy={10} r={32} fill="#9db4dc" />
        <rect x={-74} y={10} width={150} height={34} rx={17} fill="#9db4dc" />
        {Array.from({ length: 9 }, (_, i) => {
          const p = (u * 0.9 + rnd(i)) % 1;
          return <line key={i} x1={-60 + i * 15} y1={60 + p * 150} x2={-66 + i * 15} y2={78 + p * 150} stroke="#6b8fd8" strokeWidth={5} strokeLinecap="round" opacity={(1 - p) * cloud} />;
        })}
      </g>
      <g transform={heart(425, 195, 110 * beat)}><path d={HEART} fill={PINK} /></g>
    </svg>
  );
};

const PicChat: React.FC<PicProps> = ({ u, d }) => {
  const b1 = seg(u, 0.08 * d, 0.08 * d + 0.4, Easing.out(Easing.back(1.4)));
  const b2 = seg(u, 0.33 * d, 0.33 * d + 0.4, Easing.out(Easing.back(1.4)));
  const typing = seg(u, 0.02 * d, 0.12 * d) * (1 - seg(u, 0.5 * d, 0.6 * d));
  const off = seg(u, 0.55 * d, 0.62 * d);
  const err = seg(u, 0.65 * d, 0.8 * d);
  const bubble = (y: number, n: number, a: number) => (
    <g transform={`translate(${790 - 90 * a - (n === 2 ? 70 : 0)} ${y}) scale(${a})`} opacity={a} style={{ transformOrigin: "right" }}>
      <rect x={n === 2 ? -80 : -10} y={0} width={n === 2 ? 220 : 150} height={80} rx={34} fill={VIOLET} transform="translate(-70 0)" />
      {Array.from({ length: n }, (_, i) => <g key={i} transform={heart(n === 2 ? -60 + i * 75 : -5, 42, 30)}><path d={HEART} fill="#fff" /></g>)}
    </g>
  );
  return (
    <svg width={850} height={350}>
      <rect width={850} height={350} fill="#eef1fb" />
      <g transform="translate(56 30)">
        <circle r={22} cx={22} cy={22} fill="#cfd5ea" />
        <Bust x={22} y={40} s={0.17} color="#fff" />
        <text x={62} y={30} fontSize={28} fontWeight={800} fill={INK}>Ты</text>
        <circle cx={118} cy={20} r={7} fill={off > 0.5 ? "#b9bccd" : "#34c78a"} />
        <text x={134} y={29} fontSize={24} fontWeight={700} fill="#8a8ca3">{off > 0.5 ? "не в сети" : "в сети"}</text>
      </g>
      <g opacity={typing} transform="translate(60 150)">
        <rect width={130} height={70} rx={32} fill="#dfe3f2" />
        {[0, 1, 2].map((i) => <circle key={i} cx={36 + i * 29} cy={35 - 8 * Math.max(0, Math.sin(u * 8 - i))} r={8} fill="#9ea3be" />)}
      </g>
      {bubble(100, 1, b1)}
      {bubble(200, 2, b2)}
      <text x={790} y={318} textAnchor="end" fontSize={24} fontWeight={700} fill="#e0575b" opacity={err}>не доставлено</text>
    </svg>
  );
};

const PicSpring: React.FC<PicProps> = ({ u, d }) => {
  const rise = seg(u, 0, 0.35 * d);
  const g = seg(u, 0.25 * d, 0.8 * d);
  const bloom = seg(u, 0.7 * d, 0.95 * d, Easing.out(Easing.back(1.6)));
  const sx = 120 + 40 * rise, sy = 250 - 180 * rise;
  const fx = 560, fy = 300 - 170 * g;
  return (
    <svg width={850} height={350}>
      <defs><linearGradient id="sp" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#ffe9c9" /><stop offset="1" stopColor="#e4f3ff" /></linearGradient></defs>
      <rect width={850} height={350} fill="url(#sp)" />
      <polygon points={`${sx},${sy} ${fx - 70},300 ${fx + 70},300`} fill="#fff3b8" opacity={0.55 * rise} />
      <g transform={`translate(${sx} ${sy})`}>
        {Array.from({ length: 10 }, (_, i) => <line key={i} x1={0} y1={-58} x2={0} y2={-78} stroke="#ffc94d" strokeWidth={7} strokeLinecap="round" transform={`rotate(${i * 36 + u * 20})`} />)}
        <circle r={42} fill="#ffc94d" />
      </g>
      <path d="M0 320 Q220 280 430 315 T850 300 V350 H0 Z" fill="#a8d99a" />
      <line x1={fx} y1={310} x2={fx} y2={fy} stroke="#4f9d5a" strokeWidth={9} strokeLinecap="round" />
      {g > 0.3 && <ellipse cx={fx - 26} cy={fy + 70} rx={30} ry={13} fill="#6bbf6e" transform={`rotate(-25 ${fx - 26} ${fy + 70})`} />}
      {g > 0.5 && <ellipse cx={fx + 26} cy={fy + 100} rx={30} ry={13} fill="#6bbf6e" transform={`rotate(25 ${fx + 26} ${fy + 100})`} />}
      <g transform={`translate(${fx} ${fy}) scale(${bloom})`} opacity={bloom}>
        {Array.from({ length: 6 }, (_, i) => <circle key={i} cx={Math.cos((i / 6) * 6.283) * 30} cy={Math.sin((i / 6) * 6.283) * 30} r={20} fill="#ff8fb3" />)}
        <circle r={18} fill="#ffd54d" />
      </g>
    </svg>
  );
};

const PicFav: React.FC<PicProps> = ({ u, d }) => {
  const pop = seg(u, 0.2 * d, 0.2 * d + 0.5, Easing.out(Easing.back(2)));
  const fill = seg(u, 0.3 * d, 0.55 * d);
  const star = seg(u, 0.5 * d, 0.7 * d);
  return (
    <svg width={850} height={350}>
      <rect width={850} height={350} fill="#fff4dc" />
      <Bust x={190} y={340} s={1.45} color={WARM} />
      <Bust x={660} y={340} s={1.45} color={COOL} />
      <g transform={heart(425, 190, 120 * pop)}><path d={HEART} fill={PINK} fillOpacity={fill} stroke={PINK} strokeWidth={0.06} /></g>
      <path d="M425 40 l9 20 22 3 -16 15 5 22 -20 -11 -20 11 5 -22 -16 -15 22 -3 z" transform={`translate(0 -6) scale(${1})`} fill={star > 0.5 ? "#ffc94d" : "none"} stroke="#ffc94d" strokeWidth={5} strokeLinejoin="round" opacity={0.4 + 0.6 * star} />
    </svg>
  );
};

const PicBreath: React.FC<PicProps> = ({ u }) => {
  const k = 0.5 - 0.5 * Math.cos((Math.PI * u) / 1.8); // inhale 0..1.8 s, exhale 1.8..3.6 s
  const s = 0.95 + 0.4 * k;
  return (
    <div style={{ position: "relative", width: 850, height: 350, background: "#efe6fb" }}>
      <ThreeCanvas width={850} height={350} camera={{ fov: 40, position: [0, 0, 9] }}>
        <ambientLight intensity={0.9} />
        <directionalLight position={[3, 4, 5]} intensity={2.2} color="#fff4e6" />
        <pointLight position={[-4, -2, 4]} intensity={40} color="#9fc0ff" />
        <mesh scale={s}>
          <sphereGeometry args={[1.45, 64, 64]} />
          <meshStandardMaterial color="#ff9ec4" emissive="#ff6fa8" emissiveIntensity={0.2 + 0.25 * k} roughness={0.25} metalness={0.1} />
        </mesh>
        <mesh rotation={[Math.PI / 2.4, 0, u * 0.8]} scale={s * 1.1}>
          <torusGeometry args={[2.1, 0.03, 12, 160]} />
          <meshStandardMaterial color="#b9a8f0" emissive="#7a6be0" emissiveIntensity={0.5} />
        </mesh>
        {Array.from({ length: 7 }, (_, i) => {
          const a = (i / 7) * 6.283 + u * 0.8;
          return (
            <mesh key={i} position={[Math.cos(a) * 2.1 * s * 1.1, Math.sin(a) * 2.1 * s * 1.1 * Math.cos(Math.PI / 2.4), Math.sin(a) * 2.1 * s * 1.1 * Math.sin(Math.PI / 2.4)]}>
              <sphereGeometry args={[0.09, 16, 16]} />
              <meshStandardMaterial color="#fff" emissive="#ffffff" emissiveIntensity={0.6} />
            </mesh>
          );
        })}
      </ThreeCanvas>
      <svg width={850} height={350} style={{ position: "absolute", inset: 0 }}>
        <Bust x={110} y={345} s={1.15} color={WARM} />
        <Bust x={740} y={345} s={1.15} color={COOL} />
        <text x={425} y={52} textAnchor="middle" fontSize={40} fontWeight={800} fill={INK}>{u < 1.8 ? "вдох" : "выдох"}</text>
      </svg>
    </div>
  );
};

const PicDeep: React.FC<PicProps> = ({ u, d }) => {
  const p = seg(u, 0, d, lin);
  const level = 215 - 30 * p;
  const wave = (off: number, amp: number) => {
    let s = `M0 350 L0 ${level}`;
    for (let x = 0; x <= 850; x += 25) s += ` L${x} ${level + amp * Math.sin(x * 0.02 + u * 3 + off)}`;
    return s + " L850 350 Z";
  };
  return (
    <svg width={850} height={350}>
      <rect width={850} height={350} fill="#eaf4ff" />
      <Bust x={290} y={170 + 90 * p} s={1} color={WARM} />
      <Bust x={560} y={185 + 90 * p} s={1} color={COOL} />
      <path d={wave(0, 9)} fill="rgba(110,175,255,0.55)" />
      <path d={wave(2, 7)} fill="rgba(70,140,240,0.45)" />
      {Array.from({ length: 10 }, (_, i) => {
        const q = (u * 0.5 + rnd(i)) % 1;
        return <circle key={i} cx={240 + rnd(i, 1) * 380 + Math.sin(u * 3 + i) * 8} cy={340 - q * 190} r={4 + rnd(i, 2) * 6} fill="none" stroke="#fff" strokeWidth={3} opacity={1 - q} />;
      })}
    </svg>
  );
};

const PicLock: React.FC<PicProps> = ({ u, d }) => {
  const o = seg(u, 0.25 * d, 0.55 * d, Easing.out(Easing.back(1.8)));
  return (
    <svg width={850} height={350}>
      <rect width={850} height={350} fill="#fdeee4" />
      {o > 0.2 && Array.from({ length: 14 }, (_, i) => {
        const q = seg(u, 0.45 * d, 0.95 * d);
        const a = (i / 14) * 6.283;
        return <circle key={i} cx={425 + Math.cos(a) * (60 + 190 * q)} cy={190 + Math.sin(a) * (50 + 120 * q)} r={7} fill={["#ff8fb3", "#ffc94d", "#8fc0ff", "#7be0a5"][i % 4]} opacity={1 - q} />;
      })}
      <g transform={`translate(${425 + 45} 185) rotate(${-26 * o}) translate(-45 ${-52 * o})`}>
        <path d="M-45 0 V-60 a45 45 0 0 1 90 0 V0" transform="translate(45 0)" fill="none" stroke="#9a8fdc" strokeWidth={22} strokeLinecap="round" />
      </g>
      <rect x={355} y={185} width={140} height={120} rx={26} fill={VIOLET} />
      <g transform={heart(425, 242, 34 * (1 + 0.1 * Math.sin(u * 7)))}><path d={HEART} fill="#fff" /></g>
    </svg>
  );
};

const PicDream: React.FC<PicProps> = ({ u }) => (
  <svg width={850} height={350}>
    <defs><linearGradient id="nt" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#2a2160" /><stop offset="1" stopColor="#6b5bd6" /></linearGradient></defs>
    <rect width={850} height={350} fill="url(#nt)" />
    {Array.from({ length: 28 }, (_, i) => <circle key={i} cx={rnd(i) * 850} cy={rnd(i, 1) * 200} r={1.5 + rnd(i, 2) * 2.5} fill="#fff" opacity={0.3 + 0.6 * Math.abs(Math.sin(u * 2 + i))} />)}
    <path d="M0 -40 A40 40 0 1 0 0 40 A26 40 0 1 1 0 -40 Z" transform="translate(120 80)" fill="#fff0c2" />
    {[0, 1, 2].map((k) => {
      const q = (u * 0.7 + k * 0.33) % 1;
      const x = 760 - q * 420 - k * 60, y = 30 + q * 150 + k * 25;
      return <line key={k} x1={x} y1={y} x2={x + 46} y2={y - 26} stroke="#fff" strokeWidth={4} strokeLinecap="round" opacity={Math.sin(Math.PI * q)} />;
    })}
    <path d="M0 290 Q200 215 420 275 T850 245 V350 H0 Z" fill="#4b3f9f" />
    <Person x={300} y={278} h={80} color="#ffd7b8" />
    <Person x={340} y={282} h={70} color="#bcd8ff" />
    <path d="M0 330 Q250 285 520 322 T850 300 V350 H0 Z" fill="#392f80" />
  </svg>
);

type Card = { start: number; app: string; cat: string; color: string; notify: string; Pic: React.FC<PicProps> };
const CARDS: Card[] = [
  { start: 92.2, app: "Погода", cat: "на душе", color: "#5aa9ff", notify: "и солнце, и дождь", Pic: PicWeather },
  { start: 95.5, app: "Сообщения", cat: "тебя нет в сети", color: "#34c78a", notify: "не доставлено", Pic: PicChat },
  { start: 98.6, app: "Календарь", cat: "весна", color: "#ff7a59", notify: "первый луч весны", Pic: PicSpring },
  { start: 102.3, app: "Избранное", cat: "только ты", color: "#f5b942", notify: "добавлено: ты", Pic: PicFav },
  { start: 105.4, app: "Дыхание", cat: "вдох · выдох", color: VIOLET, notify: "дыши вместе со мной", Pic: PicBreath },
  { start: 109.0, app: "Глубина", cat: "всё глубже", color: "#3fb7c4", notify: "глубина растёт", Pic: PicDeep },
  { start: 112.0, app: "Замок", cat: "без секретов", color: ROSE, notify: "замок открыт", Pic: PicLock },
  { start: 115.3, app: "Сны", cat: "сладкие грёзы", color: "#6b5bd6", notify: "сладкие сны", Pic: PicDream },
];
const endOf = (i: number) => (i + 1 < CARDS.length ? CARDS[i + 1].start : AUDIO_END);
const mmss = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

const Cover: React.FC<{ size: number }> = ({ size }) => (
  <div style={{ width: size, height: size, borderRadius: size * 0.26, background: `linear-gradient(135deg, ${VIOLET}, #ff6fb5)`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: size * 0.5, color: "#fff", flexShrink: 0 }}>♪</div>
);

export const T9: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = S + frame / fps;
  const frag = AUDIO_END - S;
  const el = Math.min(t, AUDIO_END) - S;
  const uiOut = seg(t, AUDIO_END - 1.0, AUDIO_END - 0.35);
  const endIn = seg(t, AUDIO_END - 0.6, AUDIO_END + 0.2);
  const active = CARDS.reduce((m, c, i) => (t >= c.start ? i : m), 0);
  const notif = CARDS.map((c, i) => ({ i, n: seg(t - c.start, 0.5, 0.65) * (1 - seg(t - c.start, 1.9, 2.05)) })).reduce((m, x) => (x.n > m.n ? x : m), { i: 0, n: 0 });
  const vol = (f: number) => {
    const ts = S + f / fps;
    return Math.min(seg(ts, S, S + 0.12, lin), 1 - seg(ts, AUDIO_END - 0.6, AUDIO_END, lin));
  };
  const hookA = 1 - seg(t, S + 2.2, S + 2.6);

  return (
    <AbsoluteFill style={{ fontFamily, color: INK, background: "linear-gradient(160deg,#ffd9e6 0%,#eadcfb 50%,#d3e5ff 100%)" }}>
      <Audio src={staticFile("t9.mp3")} trimBefore={Math.round(S * fps)} volume={vol} />
      {[["#ffd7b8", 0.9], ["#d4f5e6", 0.7], ["#ffc6df", 0.8]].map(([c, o], i) => (
        <div key={i} style={{ position: "absolute", width: 900, height: 900, borderRadius: "50%", background: `radial-gradient(circle, ${c} 0%, transparent 65%)`, opacity: Number(o),
          left: 540 + 380 * Math.sin(t * 0.22 + i * 2.1) - 450, top: 400 + i * 420 + 220 * Math.cos(t * 0.19 + i * 1.7) - 450 }} />
      ))}
      <svg width={1080} height={1920} style={{ position: "absolute", inset: 0 }}>
        {Array.from({ length: 46 }, (_, i) => {
          const x = rnd(i) * 1080, y = (((rnd(i, 1) * 1920 - t * (14 + rnd(i, 2) * 26)) % 1920) + 1920) % 1920;
          const c = ["#ffffff", "#ff9ec4", "#ffd166", "#9fc0ff", "#b9a8f0"][i % 5];
          return <circle key={i} cx={x} cy={y} r={3 + rnd(i, 3) * 4} fill={c} opacity={0.75} />;
        })}
      </svg>

      <div style={{ position: "absolute", inset: 0, opacity: 1 - uiOut, transform: `scale(${1 - 0.06 * uiOut})` }}>
        {/* hook */}
        <div style={{ position: "absolute", top: 290, left: 70, right: 70, height: 190, display: "flex", alignItems: "center", justifyContent: "center", textAlign: "center",
          fontSize: 72, fontWeight: 800, lineHeight: 1.1, opacity: hookA, textShadow: "0 0 24px rgba(255,255,255,.9)" }}>
          {HOOK}
        </div>

        {/* island */}
        <div style={{ position: "absolute", left: "50%", top: 170, width: 600 + 40 * notif.n, height: 92, marginLeft: -(300 + 20 * notif.n), borderRadius: 46, background: "#08080d", color: "#fff" }}>
          <div style={{ position: "absolute", inset: 0, opacity: 1 - notif.n, display: "flex", alignItems: "center", padding: "0 20px", gap: 16 }}>
            <Cover size={56} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 28, fontWeight: 700 }}>{TITLE}</div>
              <div style={{ fontSize: 20, opacity: 0.55 }}>{ARTIST}</div>
            </div>
            <div style={{ display: "flex", alignItems: "flex-end", gap: 5, height: 36 }}>
              {[0, 1, 2, 3, 4].map((k) => <div key={k} style={{ width: 7, borderRadius: 3, background: "#ff7ab0", height: 10 + 24 * Math.abs(Math.sin(t * (3 + k) + k * 1.3)) }} />)}
            </div>
          </div>
          <div style={{ position: "absolute", inset: 0, opacity: notif.n, display: "flex", alignItems: "center", padding: "0 24px", gap: 16 }}>
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
          const a = i === 0 ? 1 : seg(u, 0, 0.38, Easing.out(Easing.cubic));
          const w = t > next && i < CARDS.length - 1 ? Math.min(1, (t - next) / 0.6) : 0;
          const idle = Math.sin((t * 2 * Math.PI) / 5.2) * 4 * (1 - w);
          const Pic = c.Pic;
          return (
            <div key={i} style={{ position: "absolute", left: 75, top: 500, width: 930, height: 500, borderRadius: 56, background: "rgba(255,255,255,0.97)", zIndex: i,
              boxShadow: "0 28px 70px rgba(120,90,190,.28)", opacity: a * (w > 0 ? 0.5 * (1 - w) : 1), filter: `blur(${(1 - a) * 14 + 6 * w}px)`,
              transform: `translateY(${(1 - a) * 560 - 30 * w}px) perspective(1400px) rotateX(${(1 - a) * -10}deg) rotateY(${idle - (1 - a) * 8}deg) scale(${1.04 * (1 - 0.07 * w)})` }}>
              <div style={{ position: "absolute", left: 40, top: 26, display: "flex", alignItems: "center", gap: 18 }}>
                <div style={{ width: 56, height: 56, borderRadius: 15, background: c.color, transform: `scale(${1 + 0.05 * Math.sin(t * 5)})` }} />
                <div>
                  <div style={{ fontSize: 36, fontWeight: 800, lineHeight: 1.05 }}>{c.app}</div>
                  <div style={{ fontSize: 22, fontWeight: 700, color: VIOLET }}>{c.cat}</div>
                </div>
              </div>
              <div style={{ position: "absolute", left: 40, top: 110, width: 850, height: 350, borderRadius: 30, overflow: "hidden" }}>
                <Pic u={u} d={d} />
                <div style={{ position: "absolute", inset: 0, background: `linear-gradient(105deg, transparent ${((u * 0.5) % 1.6) * 100 - 30}%, rgba(255,255,255,.35) ${((u * 0.5) % 1.6) * 100}%, transparent ${((u * 0.5) % 1.6) * 100 + 12}%)` }} />
              </div>
            </div>
          );
        })}

        {/* dots, author, title, progress */}
        <div style={{ position: "absolute", top: 1105, left: 0, right: 0, display: "flex", justifyContent: "center", gap: 14 }}>
          {CARDS.map((_, i) => <div key={i} style={{ width: i === active ? 44 : 12, height: 12, borderRadius: 6, background: i === active ? INK : "rgba(29,27,46,.25)" }} />)}
        </div>
        <div style={{ position: "absolute", top: 1170, left: "50%", marginLeft: -170, width: 340, height: 56, borderRadius: 28, background: "rgba(255,255,255,.85)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 28, fontWeight: 800 }}>
          автор: {HANDLE}
        </div>
        <div style={{ position: "absolute", top: 1252, left: 0, right: 0, textAlign: "center", fontSize: 50, fontWeight: 800, transform: `translateY(${Math.sin(t * 1.5) * 3}px)` }}>{TITLE}</div>
        <div style={{ position: "absolute", top: 1320, left: 0, right: 0, textAlign: "center", fontSize: 32, fontWeight: 500, opacity: 0.6 }}>{ARTIST}</div>
        <div style={{ position: "absolute", top: 1398, left: 165, width: 750, height: 7, borderRadius: 4, background: "rgba(29,27,46,.15)" }}>
          <div style={{ width: `${(el / frag) * 100}%`, height: "100%", borderRadius: 4, background: INK }} />
          <div style={{ position: "absolute", left: `${(el / frag) * 100}%`, top: -6, width: 19, height: 19, marginLeft: -9, borderRadius: "50%", background: INK }} />
        </div>
        <div style={{ position: "absolute", top: 1420, left: 165, fontSize: 24, opacity: 0.6 }}>{mmss(el)}</div>
        <div style={{ position: "absolute", top: 1420, right: 165, fontSize: 24, opacity: 0.6 }}>-{mmss(frag - el)}</div>
      </div>

      {/* title end card */}
      <div style={{ position: "absolute", inset: 0, opacity: endIn, transform: `scale(${0.92 + 0.08 * endIn})`, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <div style={{ position: "relative", width: 240, height: 240, marginBottom: 44 }}>
          <svg width={240} height={240} style={{ position: "absolute", inset: 0, overflow: "visible" }}>
            {Array.from({ length: 28 }, (_, i) => {
              const a = (i / 28) * Math.PI * 2 + t * 0.6;
              return <circle key={i} cx={120 + Math.cos(a) * 170} cy={120 + Math.sin(a) * 170} r={i % 2 ? 6 : 4} fill={["#ff6fb5", "#6fa8ff", "#ffd166", "#7be0a5", "#b48cff"][i % 5]} />;
            })}
          </svg>
          <div style={{ position: "absolute", inset: 20 }}><Cover size={200} /></div>
        </div>
        <div style={{ fontSize: 112, fontWeight: 800, textAlign: "center", lineHeight: 1.05, padding: "0 60px" }}>{TITLE}</div>
        <div style={{ fontSize: 60, fontWeight: 700, opacity: 0.6, marginTop: 10 }}>{ARTIST}</div>
        <div style={{ marginTop: 36, padding: "10px 34px", borderRadius: 40, background: "rgba(255,255,255,.85)", fontSize: 32, fontWeight: 800 }}>автор: {HANDLE}</div>
      </div>
    </AbsoluteFill>
  );
};
