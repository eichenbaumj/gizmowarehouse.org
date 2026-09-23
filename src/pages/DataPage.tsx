// Renders a programmatic data page (src/data/dataPages/) at /gizmo/<slug>/*.
// The dataset's files are fetched in the browser (or supplied by the static
// renderer), the pages are built from them, and the one matching this path is
// shown. Unknown paths fall through to NotFound.
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { gizmos } from "@/data/gizmos";
import { buildDataset, datasetForSlug, type Cell, type DataPage as DataPageModel, type DatasetSpec } from "@/data/dataPages";
import NotFound from "@/pages/NotFound";
import { usePageMeta } from "@/lib/usePageMeta";
import { dataPageSeo } from "@/lib/seo";
import { useStaticData } from "@/lib/staticData";

// Built pages are cached per dataset so navigating between a state and its
// jurisdictions doesn't rebuild a thousand pages each time.
const pageCache = new Map<string, Map<string, DataPageModel>>();
function pagesFor(spec: DatasetSpec, files: Record<string, unknown>): Map<string, DataPageModel> {
  let m = pageCache.get(spec.id);
  if (!m) {
    m = new Map(buildDataset(spec, files).pages.map((p) => [p.path, p]));
    pageCache.set(spec.id, m);
  }
  return m;
}

function CellView({ c }: { c: Cell }) {
  if (typeof c === "object" && c !== null && "href" in c) {
    return c.href.startsWith("/") ? <Link to={c.href}>{c.text}</Link> : <a href={c.href} target="_blank" rel="noopener noreferrer">{c.text}</a>;
  }
  return <>{c}</>;
}

function Smart({ href, children }: { href: string; children: React.ReactNode }) {
  return href.startsWith("/") ? <Link to={href}>{children}</Link> : <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
}

export function DataPageView({ page }: { page: DataPageModel }) {
  const parent = gizmos.find((g) => g.slug === page.parentSlug);
  return (
    <div>
      <nav aria-label="Breadcrumb" className="text-sm text-steel mb-8">
        {page.crumbs.map((c, i) => (
          <span key={c.path}>
            {i > 0 && <span className="mx-1.5">/</span>}
            {i < page.crumbs.length - 1 ? <Link to={c.path} className="hover:text-cobalt">{c.name}</Link> : <span>{c.name}</span>}
          </span>
        ))}
      </nav>

      <p className="text-xs font-sans font-semibold uppercase tracking-wide text-carolina mb-2">{page.kicker}</p>
      <h1 className="font-serif font-bold text-2xl sm:text-3xl text-cobalt mb-3">{page.title}</h1>
      <p className="text-sm text-steel mb-8">
        Data snapshot {page.snapshot}
        {parent && (
          <>
            {" · part of "}
            <Link to={`/gizmo/${parent.slug}`} className="text-carolina hover:underline">{parent.title}</Link>
          </>
        )}
      </p>

      <article className="prose prose-slate max-w-none prose-headings:font-serif prose-headings:text-cobalt prose-a:text-carolina prose-a:no-underline hover:prose-a:underline">
        {page.intro.map((p, i) => (
          <p key={i} className={i === 0 ? "lead" : undefined}>{p}</p>
        ))}
        {page.sections.map((s, i) => (
          <section key={i}>
            {s.heading && <h2 id={s.heading.toLowerCase().replace(/[^a-z0-9]+/g, "-")}>{s.heading}</h2>}
            {s.paragraphs?.map((p, j) => <p key={j}>{p}</p>)}
            {s.table && (
              <div className="overflow-x-auto">
                <table>
                  {s.table.caption && <caption className="text-left text-sm text-steel caption-bottom">{s.table.caption}</caption>}
                  <thead>
                    <tr>{s.table.head.map((h) => <th key={h}>{h}</th>)}</tr>
                  </thead>
                  <tbody>
                    {s.table.rows.map((r, k) => (
                      <tr key={k}>{r.map((c, m) => <td key={m}><CellView c={c} /></td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {s.list && (
              <ul>
                {s.list.map((it, j) => (
                  <li key={j}>
                    {it.href ? <Smart href={it.href}>{it.text}</Smart> : it.text}
                    {it.detail && <span className="block text-sm text-charcoal/80">{it.detail}</span>}
                  </li>
                ))}
              </ul>
            )}
            {s.note && <p className="text-sm text-steel">{s.note}</p>}
          </section>
        ))}

        <h2 id="sources">Sources</h2>
        <ul>
          {page.sources.map((s) => (
            <li key={s.href}><Smart href={s.href}>{s.name}</Smart></li>
          ))}
        </ul>
      </article>

      <aside className="mt-12 pt-6 border-t border-carolina/30 text-sm">
        <span className="text-steel mr-2">See also:</span>
        {page.related.map((r, i) => (
          <span key={r.href}>
            {i > 0 && <span className="text-steel mx-1.5">·</span>}
            <Smart href={r.href}><span className="text-carolina hover:underline">{r.text}</span></Smart>
          </span>
        ))}
      </aside>
      <p className="mt-6">
        <Link to={parent ? `/gizmo/${parent.slug}` : "/"} className="inline-flex items-center gap-1.5 text-sm text-steel hover:text-cobalt transition-colors">
          <ArrowLeft className="w-4 h-4" />
          {parent ? `Back to ${parent.title}` : "All gizmos"}
        </Link>
      </p>
    </div>
  );
}

export default function DataPage() {
  const { slug } = useParams<{ slug: string }>();
  const location = useLocation();
  const spec = slug ? datasetForSlug(slug) : undefined;
  const staticData = useStaticData();
  const path = location.pathname.replace(/\/+$/, "");

  const [files, setFiles] = useState<Record<string, unknown> | null>(() => {
    if (!spec) return null;
    return spec.files.every((f) => f in staticData.dataContexts) ? staticData.dataContexts : null;
  });
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!spec || files || staticData.isStatic) return;
    let cancelled = false;
    Promise.all(spec.files.map((f) => fetch(f).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${f}: HTTP ${r.status}`))))))
      .then((loaded) => {
        if (cancelled) return;
        setFiles(Object.fromEntries(spec.files.map((f, i) => [f, loaded[i]])));
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [spec, files, staticData.isStatic]);

  const page = useMemo(() => (spec && files ? pagesFor(spec, files).get(path) : undefined), [spec, files, path]);

  usePageMeta(page ? dataPageSeo(page) : { title: "Loading | Gizmo Warehouse", description: "", canonical: `https://gizmowarehouse.org${path}`, noindex: !page });

  if (!spec || failed || (files && !page)) return <NotFound />;
  if (!page) return <p className="py-20 text-center text-steel">Loading…</p>;
  return <DataPageView page={page} />;
}
