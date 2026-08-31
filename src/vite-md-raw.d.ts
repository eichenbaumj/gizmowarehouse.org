// Allow `?raw` imports of Markdown (and other) files as strings (Vite feature).
declare module "*.md?raw" {
  const content: string;
  export default content;
}
