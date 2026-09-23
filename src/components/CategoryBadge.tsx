import { Link } from "react-router-dom";
import { categorySlug, type Category } from "@/data/gizmos";
import { cn } from "@/lib/utils";

const colorMap: Record<Category, string> = {
  "Public Safety": "bg-cobalt/10 text-cobalt",
  "Music": "bg-carolina/10 text-carolina",
  "Using AI": "bg-purple-100 text-purple-700",
  "City Government": "bg-amber-100 text-amber-800",
  "State Government": "bg-indigo-100 text-indigo-800",
  "Healthcare Policy": "bg-emerald-100 text-emerald-800",
  "NYC": "bg-sky-100 text-sky-800",
};

export default function CategoryBadge({ category, link = false }: { category: Category; link?: boolean }) {
  const cls = cn("text-xs font-sans font-semibold px-2.5 py-0.5 rounded-full", colorMap[category]);
  if (link) {
    return (
      <Link to={`/category/${categorySlug(category)}`} className={cn(cls, "hover:underline")}>
        {category}
      </Link>
    );
  }
  return <span className={cls}>{category}</span>;
}
