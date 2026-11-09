import React from "react";

// Flat faceless people (feet / bottom centre at x,y) shared by the card pictures and the hand-made compositions.
export const INK = "#1d1b2e";
export const PURPLE = "#5b4b8a";
export const VIOLET = "#7a6be0";
export const WARM = "#f0a05a";
export const COOL = "#4aa8d8";
export const ROSE = "#ef8f9a";
export const PINK = "#ff5d8f";
export const HEART_P = "M0 0.6 C-1 -0.1 -0.6 -0.9 0 -0.35 C0.6 -0.9 1 -0.1 0 0.6 Z";

export const Bust: React.FC<{ x: number; y: number; s: number; color: string; opacity?: number }> = ({ x, y, s, color, opacity = 1 }) => (
  <g transform={`translate(${x} ${y}) scale(${s})`} fill={color} opacity={opacity}>
    <circle cx={0} cy={-112} r={32} />
    <path d="M-62 0 C-62 -62 -36 -84 0 -84 C36 -84 62 -62 62 0 Z" />
  </g>
);
export const Person: React.FC<{ x: number; y: number; h: number; color: string; opacity?: number }> = ({ x, y, h, color, opacity = 1 }) => (
  <g transform={`translate(${x} ${y}) scale(${h})`} fill={color} opacity={opacity}>
    <circle cx={0} cy={-0.86} r={0.1} />
    <path d="M-0.15 -0.4 Q-0.15 -0.72 0 -0.72 Q0.15 -0.72 0.15 -0.4 L0.12 -0.4 L0.12 0 L0.02 0 L0.02 -0.3 L-0.02 -0.3 L-0.02 0 L-0.12 0 L-0.12 -0.4 Z" />
  </g>
);
export const heartG = (x: number, y: number, s: number, fill: string, extra: React.SVGProps<SVGPathElement> = {}) => (
  <g transform={`translate(${x} ${y}) scale(${s})`}><path d={HEART_P} fill={fill} {...extra} /></g>
);
