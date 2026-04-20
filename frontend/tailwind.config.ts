import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0B0A09",
        fg: "#F2EDE4",
        accent: "#D97757",
        pass: "#7FB069",
        fail: "#E26D5A",
        border: "#26231F",
        muted: "#8A837A",
      },
      fontFamily: {
        display: ["Fraunces", "serif"],
        sans: ["Instrument Sans", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
