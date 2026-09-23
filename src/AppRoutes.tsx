// The route table, shared by the browser app (src/App.tsx, BrowserRouter) and
// the build-time static render (src/entry-static.tsx, StaticRouter). Add a
// route here once and both get it. Keep src/lib/routes.ts in step so the
// sitemap and the prerenderer know the route exists.
import { Routes, Route, Navigate } from "react-router-dom";
import Home from "@/pages/Home";
import GizmoPage from "@/pages/GizmoPage";
import DataPage from "@/pages/DataPage";
import CategoryPage from "@/pages/CategoryPage";
import MedicaidMethodology from "@/pages/MedicaidMethodology";
import CompGapMethodology from "@/pages/CompGapMethodology";
import NotFound from "@/pages/NotFound";

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/category/:category" element={<CategoryPage />} />
      {/* Public methodology pages (more specific than /gizmo/:slug). */}
      <Route path="/gizmo/medicaid-work-requirements/methodology" element={<MedicaidMethodology />} />
      <Route path="/gizmo/public-private-compensation-comparison/methodology" element={<CompGapMethodology />} />
      {/* The grocery update briefly went live at this slug; keep the old URL working. */}
      <Route path="/gizmo/nyc-public-grocery-math-30" element={<Navigate to="/gizmo/nyc-public-grocery-new-math" replace />} />
      <Route path="/gizmo/:slug" element={<GizmoPage />} />
      {/* Programmatic data pages (state, county, city, jurisdiction) under a gizmo. See src/data/dataPages. */}
      <Route path="/gizmo/:slug/*" element={<DataPage />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
