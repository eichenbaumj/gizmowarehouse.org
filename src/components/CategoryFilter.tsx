import type { Category } from "@/data/gizmos";
import { ALL_CATEGORIES } from "@/data/gizmos";
import { cn } from "@/lib/utils";

interface Props {
  selected: Category | null;
  onSelect: (cat: Category | null) => void;
}

export default function CategoryFilter({ selected, onSelect }: Props) {
  return (
    <div className="flex flex-wrap gap-2">
      <button
        onClick={() => onSelect(null)}
        className={cn(
          "text-sm font-sans px-4 py-1.5 rounded-full border transition-colors",
          selected === null
            ? "bg-cobalt text-white border-cobalt"
            : "border-border text-charcoal hover:border-cobalt/40"
        )}
      >
        All
      </button>
      {ALL_CATEGORIES.map((cat) => (
        <button
          key={cat}
          onClick={() => onSelect(cat === selected ? null : cat)}
          className={cn(
            "text-sm font-sans px-4 py-1.5 rounded-full border transition-colors",
            selected === cat
              ? "bg-cobalt text-white border-cobalt"
              : "border-border text-charcoal hover:border-cobalt/40"
          )}
        >
          {cat}
        </button>
      ))}
    </div>
  );
}
