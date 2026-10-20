/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";

// The static render (vite build --ssr src/entry-static.tsx, and vitest) swaps
// the interactive embeds for their crawlable stand-ins. The browser bundle
// never sees embeds.static.tsx. See tools/prerender.ts.
// Draft gizmos (scaffolded but not wired into src/data/gizmos.ts) are previewable ONLY under
// `vite` dev mode through the virtual module below, which resolves to src/dev/drafts.tsx. Every other
// mode (production build, build:dev, SSR, test) gets `undefined`, so a draft's code, data and slug never
// reach a bundle. src/dev/ is a privateRule in tools/mirror/manifest.ts; tools/check-draft-leak.ts
// verifies dist/ after every build.
function devDraftsPlugin(mode: string) {
  const id = "virtual:dev-drafts";
  const resolved = "\0" + id;
  return {
    name: "dev-drafts",
    resolveId(source: string) {
      return source === id ? resolved : null;
    },
    load(source: string) {
      if (source !== resolved) return null;
      return mode === "development"
        ? `export { devDrafts } from "/src/dev/drafts.tsx";`
        : `export const devDrafts = undefined;`;
    },
  };
}

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
    plugins: [react(), devDraftsPlugin(mode), mode === "development" && componentTagger()].filter(Boolean),
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
      include: ["test/**/*.test.ts", "test/**/*.test.tsx", "gizmos/*/test/**/*.test.ts", "gizmos/*/test/**/*.test.tsx"],
    },
  };
});
