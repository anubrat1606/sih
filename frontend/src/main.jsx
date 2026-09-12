import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./design/tokens.css";
import "./design/base.css";
import "./design/components.css";
import "./design/shell.css";
import "./design/bidder.css";
import "./notifications/notifications.css";
import App from "./App.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>
);
