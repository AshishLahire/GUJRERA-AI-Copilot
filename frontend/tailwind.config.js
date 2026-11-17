/**
 * Theme colours are CSS variables (light/dark in src/index.css). A plain v("--x") colour makes
 * Tailwind drop opacity modifiers such as bg-card/95 or bg-brand/60 silently, so each colour is a
 * function that mixes the variable with transparent when an opacity is asked for.
 */
const v = (name) => ({ opacityValue }) =>
  opacityValue === undefined || opacityValue === "1"
    ? `var(${name})`
    : `color-mix(in srgb, var(${name}) calc(${opacityValue} * 100%), transparent)`;

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        heading: [
          "'Plus Jakarta Sans'",
          "Inter",
          "'Noto Sans Devanagari'",
          "'Noto Sans Gujarati'",
          "system-ui",
          "sans-serif",
        ],
        sans: [
          "Inter",
          "'Noto Sans Devanagari'",
          "'Noto Sans Gujarati'",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
        mono: [
          "'JetBrains Mono'",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "'Noto Sans Devanagari'",
          "'Noto Sans Gujarati'",
          "monospace",
        ],
      },
      colors: {
        page: v("--bg-page"),
        card: v("--bg-card"),
        subtle: v("--bg-subtle"),
        skeleton: v("--bg-skeleton"),
        warm: {
          border: v("--border-warm"),
          strong: v("--border-warm-strong"),
        },
        body: v("--text-body"),
        muted: v("--text-muted"),
        accent: {
          surface: v("--accent-surface"),
          border: v("--accent-border"),
          amber: v("--accent-amber"),
          strong: v("--accent-amber-strong"),
        },
        primary: {
          bg: v("--btn-primary-bg"),
          text: v("--btn-primary-text"),
        },
        brand: {
          DEFAULT: v("--brand"),
          strong: v("--brand-strong"),
          soft: v("--brand-soft"),
        },
        "on-brand": v("--on-brand"),
      },
      borderRadius: {
        card: "12px",
      },
      transitionDuration: {
        DEFAULT: "150ms",
      },
    },
  },
  plugins: [],
};
