// One page per category: /category/<slug>. A real, crawlable list (the home
// page's filter is client-side state and invisible to a crawler), and the
// place internal links from badges land.
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { ALL_CATEGORIES, categoryFromSlug, categorySlug, gizmos } from "@/data/gizmos";
import GizmoCard from "@/components/GizmoCard";
import NotFound from "@/pages/NotFound";
import { usePageMeta } from "@/lib/usePageMeta";
import { DEFAULT_OG_IMAGE, SITE_NAME, SITE_URL, breadcrumbJsonLd } from "@/lib/seo";
import { CATEGORY_BLURBS } from "@/lib/categories";

export default function CategoryPage() {
  const { category: slug } = useParams<{ category: string }>();
  const category = slug ? categoryFromSlug(slug) : undefined;
  const items = category ? gizmos.filter((g) => !g.hidden && g.categories.includes(category)) : [];
  const canonical = category ? `${SITE_URL}/category/${categorySlug(category)}` : `${SITE_URL}/`;
  const blurb = category ? CATEGORY_BLURBS[category] : "";

  usePageMeta(
    category && items.length > 0
      ? {
          title: `${category} | ${SITE_NAME}`,
          description: `${blurb} ${items.length} gizmo${items.length === 1 ? "" : "s"} from Joe Eichenbaum at 17A.`,
          canonical,
          ogImage: DEFAULT_OG_IMAGE,
          ogType: "website",
          jsonLd: [
            {
              "@context": "https://schema.org",
              "@type": "CollectionPage",
              name: category,
              url: canonical,
              description: blurb,
              hasPart: items.map((g) => ({ "@type": "Article", headline: g.title, url: `${SITE_URL}/gizmo/${g.slug}` })),
            },
            breadcrumbJsonLd([
              { name: SITE_NAME, url: `${SITE_URL}/` },
              { name: category, url: canonical },
            ]),
          ],
        }
      : { title: `Not Found | ${SITE_NAME}`, description: "", canonical: `${SITE_URL}/`, ogImage: DEFAULT_OG_IMAGE, ogType: "website", noindex: true }
  );

  if (!category || items.length === 0) return <NotFound />;

  return (
    <div>
      <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-steel hover:text-cobalt transition-colors mb-8">
        <ArrowLeft className="w-4 h-4" />
        All gizmos
      </Link>
      <h1 className="font-serif font-bold text-3xl text-cobalt mb-3">{category}</h1>
      <p className="text-charcoal/80 leading-relaxed max-w-2xl mb-8">{blurb}</p>
      <div className="grid gap-5 sm:grid-cols-2">
        {items.map((g) => (
          <GizmoCard key={g.slug} gizmo={g} />
        ))}
      </div>
      <p className="text-sm text-steel mt-10">
        Other categories:{" "}
        {ALL_CATEGORIES.filter((c) => c !== category && gizmos.some((g) => !g.hidden && g.categories.includes(c))).map((c, i, arr) => (
          <span key={c}>
            <Link to={`/category/${categorySlug(c)}`} className="text-carolina hover:underline">{c}</Link>
            {i < arr.length - 1 ? ", " : ""}
          </span>
        ))}
      </p>
    </div>
  );
}
