// Prints src/data/gizmos.ts as JSON for non-TS tooling (tools/generate-og-cards.py).
import { gizmos } from "../src/data/gizmos";
process.stdout.write(JSON.stringify(gizmos));
