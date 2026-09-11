import { Link } from "react-router-dom";
import "./emptyState.css";

// Replaces the plain `<p className="hint">` empty-state text scattered
// across TendersPage.jsx, TenderDashboardPage.jsx, and the bidder detail
// page's document list.
export function EmptyState({ message, actionLabel, actionTo }) {
  const hasAction = Boolean(actionLabel && actionTo);
  return (
    <div className="empty-state">
      <p className="empty-state-message">{message}</p>
      {hasAction && (
        <Link to={actionTo} className="empty-state-action">
          {actionLabel}
        </Link>
      )}
    </div>
  );
}
