import { useState } from "react";

export default function InterruptPrompt({ pending, onResolve, busy }) {
  const [feedback, setFeedback] = useState("");
  const [showFeedback, setShowFeedback] = useState(false);

  if (!pending) return null;

  const handleClick = (action) => {
    if (pending.requires_feedback && action === "edit" && !showFeedback) {
      setShowFeedback(true);
      return;
    }
    onResolve(action, feedback);
    setShowFeedback(false);
    setFeedback("");
  };

  return (
    <div className="interrupt-card">
      <div className="interrupt-header">Needs your input — {pending.type.replace("_", " ")}</div>

      {pending.type === "email_review" && (
        <pre className="interrupt-draft">{pending.payload.draft}</pre>
      )}
      {pending.type === "confirm_booking" && (
        <div className="interrupt-draft">
          Book flight <b>{pending.payload.flight_id}</b> for <b>{pending.payload.passenger_name}</b>?
        </div>
      )}

      {showFeedback && (
        <textarea
          className="interrupt-feedback"
          placeholder="What should change?"
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
        />
      )}

      <div className="interrupt-actions">
        {pending.actions.map((a) => (
          <button
            key={a.action}
            className={`btn ${a.action === "approve" || a.action === "confirm" ? "btn-primary" : "btn-secondary"}`}
            disabled={busy}
            onClick={() => handleClick(a.action)}
          >
            {a.label}
          </button>
        ))}
        {showFeedback && (
          <button className="btn btn-primary" disabled={busy} onClick={() => handleClick("edit")}>
            Send feedback
          </button>
        )}
      </div>
    </div>
  );
}
