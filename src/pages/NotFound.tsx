import { Link } from "react-router-dom";
import { usePageMeta } from "@/lib/usePageMeta";
import { notFoundSeo } from "@/lib/seo";

export default function NotFound() {
  // Lovable's host can't return a 404 status for an SPA route, so the page
  // declares itself noindex and canonicalizes to the homepage instead.
  usePageMeta(notFoundSeo());

  return (
    <div className="py-20 text-center">
      <h1 className="font-serif font-bold text-2xl text-cobalt mb-3">404</h1>
      <p className="text-charcoal/70 mb-6">This page doesn't exist.</p>
      <Link to="/" className="text-carolina hover:underline">Back to the warehouse</Link>
    </div>
  );
}
