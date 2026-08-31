// Maps DOF building-class codes to short human-readable labels.
//
// Source: NYC DCP MapPLUTO data dictionary, simplified for popup display.
// Imprecise on purpose — a `D4` building could be rental, condo, or co-op
// depending on legal structure not visible in the class code. The popup's
// year-built + unit-count line adds the missing context.

export function bldgClassLabel(code: string | undefined | null): string {
  if (!code) return "Building";
  const c = code.trim().toUpperCase();
  if (c.length === 0) return "Building";

  // Specific 2-char prefixes first.
  if (c === "R0") return "Condo (billing umbrella)";
  if (c.startsWith("R")) return "Condo apartment";
  if (c.startsWith("C6") || c.startsWith("C7") || c.startsWith("C8")) {
    return "Walk-up co-op";
  }
  if (c.startsWith("C")) return "Walk-up apartment";
  if (c.startsWith("D")) return "Elevator apartment building";

  // Single-char prefixes.
  switch (c[0]) {
    case "A":
      return "Single-family home";
    case "B":
      return "Two-family home";
    case "F":
      return "Factory or warehouse";
    case "G":
      return "Parking garage";
    case "H":
      return "Hotel";
    case "K":
      return "Mixed retail + apartments";
    case "L":
      return "Loft building";
    case "N":
      return "Group home";
    case "O":
      return "Office building";
    case "S":
      return "Mixed-use (small)";
    default:
      return "Building";
  }
}
