// Build-time entry: renders any route to static HTML so crawlers that don't
// run JavaScript (Bing, most LLM crawlers, Google's first pass) see the whole
// page, not an empty <div id="root">. Built by `vite build --ssr` into
// dist-static/ and consumed by tools/prerender.ts. In this build the
// interactive embeds are swapped for src/content/embeds.static.tsx (see the
// alias in vite.config.ts), which render the same numbers as plain tables.
//
// The browser still mounts with createRoot().render(), which replaces this
// markup wholesale — no hydration, so the static and live trees are free to
// differ.
import { renderToStaticMarkup } from "react-dom/server";
import { StaticRouter } from "react-router-dom/server";
import Layout from "@/components/Layout";
import AppRoutes from "@/AppRoutes";
import { StaticDataContext } from "@/lib/staticData";

export function renderRoute(url: string, dataContexts: Record<string, unknown> = {}): string {
  return renderToStaticMarkup(
    <StaticDataContext.Provider value={{ isStatic: true, dataContexts }}>
      <StaticRouter location={url}>
        <Layout>
          <AppRoutes />
        </Layout>
      </StaticRouter>
    </StaticDataContext.Provider>
  );
}

export { publicRoutes } from "@/lib/routes";
export { gizmos } from "@/data/gizmos";
