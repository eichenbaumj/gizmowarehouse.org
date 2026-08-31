import { Link } from "react-router-dom";
import { SITE_URL, usePageMeta } from "@/lib/usePageMeta";

export default function NotFound() {
  usePageMeta({
    title: "Not Found | Gizmo Warehouse",
    description:
      "The page you're looking for doesn't exist. Head back to the Gizmo Warehouse to browse all available tools and analyses.",
    canonical: `${SITE_URL}/`,
  });

  return (
    <div className="py-20 text-center">
      <h1 className="font-serif font-bold text-2xl text-cobalt mb-3">404</h1>
      <p className="text-charcoal/70 mb-6">This page doesn't exist.</p>
      <Link to="/" className="text-carolina hover:underline">Back to the warehouse</Link>
    </div>
  );
}
