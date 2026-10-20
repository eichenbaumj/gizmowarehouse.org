/// <reference types="vite/client" />

declare module "*.md" {
  const content: string;
  export default content;
}

declare module "virtual:dev-drafts" {
  import type { DevDrafts } from "@/lib/devDrafts";
  export const devDrafts: DevDrafts | undefined;
}
