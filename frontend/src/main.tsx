import React from "react";
import ReactDOM from "react-dom/client";
import { SaathiApp } from "./saathi/SaathiApp";
import "./index.css";

// GujRERA Saathi. Pramaan's original console (src/App.tsx) is kept in the repo but no longer mounted.
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <SaathiApp />
  </React.StrictMode>
);
