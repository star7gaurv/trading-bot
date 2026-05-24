/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Dashboard v2 design tokens — restrained dark theme
        canvas: "#0a0d11",
        surface: "#13171c",
        elevated: "#1a1f26",
        hover: "#222831",
        border: {
          DEFAULT: "#1f242b",
          strong: "#2b323b",
        },
        accent: {
          DEFAULT: "#3b82f6",
          dim: "#1d4ed8",
        },
        profit: "#22c55e",
        loss: "#ef4444",
        warn: "#f59e0b",
        info: "#3b82f6",
        text: {
          primary: "#f1f5f9",
          secondary: "#94a3b8",
          tertiary: "#64748b",
          muted: "#475569",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        // 11/12/13/14/16/20/28 px scale
        xxs: ["11px", { lineHeight: "16px" }],
        xs: ["12px", { lineHeight: "16px" }],
        sm: ["13px", { lineHeight: "18px" }],
        base: ["14px", { lineHeight: "20px" }],
        lg: ["16px", { lineHeight: "22px" }],
        xl: ["20px", { lineHeight: "26px" }],
        "2xl": ["28px", { lineHeight: "34px" }],
      },
      spacing: {
        // Tight scale: 4/8/12/16/24/32 — keep Tailwind defaults available too
        "1.5": "6px",
      },
      boxShadow: {
        soft: "0 1px 2px rgba(0,0,0,0.4)",
        lifted: "0 4px 12px rgba(0,0,0,0.45)",
      },
    },
  },
  plugins: [],
};
