import { Children, isValidElement, useEffect, type ReactNode } from "react";
import { Link } from "react-router-dom";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import { ArrowLeft } from "lucide-react";
import { SITE_URL, usePageMeta } from "@/lib/usePageMeta";
// Single source of truth: the pipeline's METHODOLOGY.md, inlined at build time.
// This is what makes the in-page "See methodology ↗" links resolve publicly
// (the GitHub repo is private). Section anchors come from <a id="..."> tags
// embedded in the markdown.
import methodologyMd from "../../gizmos/medicaid-work-requirements/METHODOLOGY.md?raw";

/** Slugify a heading's text for use as an anchor id (mirrors GizmoPage). */
function headingSlug(children: ReactNode): string {
  const txt = Children.toArray(children)
    .map((c) => (typeof c === "string" ? c : isValidElement(c) ? "" : String(c ?? "")))
    .join("")
    .trim()
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-");
  return txt || "section";
}

const markdownComponents: Components = {
  h2: ({ children, ...props }) => <h2 id={headingSlug(children)} {...props}>{children}</h2>,
  h3: ({ children, ...props }) => <h3 id={headingSlug(children)} {...props}>{children}</h3>,
  h4: ({ children, ...props }) => <h4 id={headingSlug(children)} {...props}>{children}</h4>,
};

const GIZMO_PATH = "/gizmo/medicaid-work-requirements";

export default function MedicaidMethodology() {
  usePageMeta({
    title: "Methodology — Medicaid Work Requirements | Gizmo Warehouse",
    description:
      "Full methodology for the Medicaid work-requirements map: data sources, every assumption, and every limitation behind the subject-pool, exemption, loss-breakdown, and ex parte estimates.",
    canonical: `${SITE_URL}${GIZMO_PATH}/methodology`,
  });

  // React Router doesn't auto-scroll to a #hash on load. Do it ourselves once
  // the markdown has rendered (the disclosure links open this page at an anchor).
  useEffect(() => {
    const hash = window.location.hash;
    if (!hash) return;
    const id = decodeURIComponent(hash.slice(1));
    // Don't let the browser restore a remembered scroll position and fight us.
    const prevRestoration = history.scrollRestoration;
    if ("scrollRestoration" in history) history.scrollRestoration = "manual";
    // The methodology doc is long; the target anchor may not be laid out on the
    // first tick. Retry a few times until it's present, then jump to it.
    let tries = 0;
    let timer: number | undefined;
    const scroll = () => {
      const el = document.getElementById(id);
      if (el) {
        el.scrollIntoView({ behavior: "auto", block: "start" });
        return;
      }
      if (tries++ < 25) timer = window.setTimeout(scroll, 100);
    };
    timer = window.setTimeout(scroll, 50);
    return () => {
      if (timer) window.clearTimeout(timer);
      if ("scrollRestoration" in history) history.scrollRestoration = prevRestoration;
    };
  }, []);

  return (
    <div>
      <Link
        to={GIZMO_PATH}
        className="inline-flex items-center gap-1.5 text-sm text-steel hover:text-cobalt transition-colors mb-8"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to the Medicaid work-requirements map
      </Link>

      <article className="prose prose-slate max-w-none prose-headings:font-serif prose-headings:text-cobalt prose-a:text-carolina prose-a:no-underline hover:prose-a:underline prose-table:text-sm">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeRaw]}
          components={markdownComponents}
        >
          {methodologyMd}
        </ReactMarkdown>
      </article>
    </div>
  );
}
