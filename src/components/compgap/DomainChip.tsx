// A domain filter chip with a hover/focus tooltip explaining which occupations
// the filter includes (note 8). Pure CSS popover — no positioning library.

interface Props {
  label: string;
  selected: boolean;
  onClick: () => void;
  includes?: string;
  elite?: boolean;
  size?: "sm" | "md";
}

export default function DomainChip({ label, selected, onClick, includes, elite, size = "md" }: Props) {
  const pad = size === "sm" ? "px-2.5 py-0.5 text-[12px]" : "px-3 py-1 text-[12.5px]";
  return (
    <span className="group relative inline-flex">
      <button
        onClick={onClick}
        aria-label={includes ? `${label}: ${includes}` : label}
        className={
          "rounded-full border transition-colors " + pad + " " +
          (selected
            ? "border-cobalt bg-cobalt text-white"
            : "border-slate-300 bg-white text-charcoal hover:border-cobalt/50")
        }
      >
        {label}
        {elite ? <span className="ml-1 opacity-60">★</span> : null}
      </button>
      {includes && (
        <span
          role="tooltip"
          className="pointer-events-none absolute left-0 top-full z-30 mt-1 hidden w-60 rounded-md border border-slate-200 bg-white p-2.5 text-left text-[11.5px] font-normal leading-snug text-charcoal/80 shadow-lg group-hover:block group-focus-within:block"
        >
          <span className="font-semibold text-cobalt">{label}.</span> {includes}
        </span>
      )}
    </span>
  );
}
