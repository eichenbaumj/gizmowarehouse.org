// isTouchPrimary — the single mobile/desktop gate for the Medicaid maps.
//
// Returns true only when the device's PRIMARY pointer is coarse (a finger):
// phones and tablets. A desktop with a mouse/trackpad — at ANY window width —
// returns false, and a touchscreen laptop whose primary pointer is the
// trackpad also returns false. This is the exact predicate the map already
// used inline for cooperativeGestures (matchMedia("(pointer: coarse)")), now
// shared so the mobile-only memory optimizations key off the same signal.
//
// Deliberately a pure, read-once function (not a reactive hook): both MapLibre
// instances build their style once in a []-effect and can't restyle on resize
// without a full teardown we don't want, so the gate is read a single time at
// mount. Desktop is therefore the untouched fallback for every caller — when
// this returns false, callers must reproduce today's exact behavior.
export function isTouchPrimary(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia?.("(pointer: coarse)").matches ?? false;
}
