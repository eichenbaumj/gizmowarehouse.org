import { Children, isValidElement, useEffect, type ReactNode } from "react";
import { Link } from "react-router-dom";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import { ArrowLeft } from "lucide-react";
import { SITE_URL, usePageMeta } from "@/lib/usePageMeta";
// Single source of truth: the pipeline's APPENDIX.md, inlined at build time, so the
// in-page "full methodology ↗" links resolve publicly (the GitHub repo is private).
// Section anchors come from the slugified headings below.
import appendixMd from "../../gizmos/public-private-compensation-comparison/APPENDIX.md?raw";

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

const GIZMO_PATH = "/gizmo/public-private-compensation-comparison";

export default function CompGapMethodology() {
  usePageMeta({
    title: "Methodology — The Public-Sector Pay Gap | Gizmo Warehouse",
    description:
      "Full methodology for the public-vs-private compensation gap: data sources, every modeling choice, and every limitation behind the gap estimates.",
    canonical: `${SITE_URL}${GIZMO_PATH}/methodology`,
  });

  // React Router doesn't auto-scroll to a #hash on load. Do it ourselves once the
  // markdown has rendered (the disclosure links open this page at an anchor).
  useEffect(() => {
    const hash = window.location.hash;
    if (!hash) return;
    const id = decodeURIComponent(hash.slice(1));
    const prevRestoration = history.scrollRestoration;
    if ("scrollRestoration" in history) history.scrollRestoration = "manual";
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
        Back to the public-sector pay gap
      </Link>

      <article className="prose prose-slate max-w-none prose-headings:font-serif prose-headings:text-cobalt prose-a:text-carolina prose-a:no-underline hover:prose-a:underline prose-table:text-sm">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeRaw]}
          components={markdownComponents}
        >
          {appendixMd}
        </ReactMarkdown>
      </article>
    </div>
  );
}
