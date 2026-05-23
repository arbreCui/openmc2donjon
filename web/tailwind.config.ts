import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "media",
  theme: {
    extend: {
      fontFamily: {
        sans: ["-apple-system", "BlinkMacSystemFont", "ui-sans-serif", "system-ui"],
        mono: ["SF Mono", "Menlo", "Monaco", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
