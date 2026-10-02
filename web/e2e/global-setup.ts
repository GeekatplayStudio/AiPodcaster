import { rmSync } from "node:fs";
import { resolve } from "node:path";

/** Start every e2e run from an empty data directory so selectors stay unambiguous. */
export default function globalSetup(): void {
  rmSync(resolve(import.meta.dirname, "../../backend/tests/.e2e-data"), { recursive: true, force: true });
}
