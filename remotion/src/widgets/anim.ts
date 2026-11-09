// Tween helpers: pure functions of time (seconds since the card started). The names of the eases are the ones the author step may use.
const clamp01 = (x: number) => Math.min(1, Math.max(0, x));
const pw = (n: number) => ({ in: (x: number) => x ** n, out: (x: number) => 1 - (1 - x) ** n, inOut: (x: number) => (x < 0.5 ? 2 ** (n - 1) * x ** n : 1 - (-2 * x + 2) ** n / 2) });
const back = (s: number) => (x: number) => 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2;
const bounceOut = (x: number) => {
  const n = 7.5625, d = 2.75;
  if (x < 1 / d) return n * x * x;
  if (x < 2 / d) return n * (x -= 1.5 / d) * x + 0.75;
  if (x < 2.5 / d) return n * (x -= 2.25 / d) * x + 0.9375;
  return n * (x -= 2.625 / d) * x + 0.984375;
};

export const ease = (name = "none"): ((x: number) => number) => {
  const m = /^back\.out\(([\d.]+)\)$/.exec(name);
  if (m) return back(Number(m[1]));
  switch (name) {
    case "power1.out": return pw(2).out;
    case "power1.inOut": return pw(2).inOut;
    case "power2.in": return pw(3).in;
    case "power2.out": return pw(3).out;
    case "power2.inOut": return pw(3).inOut;
    case "power3.in": return pw(4).in;
    case "power3.out": return pw(4).out;
    case "power3.inOut": return pw(4).inOut;
    case "sine.inOut": return (x) => -(Math.cos(Math.PI * x) - 1) / 2;
    case "bounce.out": return bounceOut;
    default: return (x) => x;
  }
};

/** value of a -> b between `at` and `at + dur` (held before and after). */
export const ft = (u: number, at: number, dur: number, a: number, b: number, e = "none") => a + (b - a) * ease(e)(clamp01((u - at) / Math.max(dur, 0.001)));
/** progress 0..1 of a tween window. */
export const pr = (u: number, at: number, dur: number, e = "none") => ease(e)(clamp01((u - at) / Math.max(dur, 0.001)));
/** there-and-back loop (GSAP yoyo + repeat): 0..1..0 with period 2*dur. */
export const yoyo = (u: number, at: number, dur: number, e = "sine.inOut") => {
  const p = Math.max(0, u - at) / dur;
  const k = p % 2;
  return ease(e)(k <= 1 ? k : 2 - k);
};
export const fmtNum = (v: number) => Math.round(v).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");

export type Tween = {
  id: string; at: number; dur: number; from?: Record<string, number>; to: Record<string, number>; ease?: string; loop?: boolean | string; o?: [number, number];
};

type Vals = Record<string, number>;

/** Apply drawn-picture tweens to elements `#<prefix><id>` inside `root`. Later tweens of one shape continue from the earlier ones. */
export const applyTweens = (root: HTMLElement | null, prefix: string, tweens: Tween[], u: number) => {
  if (!root) return;
  const state = new Map<string, { vals: Vals; origin?: string }>();
  for (const t of tweens) {
    const st = state.get(t.id) ?? { vals: {} };
    state.set(t.id, st);
    const from: Vals = t.from && Object.keys(t.from).length ? t.from : Object.fromEntries(Object.entries(t.to).filter(([k]) => k === "opacity" || k === "scale"));
    const first = !("__seen" in st.vals);
    let p = (u - t.at) / t.dur;
    if (p < 0 && !first) continue;
    let k = clamp01(p);
    if (t.loop && p > 0) {
      k = t.loop === "cycle" ? p % 1 : (p % 2 <= 1 ? p % 2 : 2 - (p % 2));
    }
    const e = ease(t.ease)(k);
    for (const key of new Set([...Object.keys(from), ...Object.keys(t.to)])) {
      const a = from[key] ?? st.vals[key] ?? (key.startsWith("scale") || key === "opacity" ? 1 : 0);
      st.vals[key] = a + (t.to[key] - a) * e;
    }
    st.vals.__seen = 1;
    if (t.o) st.origin = `${t.o[0]}px ${t.o[1]}px`;
  }
  for (const [id, st] of state) {
    const el = root.querySelector<SVGElement | HTMLElement>(`#${prefix}${id}`);
    if (!el) continue;
    const v = st.vals;
    const sx = v.scaleX ?? v.scale ?? 1, sy = v.scaleY ?? v.scale ?? 1;
    el.style.transform = `translate(${v.x ?? 0}px, ${v.y ?? 0}px) rotate(${v.rotation ?? 0}deg) scale(${sx}, ${sy})`;
    if (st.origin) el.style.transformOrigin = st.origin;
    if (v.opacity !== undefined) el.style.opacity = String(v.opacity);
    if (v.strokeDashoffset !== undefined) el.style.strokeDashoffset = String(v.strokeDashoffset);
  }
};
