/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        mono: ["'JetBrains Mono'", "'Fira Code'", "ui-monospace", "monospace"],
      },
      colors: {
        hud: {
          bg:        "#030811",
          panel:     "#010D1A",
          cyan:      "#00F0FF",
          blue:      "#005F88",
          ice:       "#E0FFFF",
          cyan_dim:  "#00A8CC",
          warn:      "#FFB800",
          proc:      "#FF00FF",
          ok:        "#00FF88",
          err:       "#FF3366",
          amber:     "#B8860B",
        },
      },
      boxShadow: {
        "glow-cyan": "0 0 24px rgba(0,240,255,.45), 0 0 64px rgba(0,240,255,.18)",
        "glow-warn": "0 0 24px rgba(255,184,0,.45),  0 0 64px rgba(255,184,0,.18)",
        "glow-proc": "0 0 24px rgba(255,0,255,.45),  0 0 64px rgba(255,0,255,.18)",
        "glow-ok":   "0 0 24px rgba(0,255,136,.45),  0 0 64px rgba(0,255,136,.18)",
        "inner-cyan": "inset 0 0 18px rgba(0,240,255,.25)",
      },
      animation: {
        "scan-line": "scan-line 4s linear infinite",
        "pulse-slow": "pulse 3s cubic-bezier(.4,0,.6,1) infinite",
        "grid-drift": "grid-drift 40s linear infinite",
      },
      keyframes: {
        "scan-line": {
          "0%":   { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100vh)" },
        },
        "grid-drift": {
          "0%":   { backgroundPosition: "0 0" },
          "100%": { backgroundPosition: "60px 60px" },
        },
      },
    },
  },
  plugins: [],
};
