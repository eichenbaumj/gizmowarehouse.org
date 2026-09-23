// Runtime <head> management for the SPA. Takes the same PageSeo shape that
// tools/prerender.ts bakes into the static HTML (see src/lib/seo.ts), so the
// two views agree tag for tag. On a static-rendered page the tags already
// exist and this hook just keeps them in step as the reader navigates.
import { useEffect } from "react";
import { DEFAULT_OG_IMAGE, OG_IMAGE_SIZE, SITE_NAME, type PageSeo } from "./seo";

export { SITE_URL } from "./seo";

export function usePageMeta(seo: PageSeo) {
  const { title, socialTitle, description, canonical, datePublished, dateModified, noindex, jsonLd } = seo;
  const ogImage = seo.ogImage || DEFAULT_OG_IMAGE;
  const ogType = seo.ogType || "website";
  // Pages build jsonLd inline, so compare by value, not identity.
  const jsonLdKey = JSON.stringify(jsonLd ?? null);
  useEffect(() => {
    document.title = title;
    setMeta("description", description);
    setLink("canonical", canonical);
    setMeta("og:site_name", SITE_NAME, true);
    setMeta("og:title", socialTitle || title, true);
    setMeta("og:description", description, true);
    setMeta("og:url", canonical, true);
    setMeta("og:type", ogType, true);
    setMeta("twitter:title", socialTitle || title);
    setMeta("twitter:description", description);
    setMeta("og:image", ogImage, true);
    setMeta("og:image:width", String(OG_IMAGE_SIZE.width), true);
    setMeta("og:image:height", String(OG_IMAGE_SIZE.height), true);
    setMeta("og:image:alt", socialTitle || title, true);
    setMeta("twitter:image", ogImage);
    if (ogType === "article" && datePublished) {
      setMeta("article:published_time", datePublished, true);
      if (dateModified) setMeta("article:modified_time", dateModified, true);
    } else {
      removeMeta("article:published_time", true);
      removeMeta("article:modified_time", true);
    }
    setMeta("robots", noindex ? "noindex, follow" : "index, follow, max-image-preview:large");
    setJsonLd(jsonLd);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [title, socialTitle, description, canonical, ogImage, ogType, datePublished, dateModified, noindex, jsonLdKey]);
}

function setMeta(name: string, content: string, isProperty = false) {
  const attr = isProperty ? "property" : "name";
  let el = document.head.querySelector<HTMLMetaElement>(`meta[${attr}="${name}"]`);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attr, name);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

function removeMeta(name: string, isProperty = false) {
  const attr = isProperty ? "property" : "name";
  document.head.querySelector(`meta[${attr}="${name}"]`)?.remove();
}

function setLink(rel: string, href: string) {
  let el = document.head.querySelector<HTMLLinkElement>(`link[rel="${rel}"]`);
  if (!el) {
    el = document.createElement("link");
    el.setAttribute("rel", rel);
    document.head.appendChild(el);
  }
  el.setAttribute("href", href);
}

export const JSON_LD_ID = "page-jsonld";
function setJsonLd(data?: object | object[]) {
  const existing = document.getElementById(JSON_LD_ID);
  if (existing) existing.remove();
  if (!data) return;
  const el = document.createElement("script");
  el.type = "application/ld+json";
  el.id = JSON_LD_ID;
  el.text = JSON.stringify(data);
  document.head.appendChild(el);
}
