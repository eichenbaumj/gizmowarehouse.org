/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";

// The static render (vite build --ssr src/entry-static.tsx, and vitest) swaps
// the interactive embeds for their crawlable stand-ins. The browser bundle
// never sees embeds.static.tsx. See tools/prerender.ts.
export default defineConfig(({ mode, isSsrBuild }) => {
  const staticEmbeds = !!isSsrBuild || mode === "test";
  return {
    server: {
      host: "::",
      port: Number(process.env.PORT) || 8080,
      hmr: {
        overlay: false,
      },
    },
    build: {
      target: "esnext",
    },
    plugins: [react(), mode === "development" && componentTagger()].filter(Boolean),
    resolve: {
      alias: [
        ...(staticEmbeds
          ? [{ find: /^@\/content\/embeds$/, replacement: path.resolve(__dirname, "./src/content/embeds.static.tsx") }]
          : []),
        // Regex, not the string "@": a string alias also matches "@vitest/expect" and every other scoped package.
        { find: /^@\//, replacement: path.resolve(__dirname, "./src") + "/" },
      ],
    },
    ssr: {
      // Bundle everything into dist-static so the prerenderer imports one file.
      // Only for the real SSR build: under vitest this would inline vitest itself.
      noExternal: isSsrBuild ? true : undefined,
    },
    test: {
      environment: "node",
      include: ["test/**/*.test.ts", "test/**/*.test.tsx"],
    },
  };
});
