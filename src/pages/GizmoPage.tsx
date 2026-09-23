import { Children, Fragment, isValidElement, useEffect, useState, type ReactNode } from "react";
import { useParams, Link, useSearchParams } from "react-router-dom";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { gizmos } from "@/data/gizmos";
import CategoryBadge from "@/components/CategoryBadge";
import ReadModeToggle, { type ReadMode } from "@/components/ReadModeToggle";
import { ReadModeContext } from "@/lib/readMode";
import { gizmoContent, gizmoBlufContent } from "@/content";
import { gizmoEmbeds } from "@/content/embeds";
import { interpolateTokens } from "@/lib/interpolateTokens";
import { usePageMeta } from "@/lib/usePageMeta";
import { gizmoSeo, notFoundSeo, relatedGizmos } from "@/lib/seo";
import { useStaticData } from "@/lib/staticData";
import GizmoCard from "@/components/GizmoCard";

// Custom HTML-style tags in markdown (e.g. <nyc-tax-map />) resolve to React
// components from the embed registry. `gizmoEmbeds` is a stable module-scope
// object, so component identities don't change across renders.
//
// Markdown auto-wraps standalone elements in a <p>, which is invalid HTML
// when the child renders a <div> (which all our embeds do). Override `p` to
// detect a registered embed child and unwrap.
const embedTypes = new Set(Object.values(gizmoEmbeds));

function childContainsEmbed(children: ReactNode): boolean {
  return Children.toArray(children).some((child) => {
    if (isValidElement(child)) {
      return embedTypes.has(child.type as any);
    }
    return false;
  });
}

/** Slugify a heading's text for use as an anchor id. */
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
  ...(gizmoEmbeds as Components),
  p: ({ children, ...props }) => {
    if (childContainsEmbed(children)) {
      return <Fragment>{children}</Fragment>;
    }
    return <p {...props}>{children}</p>;
  },
  // Auto-id H2/H3 so popup methodology links can scroll-target them via #anchor.
  h2: ({ children, ...props }) => (
    <h2 id={headingSlug(children)} {...props}>{children}</h2>
  ),
  h3: ({ children, ...props }) => (
    <h3 id={headingSlug(children)} {...props}>{children}</h3>
  ),
  h4: ({ children, ...props }) => (
    <h4 id={headingSlug(children)} {...props}>{children}</h4>
  ),
};

export default function GizmoPage() {
  const { slug } = useParams<{ slug: string }>();
  const gizmo = gizmos.find((g) => g.slug === slug);

  usePageMeta(gizmo ? gizmoSeo(gizmo) : notFoundSeo());

  if (!gizmo) {
    return (
      <div className="py-20 text-center">
        <p className="text-steel mb-4">Gizmo not found.</p>
        <Link to="/" className="text-cobalt hover:underline">Back to all gizmos</Link>
      </div>
    );
  }

  // Read-mode (full vs. short-form "BLUF") is carried in a ?view= URL param so
  // the short version is shareable as its own link. A gizmo offers BLUF only if
  // it has an entry in gizmoBlufContent; otherwise the toggle never renders.
  const [searchParams, setSearchParams] = useSearchParams();
  const blufAvailable = !!gizmoBlufContent[gizmo.slug];
  const mode: ReadMode =
    blufAvailable && searchParams.get("view") === "bluf" ? "bluf" : "full";

  const setMode = (next: ReadMode) =>
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        if (next === "bluf") params.set("view", "bluf");
        else params.delete("view");
        return params;
      },
      { replace: false }
    );

  const rawContent =
    (mode === "bluf" ? gizmoBlufContent[gizmo.slug] : gizmoContent[gizmo.slug]) || "";

  // Load optional data context for {tokenName} interpolation. At build time
  // the static renderer supplies it up front (src/lib/staticData.tsx) so the
  // figures are baked into the crawlable HTML; in the browser we fetch it.
  const staticData = useStaticData();
  const [dataContext, setDataContext] = useState<Record<string, any> | null>(
    () => (gizmo.dataContextUrl ? (staticData.dataContexts[gizmo.dataContextUrl] as Record<string, any>) ?? null : null)
  );
  useEffect(() => {
    if (staticData.isStatic) return;
    if (!gizmo.dataContextUrl) {
      setDataContext(null);
      return;
    }
    fetch(gizmo.dataContextUrl)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
      .then(setDataContext)
      .catch(() => setDataContext(null));
  }, [gizmo.dataContextUrl, staticData.isStatic]);

  const related = relatedGizmos(gizmo, gizmos);
  const content = interpolateTokens(rawContent, dataContext);

  return (
    <div>
      <Link
        to="/"
        className="inline-flex items-center gap-1.5 text-sm text-steel hover:text-cobalt transition-colors mb-8"
      >
        <ArrowLeft className="w-4 h-4" />
        All gizmos
      </Link>

      <div className="flex flex-wrap gap-1.5 mb-4">
        {gizmo.categories.map((cat) => (
          <CategoryBadge key={cat} category={cat} link />
        ))}
      </div>

      <h1 className="font-serif font-bold text-2xl sm:text-3xl text-cobalt mb-2">
        {gizmo.title}
      </h1>
      {gizmo.dek && (
        <p className="font-serif text-lg leading-snug text-charcoal/75 mb-2 max-w-3xl">
          {gizmo.dek}
        </p>
      )}
      <p className="text-sm text-steel mb-8">{gizmo.date}</p>

      {gizmo.links && gizmo.links.length > 0 && (
        <div className="flex flex-wrap gap-3 mb-8">
          {gizmo.links.map((link) => (
            <a
              key={link.url}
              href={link.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-sm font-sans font-semibold px-4 py-2 rounded-md bg-cobalt text-white hover:bg-cobalt/90 transition-colors"
            >
              {link.label}
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          ))}
        </div>
      )}

      {blufAvailable && <ReadModeToggle mode={mode} onChange={setMode} />}

      <article className="prose prose-slate max-w-none prose-headings:font-serif prose-headings:text-cobalt prose-a:text-carolina prose-a:no-underline hover:prose-a:underline">
        <ReadModeContext.Provider value={mode}>
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeRaw]}
            components={markdownComponents}
          >
            {content}
          </ReactMarkdown>
        </ReadModeContext.Provider>
      </article>

      {related.length > 0 && (
        <aside className="mt-16 pt-8 border-t border-carolina/30" aria-labelledby="related-heading">
          <h2 id="related-heading" className="font-serif font-bold text-xl text-cobalt mb-5">More from the warehouse</h2>
          <div className="grid gap-5 sm:grid-cols-3">
            {related.map((g) => (
              <GizmoCard key={g.slug} gizmo={g} compact />
            ))}
          </div>
        </aside>
      )}
    </div>
  );
}
