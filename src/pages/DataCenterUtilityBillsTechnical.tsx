import { Children, isValidElement, useEffect, type ReactNode } from "react";
import { Link } from "react-router-dom";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { gizmos } from "@/data/gizmos";
import { methodologySeo } from "@/lib/seo";
import { usePageMeta } from "@/lib/usePageMeta";
// The technical version of "Do Data Centers Raise Your Electric Bill?". Single source: the gizmo
// folder's TECHNICAL.md (shipped on the public mirror beside the code), inlined at build time.
import technicalMd from "../../gizmos/data-center-utility-bills/TECHNICAL.md?raw";

const SLUG = "data-center-utility-bills";
const GIZMO_PATH = `/gizmo/${SLUG}`;
const PATH = `${GIZMO_PATH}/methodology`;
const CODE_URL = "https://github.com/eichenbaumj/gizmowarehouse.org/tree/main/gizmos/data-center-utility-bills";

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
  h2: ({ node: _node, children, ...props }) => <h2 id={headingSlug(children)} {...props}>{children}</h2>,
  h3: ({ node: _node, children, ...props }) => <h3 id={headingSlug(children)} {...props}>{children}</h3>,
  // The appendix tables are wide; let them scroll sideways instead of breaking the page on a phone.
  table: ({ node: _node, ...props }) => (
    <div className="overflow-x-auto">
      <table {...props} />
    </div>
  ),
  img: ({ node: _node, alt, ...props }) => (
    <img alt={alt ?? ""} loading="lazy" className="w-full h-auto rounded-md border border-slate-200 bg-white" {...props} />
  ),
};

export default function DataCenterUtilityBillsTechnical() {
  const gizmo = gizmos.find((g) => g.slug === SLUG)!;
  usePageMeta(methodologySeo(gizmo, PATH));

  // React Router doesn't scroll to a #hash on load; do it once the markdown has rendered.
  useEffect(() => {
    const id = decodeURIComponent(window.location.hash.slice(1));
    if (!id) return;
    const t = window.setTimeout(() => document.getElementById(id)?.scrollIntoView({ block: "start" }), 50);
    return () => window.clearTimeout(t);
  }, []);

  return (
    <div>
      <Link
        to={GIZMO_PATH}
        className="inline-flex items-center gap-1.5 text-sm text-steel hover:text-cobalt transition-colors mb-8"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to the plain-language version
      </Link>

      <p className="font-sans text-xs font-semibold uppercase tracking-wider text-carolina mb-2">Technical version</p>
      <h1 className="font-serif font-bold text-2xl sm:text-3xl text-cobalt mb-2">{gizmo.title}</h1>
      <p className="text-sm text-steel mb-6">{gizmo.date}</p>

      <div className="flex flex-wrap gap-3 mb-8">
        <a
          href={CODE_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 text-sm font-sans font-semibold px-4 py-2 rounded-md bg-cobalt text-white hover:bg-cobalt/90 transition-colors"
        >
          Code, plan and results (GitHub)
          <ExternalLink className="w-3.5 h-3.5" />
        </a>
      </div>

      <article className="prose prose-slate max-w-none prose-headings:font-serif prose-headings:text-cobalt prose-a:text-carolina prose-a:no-underline hover:prose-a:underline prose-table:text-sm">
        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]} components={markdownComponents}>
          {technicalMd}
        </ReactMarkdown>
      </article>
    </div>
  );
}
