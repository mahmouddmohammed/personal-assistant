import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AdminAPI } from "../api/client";
import { useAuth } from "../context/AuthContext";

export default function AdminPage() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState("conversations");
  const [users, setUsers] = useState([]);
  const [conversations, setConversations] = useState([]);
  const [trace, setTrace] = useState(null);
  const [traceConvId, setTraceConvId] = useState(null);

  useEffect(() => {
    AdminAPI.listUsers().then((r) => setUsers(r.data));
    AdminAPI.listConversations().then((r) => setConversations(r.data));
  }, []);

  const openTrace = async (conversationId) => {
    setTraceConvId(conversationId);
    const { data } = await AdminAPI.conversationTrace(conversationId);
    setTrace(data);
  };

  // Group flat log rows by turn_id so each prompt's fired-node sequence is one block.
  const groupedTrace = (trace || []).reduce((acc, row) => {
    (acc[row.turn_id] ||= []).push(row);
    return acc;
  }, {});

  return (
    <div className="admin-shell">
      <header className="admin-header">
        <h1>Admin panel</h1>
        <div>
          <button className="btn btn-secondary" onClick={() => navigate("/chat")}>Back to chat</button>
          <button className="btn btn-secondary" onClick={() => { logout(); navigate("/login"); }}>Log out</button>
        </div>
      </header>

      <nav className="admin-tabs">
        <button className={tab === "conversations" ? "active" : ""} onClick={() => setTab("conversations")}>Conversations</button>
        <button className={tab === "users" ? "active" : ""} onClick={() => setTab("users")}>Users</button>
      </nav>

      {tab === "users" && (
        <table className="admin-table">
          <thead>
            <tr><th>Username</th><th>Email</th><th>Admin</th><th>Conversations</th><th>Joined</th></tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.username}</td><td>{u.email}</td>
                <td>{u.is_admin ? "yes" : "no"}</td>
                <td>{u.conversation_count}</td>
                <td>{new Date(u.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {tab === "conversations" && (
        <div className="admin-split">
          <table className="admin-table">
            <thead>
              <tr><th>User</th><th>Title</th><th>Messages</th><th>Updated</th><th></th></tr>
            </thead>
            <tbody>
              {conversations.map((c) => (
                <tr key={c.id} className={c.id === traceConvId ? "selected" : ""}>
                  <td>{c.username}</td><td>{c.title}</td><td>{c.message_count}</td>
                  <td>{new Date(c.updated_at).toLocaleString()}</td>
                  <td><button className="btn btn-secondary" onClick={() => openTrace(c.id)}>View trace</button></td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="trace-viewer">
            <h3>Node execution trace</h3>
            {!trace && <p className="hint">Select a conversation to see which node fired for each prompt.</p>}
            {Object.entries(groupedTrace).map(([turnId, rows]) => (
              <div key={turnId} className="trace-turn-block">
                <div className="trace-turn-id">turn {turnId.slice(0, 8)}</div>
                <ol>
                  {rows.map((r) => (
                    <li key={r.id}>
                      <b>{r.node_name}</b>
                      <pre>{JSON.stringify(r.node_output, null, 2)}</pre>
                    </li>
                  ))}
                </ol>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
