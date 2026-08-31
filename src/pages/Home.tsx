import { useState } from "react";
import type { Category } from "@/data/gizmos";
import { gizmos } from "@/data/gizmos";
import CategoryFilter from "@/components/CategoryFilter";
import GizmoCard from "@/components/GizmoCard";
import { SITE_URL, usePageMeta } from "@/lib/usePageMeta";

export default function Home() {
  usePageMeta({
    title: "Gizmo Warehouse | 17A",
    description: "Shareable tools, analyses, and work products from Joe Eichenbaum at 17A.",
    canonical: `${SITE_URL}/`,
    jsonLd: [
      {
        "@context": "https://schema.org",
        "@type": "WebSite",
        name: "Gizmo Warehouse",
        url: SITE_URL,
      },
      {
        "@context": "https://schema.org",
        "@type": "Organization",
        name: "17A",
        url: "https://www.17a.co",
        founder: { "@type": "Person", name: "Joe Eichenbaum" },
      },
    ],
  });

  const [selected, setSelected] = useState<Category | null>(null);

  const visible = gizmos.filter((g) => !g.hidden);
  const filtered = selected
    ? visible.filter((g) => g.categories.includes(selected))
    : visible;

  return (
    <div>
      <div className="mb-10">
        <h1 className="font-serif font-bold text-3xl text-cobalt mb-3">Gizmo Warehouse</h1>
        <p className="text-charcoal/80 leading-relaxed max-w-2xl">
          The Gizmo Warehouse is more of a workshop than a showroom. The thinking behind these gizmos is proudly in progress. The analyses follow the data, but there's a lot of interpretation between the numbers and the ground, and surely we're missing context somewhere. The warehouse is built this way on purpose, because it's fun to discover the answers in public. If a gizmo here sparks something, <a href="mailto:joe@group17a.com" className="text-cobalt hover:underline">reach out</a>.
        </p>
      </div>

      <div className="mb-8">
        <CategoryFilter selected={selected} onSelect={setSelected} />
      </div>

      <div className="grid gap-5 sm:grid-cols-2">
        {filtered.map((gizmo) => (
          <GizmoCard key={gizmo.slug} gizmo={gizmo} />
        ))}
      </div>

      {filtered.length === 0 && (
        <p className="text-steel text-sm py-10 text-center">Nothing here yet in this category.</p>
      )}
    </div>
  );
}
