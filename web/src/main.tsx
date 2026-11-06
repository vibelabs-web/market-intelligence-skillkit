import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import "./index.css";
import Layout from "./components/Layout";
import Start from "./pages/Start";
import NewProject from "./pages/NewProject";
import Research from "./pages/Research";
import Project from "./pages/Project";
import Review from "./pages/Review";
import Library from "./pages/Library";
import Criteria from "./pages/Criteria";
import Goldens from "./pages/Goldens";
import Dev from "./pages/Dev";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Start />} />
          <Route path="projects/new" element={<NewProject />} />
          <Route path="projects/:id/research" element={<Research />} />
          <Route path="projects/:id" element={<Project />} />
          <Route path="briefs/:run" element={<Review />} />
          <Route path="library" element={<Library />} />
          <Route path="criteria" element={<Criteria />} />
          <Route path="goldens" element={<Goldens />} />
          <Route path="dev" element={<Dev />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
