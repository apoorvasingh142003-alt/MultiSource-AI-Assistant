import type { Config } from "tailwindcss";

// Semantic color tokens are driven by CSS variables (space-separated RGB channels defined in
// globals.css) so the whole UI inverts cleanly between light and dark from a single source of
// truth. `<alpha-value>` keeps Tailwind opacity modifiers working (e.g. `bg-surface-2/60`).
const token = (v: string) => `rgb(var(${v}) / <alpha-value>)`;

const config: Config = {
  // `class` (not the default `media`) so the manual light/dark toggle — which sets `.dark` on
  // <html> — actually drives every `dark:` variant, and the token vars flip in lockstep.
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      colors: {
        ink: "#0b1220",
        // ---- semantic surface / text / line tokens (auto light+dark) ----
        app: token("--c-app"),
        surface: token("--c-surface"),
        "surface-2": token("--c-surface-2"),
        overlay: token("--c-overlay"),
        line: token("--c-line"),
        "line-strong": token("--c-line-strong"),
        fg: token("--c-fg"),
        body: token("--c-body"),
        muted: token("--c-muted"),
        faint: token("--c-faint"),
        accent: {
          DEFAULT: token("--c-accent"),
          strong: token("--c-accent-strong"),
          soft: token("--c-accent-soft"),
          fg: token("--c-accent-fg"),
        },
      },
      boxShadow: {
        card: "0 1px 2px rgba(16,24,40,0.04), 0 1px 3px rgba(16,24,40,0.06)",
        pop: "0 10px 30px -12px rgba(16,24,40,0.28), 0 4px 10px -6px rgba(16,24,40,0.12)",
        glow: "0 0 0 1px rgba(99,102,241,0.25), 0 8px 30px -10px rgba(99,102,241,0.45)",
      },
      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "scale-in": {
          from: { opacity: "0", transform: "translateY(-4px) scale(0.98)" },
          to: { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        float: {
          "0%,100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-6px)" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.2s ease-out both",
        "scale-in": "scale-in 0.16s cubic-bezier(0.22,1,0.36,1) both",
        float: "float 6s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
export default config;
