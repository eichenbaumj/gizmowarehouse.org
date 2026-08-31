// ReadModeToggle — a small segmented control for switching a gizmo detail page
// between the full piece and its short-form "BLUF" (Bottom Line Up Front) cut.
// Presentational only: the parent owns the mode (GizmoPage maps it to a ?view
// URL param) and passes it back down. Rendered only when a BLUF variant exists,
// so it's a drop-in for any future gizmo that gets one.

export type ReadMode = "full" | "bluf";

interface ReadModeToggleProps {
  mode: ReadMode;
  onChange: (mode: ReadMode) => void;
}

const OPTIONS: { key: ReadMode; label: string }[] = [
  { key: "full", label: "Full read" },
  { key: "bluf", label: "BLUF mode" },
];

export default function ReadModeToggle({ mode, onChange }: ReadModeToggleProps) {
  return (
    <div className="mb-8 flex flex-wrap items-center gap-x-3 gap-y-2">
      <div className="inline-flex rounded-lg border border-cobalt/30 bg-white p-1 shadow-sm">
        {OPTIONS.map((o) => (
          <button
            key={o.key}
            type="button"
            onClick={() => onChange(o.key)}
            aria-pressed={mode === o.key}
            className={
              "rounded-md px-4 py-2 text-sm font-sans font-semibold transition-colors " +
              (mode === o.key
                ? "bg-cobalt text-white"
                : "text-cobalt hover:bg-cobalt/5")
            }
          >
            {o.label}
          </button>
        ))}
      </div>
      <span className="text-xs text-steel">
        {mode === "bluf"
          ? "The short executive version. Charts kept."
          : "Reading the full piece. Short on time? Try BLUF."}
      </span>
    </div>
  );
}
