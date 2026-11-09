import React from "react";
import { ThreeCanvas } from "@remotion/three";
import { pr } from "./anim";
import { Bust, COOL, heartG, INK, PINK, VIOLET, WARM } from "./shapes";
import type { BodyProps } from "./types";

// Hand-made animated scenes (from the Т9 video): every object keeps moving for as long as the card lives.
// Kinds: weather, typing, bloom, duo, breath (3D), deep, unlock, night. Pictures are 850x350 scaled to the 820x340 body.
const sg = (u: number, a: number, b: number, e = "power2.inOut") => pr(u, a, b - a, e);
const rnd = (i: number, k = 0) => { const x = Math.sin(i * 127.1 + k * 311.7) * 43758.5453; return x - Math.floor(x); };
const clip = (t: unknown, n: number) => { const s = String(t ?? ""); return s.length <= n ? s : s.slice(0, n - 1).trimEnd() + "…"; };
const Svg: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <svg viewBox="0 0 850 350" preserveAspectRatio="xMidYMid slice" width={820} height={340} style={{ display: "block" }}>{children}</svg>
);
const Rays: React.FC<{ r: number; u: number; col?: string; sw?: number }> = ({ r, u, col = "#ffc94d", sw = 8 }) => (
  <>{Array.from({ length: 10 }, (_, i) => <line key={i} x1={0} y1={-(r + 16)} x2={0} y2={-(r + 40)} stroke={col} strokeWidth={sw} strokeLinecap="round" transform={`rotate(${i * 36 + u * 45})`} />)}</>
);

export const Weather: React.FC<BodyProps> = ({ i, u, d }) => {
  const cloud = sg(u, 0.12 * d, 0.4 * d);
  const beat = 1 + 0.1 * Math.sin(u * 7), sunK = 1 + 0.06 * Math.sin(u * 3), drift = 18 * Math.sin(u * 1.4);
  return (
    <Svg>
      <defs><linearGradient id={`wx${i}`} x1="0" x2="1"><stop offset="0.35" stopColor="#fff0c9" /><stop offset="0.65" stopColor="#d6e3fa" /></linearGradient></defs>
      <rect width={850} height={350} fill={`url(#wx${i})`} />
      <g transform={`translate(170 110) scale(${sunK})`}><Rays r={46} u={u} /><circle r={46} fill="#ffc94d" /></g>
      <g transform={`translate(${690 + drift} 100)`} opacity={cloud}>
        <circle cx={-40} cy={10} r={34} fill="#9db4dc" /><circle cx={0} cy={-8} r={44} fill="#9db4dc" /><circle cx={44} cy={10} r={32} fill="#9db4dc" />
        <rect x={-74} y={10} width={150} height={34} rx={17} fill="#9db4dc" />
        {Array.from({ length: 9 }, (_, k) => {
          const p = (u * 0.9 + rnd(k)) % 1;
          return <line key={k} x1={-60 + k * 15} y1={60 + p * 150} x2={-66 + k * 15} y2={78 + p * 150} stroke="#4a73d0" strokeWidth={7} strokeLinecap="round" opacity={(1 - p) * cloud} />;
        })}
      </g>
      {heartG(425, 195, 110 * beat, PINK)}
    </Svg>
  );
};

