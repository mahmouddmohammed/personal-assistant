export default function Sidebar({ conversations, activeId, onSelect, onNew, username, isAdmin, onLogout, onGoAdmin }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <span className="brand">Personal Assistant</span>
      </div>
      <button className="btn btn-primary new-chat-btn" onClick={onNew}>+ New chat</button>
      <div className="conversation-list">
        {conversations.map((c) => (
          <div
            key={c.id}
            className={`conversation-item ${c.id === activeId ? "active" : ""}`}
            onClick={() => onSelect(c.id)}
          >
            {c.title || "New conversation"}
          </div>
        ))}
      </div>
      <div className="sidebar-footer">
        <div className="user-chip">{username}{isAdmin && <span className="admin-badge">admin</span>}</div>
        {isAdmin && <button className="btn btn-secondary" onClick={onGoAdmin}>Admin panel</button>}
        <button className="btn btn-secondary" onClick={onLogout}>Log out</button>
      </div>
    </aside>
  );
}
