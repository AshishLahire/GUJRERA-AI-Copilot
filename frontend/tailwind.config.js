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
        page: "var(--bg-page)",
        card: "var(--bg-card)",
        subtle: "var(--bg-subtle)",
        skeleton: "var(--bg-skeleton)",
        warm: {
          border: "var(--border-warm)",
          strong: "var(--border-warm-strong)",
        },
        body: "var(--text-body)",
        muted: "var(--text-muted)",
        accent: {
          surface: "var(--accent-surface)",
          border: "var(--accent-border)",
          amber: "var(--accent-amber)",
          strong: "var(--accent-amber-strong)",
        },
        primary: {
          bg: "var(--btn-primary-bg)",
          text: "var(--btn-primary-text)",
        },
        brand: {
          DEFAULT: "var(--brand)",
          strong: "var(--brand-strong)",
          soft: "var(--brand-soft)",
        },
        "on-brand": "var(--on-brand)",
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