export const Typing: React.FC<BodyProps> = ({ w, u, d }) => {
  const b1 = sg(u, 0.08 * d, 0.08 * d + 0.4, "back.out(1.4)"), b2 = sg(u, 0.33 * d, 0.33 * d + 0.4, "back.out(1.4)");
  const typing = sg(u, 0.02 * d, 0.12 * d) * (1 - sg(u, 0.5 * d, 0.6 * d)), off = sg(u, 0.55 * d, 0.62 * d), err = sg(u, 0.65 * d, 0.8 * d);
  const bubble = (y: number, n: number, a: number) => (
    <g transform={`translate(${n === 2 ? 650 - 90 * (1 - a) : 720 - 90 * (1 - a)} ${y}) scale(${a})`} opacity={a}>
      <rect x={n === 2 ? -150 : -80} y={0} width={n === 2 ? 220 : 150} height={80} rx={34} fill={VIOLET} />
      {Array.from({ length: n }, (_, k) => heartG(n === 2 ? -105 + k * 75 : -5, 42, 30, "#fff"))}
    </g>
  );
  return (
    <Svg>
      <rect width={850} height={350} fill="#eef1fb" />
      <g transform="translate(56 30)">
        <circle r={22} cx={22} cy={22} fill="#cfd5ea" /><Bust x={22} y={40} s={0.17} color="#fff" />
        <text x={62} y={30} fontSize={28} fontWeight={800} fill={INK}>{clip(w.who ?? "Ты", 8)}</text>
        <circle cx={150} cy={20} r={7} fill={off > 0.5 ? "#b9bccd" : "#34c78a"} />
        <text x={166} y={29} fontSize={24} fontWeight={700} fill="#8a8ca3">{off > 0.5 ? clip(w.status ?? "не в сети", 14) : "в сети"}</text>
      </g>
      <g opacity={typing} transform="translate(60 150)">
        <rect width={130} height={70} rx={32} fill="#dfe3f2" />
        {[0, 1, 2].map((k) => <circle key={k} cx={36 + k * 29} cy={35 - 8 * Math.max(0, Math.sin(u * 8 - k))} r={8} fill="#9ea3be" />)}
      </g>
      {bubble(100, 1, b1)}{bubble(200, 2, b2)}
      <text x={790} y={318} textAnchor="end" fontSize={24} fontWeight={700} fill="#e0575b" opacity={err}>{clip(w.err ?? "не доставлено", 18)}</text>
    </Svg>
  );
};

