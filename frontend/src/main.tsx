import React from "react";
import ReactDOM from "react-dom/client";
import WizardApp from "./WizardApp";
import "./styles.css";
import "./wizard.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <WizardApp />
  </React.StrictMode>
);
