// Localhost-only preview of draft gizmos. `virtual:dev-drafts` is `undefined` in every mode except the
// `vite` dev server (see devDraftsPlugin in vite.config.ts), and this module additionally refuses to
// expose drafts unless the page is served from a loopback host. Generic: it never names a slug.
import type { ComponentType } from "react";
import type { Gizmo } from "@/data/gizmos";
import { devDrafts as raw } from "virtual:dev-drafts";

export interface DevDrafts {
  gizmos: Gizmo[];
  content: Record<string, string>;
  embeds: Record<string, ComponentType<any>>;
}

function onLoopback(): boolean {
  if (typeof window === "undefined") return false;
  const h = window.location.hostname;
  return h === "localhost" || h === "127.0.0.1" || h === "[::1]" || h === "::1";
}

export const devDrafts: DevDrafts | undefined = raw && onLoopback() ? raw : undefined;
