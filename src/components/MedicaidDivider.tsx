// MedicaidDivider — a cobalt accent rule between H2 sections of the content
// markdown. Renders as a 2px cobalt line at 30% opacity. Lightweight.

export default function MedicaidDivider() {
  return (
    <div
      className="not-prose my-12 flex items-center justify-center"
      aria-hidden
    >
      <div
        className="h-px w-full max-w-md"
        style={{
          background:
            "linear-gradient(to right, transparent, rgba(31, 31, 214, 0.3) 30%, rgba(31, 31, 214, 0.3) 70%, transparent)",
        }}
      />
    </div>
  );
}
