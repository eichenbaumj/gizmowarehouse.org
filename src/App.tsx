import { BrowserRouter } from "react-router-dom";
import Layout from "@/components/Layout";
import AppRoutes from "@/AppRoutes";

const App = () => (
  <BrowserRouter>
    <Layout>
      <AppRoutes />
    </Layout>
  </BrowserRouter>
);

export default App;