export const Bloom: React.FC<BodyProps> = ({ i, u, d }) => {
  const rise = sg(u, 0, 0.35 * d), g = sg(u, 0.25 * d, 0.8 * d), bloom = sg(u, 0.7 * d, 0.95 * d, "back.out(1.6)");
  const sx = 120 + 40 * rise, sy = 250 - 180 * rise, fx = 560, fy = 300 - 170 * g;
  const sway = Math.sin(u * 2) * 5 * bloom;
  return (
    <Svg>
      <defs><linearGradient id={`sp${i}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#ffe9c9" /><stop offset="1" stopColor="#e4f3ff" /></linearGradient></defs>
      <rect width={850} height={350} fill={`url(#sp${i})`} />
      <polygon points={`${sx},${sy} ${fx - 70},300 ${fx + 70},300`} fill="#fff3b8" opacity={0.55 * rise} />
      <g transform={`translate(${sx} ${sy})`}><Rays r={42} u={u} sw={7} /><circle r={42} fill="#ffc94d" /></g>
      {Array.from({ length: 9 }, (_, k) => {
        const q = (u * 0.3 + rnd(k)) % 1;
        return <circle key={k} cx={380 + rnd(k, 1) * 420 + Math.sin(u * 2 + k) * 14} cy={320 - q * 230} r={5 + rnd(k, 2) * 5} fill="#ff8fb3" opacity={Math.sin(Math.PI * q) * rise} />;
      })}
      <path d="M0 320 Q220 280 430 315 T850 300 V350 H0 Z" fill="#a8d99a" />
      <g transform={`rotate(${sway} ${fx} 310)`}>
        <line x1={fx} y1={310} x2={fx} y2={fy} stroke="#4f9d5a" strokeWidth={9} strokeLinecap="round" />
        {g > 0.3 && <ellipse cx={fx - 26} cy={fy + 70} rx={30} ry={13} fill="#6bbf6e" transform={`rotate(-25 ${fx - 26} ${fy + 70})`} />}
        {g > 0.5 && <ellipse cx={fx + 26} cy={fy + 100} rx={30} ry={13} fill="#6bbf6e" transform={`rotate(25 ${fx + 26} ${fy + 100})`} />}
        <g transform={`translate(${fx} ${fy}) scale(${bloom})`} opacity={bloom}>
          {Array.from({ length: 6 }, (_, k) => <circle key={k} cx={Math.cos((k / 6) * 6.283 + u * 0.4) * 30} cy={Math.sin((k / 6) * 6.283 + u * 0.4) * 30} r={20} fill="#ff8fb3" />)}
          <circle r={18} fill="#ffd54d" />
        </g>
      </g>
    </Svg>
  );
};

export const Duo: React.FC<BodyProps> = ({ u, d }) => {
  const pop = sg(u, 0.2 * d, 0.2 * d + 0.5, "back.out(2)"), fill = sg(u, 0.3 * d, 0.55 * d), star = sg(u, 0.5 * d, 0.7 * d);
  const beat = 1 + 0.06 * Math.sin(u * 6) * fill;
  return (
    <Svg>
      <rect width={850} height={350} fill="#fff4dc" />
      <Bust x={190} y={340} s={1.45 + 0.02 * Math.sin(u * 2)} color={WARM} /><Bust x={660} y={340} s={1.45 + 0.02 * Math.sin(u * 2 + 1.5)} color={COOL} />
      {heartG(425, 190, 120 * pop * beat, "none", { fill: PINK, fillOpacity: fill, stroke: PINK, strokeWidth: 0.06 })}
      <path d="M425 40 l9 20 22 3 -16 15 5 22 -20 -11 -20 11 5 -22 -16 -15 22 -3 z" fill={star > 0.5 ? "#ffc94d" : "none"} stroke="#ffc94d" strokeWidth={5} strokeLinejoin="round" opacity={0.4 + 0.6 * star}
        transform={`rotate(${star > 0.5 ? Math.sin(u * 3) * 6 : 0} 425 62)`} />
    </Svg>
  );
};

export const Breath: React.FC<BodyProps> = ({ u }) => {
  const k = 0.5 - 0.5 * Math.cos((Math.PI * u) / 1.8); // inhale 1.8 s, exhale 1.8 s, again and again
  const s = 0.95 + 0.4 * k;
  const phase = Math.floor(u / 1.8) % 2 === 0 ? "вдох" : "выдох";
  const tilt = Math.PI / 2.4;
  return (
    <div style={{ position: "relative", width: 820, height: 340, background: "#efe6fb" }}>
      <ThreeCanvas width={820} height={340} camera={{ fov: 40, position: [0, 0, 9] }}>
        <ambientLight intensity={0.9} />
        <directionalLight position={[3, 4, 5]} intensity={2.2} color="#fff4e6" />
        <pointLight position={[-4, -2, 4]} intensity={40} color="#9fc0ff" />
        <mesh scale={s}><sphereGeometry args={[1.45, 64, 64]} /><meshStandardMaterial color="#ff9ec4" emissive="#ff6fa8" emissiveIntensity={0.2 + 0.25 * k} roughness={0.25} metalness={0.1} /></mesh>
        <mesh rotation={[tilt, 0, u * 0.8]} scale={s * 1.1}><torusGeometry args={[2.1, 0.03, 12, 160]} /><meshStandardMaterial color="#b9a8f0" emissive="#7a6be0" emissiveIntensity={0.5} /></mesh>
        {Array.from({ length: 7 }, (_, n) => {
          const a = (n / 7) * 6.283 + u * 0.8, r = 2.1 * s * 1.1;
          return <mesh key={n} position={[Math.cos(a) * r, Math.sin(a) * r * Math.cos(tilt), Math.sin(a) * r * Math.sin(tilt)]}><sphereGeometry args={[0.09, 16, 16]} /><meshStandardMaterial color="#fff" emissive="#ffffff" emissiveIntensity={0.6} /></mesh>;
        })}
      </ThreeCanvas>
      <svg viewBox="0 0 850 350" preserveAspectRatio="xMidYMid slice" width={820} height={340} style={{ position: "absolute", inset: 0 }}>
        <Bust x={110} y={345} s={1.15} color={WARM} /><Bust x={740} y={345} s={1.15} color={COOL} />
        <text x={425} y={52} textAnchor="middle" fontSize={40} fontWeight={800} fill={INK}>{phase}</text>
      </svg>
    </div>
  );
};

export const Deep: React.FC<BodyProps> = ({ u, d }) => {
  const p = Math.min(1, u / Math.max(d, 0.1)), level = 215 - 30 * p;
  const wave = (off: number, amp: number) => {
    let s = `M0 350 L0 ${level}`;
    for (let x = 0; x <= 850; x += 25) s += ` L${x} ${level + amp * Math.sin(x * 0.02 + u * 3 + off)}`;
    return s + " L850 350 Z";
  };
  return (
    <Svg>
      <rect width={850} height={350} fill="#eaf4ff" />
      <Bust x={290} y={170 + 90 * p} s={1} color={WARM} /><Bust x={560} y={185 + 90 * p} s={1} color={COOL} />
      <path d={wave(0, 9)} fill="rgba(110,175,255,0.55)" /><path d={wave(2, 7)} fill="rgba(70,140,240,0.45)" />
      {Array.from({ length: 10 }, (_, k) => {
        const q = (u * 0.5 + rnd(k)) % 1;
        return <circle key={k} cx={240 + rnd(k, 1) * 380 + Math.sin(u * 3 + k) * 8} cy={340 - q * 190} r={4 + rnd(k, 2) * 6} fill="none" stroke="#fff" strokeWidth={3} opacity={1 - q} />;
      })}
    </Svg>
  );
};

export const Unlock: React.FC<BodyProps> = ({ u, d }) => {
  const o = sg(u, 0.25 * d, 0.55 * d, "back.out(1.8)"), q = sg(u, 0.45 * d, 0.95 * d);
  return (
    <Svg>
      <rect width={850} height={350} fill="#fdeee4" />
      {o > 0.2 && Array.from({ length: 14 }, (_, k) => {
        const a = (k / 14) * 6.283;
        return <circle key={k} cx={425 + Math.cos(a) * (60 + 190 * q)} cy={190 + Math.sin(a) * (50 + 120 * q)} r={7} fill={["#ff8fb3", "#ffc94d", "#8fc0ff", "#7be0a5"][k % 4]} opacity={1 - q} />;
      })}
      <g transform={`translate(470 185) rotate(${-26 * o}) translate(-45 ${-52 * o})`}>
        <path d="M-45 0 V-60 a45 45 0 0 1 90 0 V0" transform="translate(45 0)" fill="none" stroke="#9a8fdc" strokeWidth={22} strokeLinecap="round" />
      </g>
      <rect x={355} y={185} width={140} height={120} rx={26} fill={VIOLET} />
      {heartG(425, 242, 34 * (1 + 0.1 * Math.sin(u * 7)), "#fff")}
    </Svg>
  );
};

export const Night: React.FC<BodyProps> = ({ i, u }) => (
  <Svg>
    <defs><linearGradient id={`nt${i}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#2a2160" /><stop offset="1" stopColor="#6b5bd6" /></linearGradient></defs>
    <rect width={850} height={350} fill={`url(#nt${i})`} />
    {Array.from({ length: 28 }, (_, k) => <circle key={k} cx={rnd(k) * 850} cy={rnd(k, 1) * 200} r={1.5 + rnd(k, 2) * 2.5} fill="#fff" opacity={0.3 + 0.6 * Math.abs(Math.sin(u * 2 + k))} />)}
    <path d="M0 -40 A40 40 0 1 0 0 40 A26 40 0 1 1 0 -40 Z" transform="translate(120 80)" fill="#fff0c2" />
    {[0, 1, 2].map((k) => {
      const q = (u * 0.7 + k * 0.33) % 1, x = 760 - q * 420 - k * 60, y = 30 + q * 150 + k * 25;
      return <line key={k} x1={x} y1={y} x2={x + 46} y2={y - 26} stroke="#fff" strokeWidth={4} strokeLinecap="round" opacity={Math.sin(Math.PI * q)} />;
    })}
    <path d="M0 290 Q200 215 420 275 T850 245 V350 H0 Z" fill="#4b3f9f" />
    <g transform={`translate(0 ${1.5 * Math.sin(u * 1.5)})`}>
      <Bust x={300} y={290} s={0.45} color="#ffd7b8" /><Bust x={352} y={294} s={0.4} color="#bcd8ff" />
    </g>
    <path d="M0 330 Q250 285 520 322 T850 300 V350 H0 Z" fill="#392f80" />
  </Svg>
);

export const SCENES: Record<string, React.FC<BodyProps>> = { weather: Weather, typing: Typing, bloom: Bloom, duo: Duo, breath: Breath, deep: Deep, unlock: Unlock, night: Night };
