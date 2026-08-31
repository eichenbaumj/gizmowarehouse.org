import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Layout from "@/components/Layout";
import Home from "@/pages/Home";
import GizmoPage from "@/pages/GizmoPage";
import MedicaidMethodology from "@/pages/MedicaidMethodology";
import CompGapMethodology from "@/pages/CompGapMethodology";
import NotFound from "@/pages/NotFound";

const App = () => (
  <BrowserRouter>
    <Layout>
      <Routes>
        <Route path="/" element={<Home />} />
        {/* Public methodology pages (more specific than /gizmo/:slug). */}
        <Route path="/gizmo/medicaid-work-requirements/methodology" element={<MedicaidMethodology />} />
        <Route path="/gizmo/public-private-compensation-comparison/methodology" element={<CompGapMethodology />} />
        {/* The grocery update briefly went live at this slug; keep the old URL working. */}
        <Route path="/gizmo/nyc-public-grocery-math-30" element={<Navigate to="/gizmo/nyc-public-grocery-new-math" replace />} />
        <Route path="/gizmo/:slug" element={<GizmoPage />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Layout>
  </BrowserRouter>
);

export default App;
