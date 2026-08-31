import { Link } from "react-router-dom";
import type { Gizmo } from "@/data/gizmos";
import CategoryBadge from "./CategoryBadge";

export default function GizmoCard({ gizmo }: { gizmo: Gizmo }) {
  return (
    <Link
      to={`/gizmo/${gizmo.slug}`}
      className="block border border-border rounded-lg p-6 hover:border-carolina/60 hover:shadow-sm transition-all group"
    >
      <div className="flex flex-wrap gap-1.5 mb-3">
        {gizmo.categories.map((cat) => (
          <CategoryBadge key={cat} category={cat} />
        ))}
      </div>
      <h3 className="font-serif font-bold text-lg text-charcoal group-hover:text-cobalt transition-colors mb-2">
        {gizmo.title}
      </h3>
      <p className="text-sm text-charcoal/70 leading-relaxed">{gizmo.summary}</p>
      <p className="text-xs text-steel mt-3">{gizmo.date}</p>
    </Link>
  );
}
