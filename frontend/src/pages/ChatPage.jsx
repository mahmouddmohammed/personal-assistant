import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChatAPI } from "../api/client";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/Sidebar";
import InterruptPrompt from "../components/InterruptPrompt";
import TracePanel from "../components/TracePanel";

export default function ChatPage() {
  const { username, isAdmin, logout } = useAuth();
  const navigate = useNavigate();

  const [conversations, setConversations] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]); // {role, content, trace?}
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const bottomRef = useRef(null);

  const refreshConversations = async () => {
    const { data } = await ChatAPI.listConversations();
    setConversations(data);
  };

  useEffect(() => {
    refreshConversations();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pending]);

  const loadConversation = async (id) => {
    setActiveId(id);
    setPending(null);
    setError("");
    const { data } = await ChatAPI.getConversation(id);
    setMessages(data.messages.map((m) => ({ role: m.role, content: m.content })));
  };

  const startNewChat = () => {
    setActiveId(null);
    setMessages([]);
    setPending(null);
    setError("");
  };

  const applyResponse = (data) => {
    setActiveId(data.conversation_id);
    if (data.final_response) {
      setMessages((m) => [...m, { role: "assistant", content: data.final_response, trace: data.trace }]);
      setPending(null);
    } else if (data.pending_interrupt) {
      setPending(data.pending_interrupt);
    }
    refreshConversations();
  };

  const send = async () => {
    if (!input.trim() || busy) return;
    const text = input;
    setInput("");
    setError("");
    setMessages((m) => [...m, { role: "user", content: text }]);
    setBusy(true);
    try {
      const { data } = await ChatAPI.send(text, activeId);
      applyResponse(data);
    } catch (err) {
      // BUGFIX: previously any failed request (network error, expired
      // session, 500, etc.) left the optimistically-added user bubble
      // sitting there forever with no assistant reply and no feedback —
      // busy just silently reset via `finally` with nothing telling the
      // user anything had gone wrong. Now we surface the error and give
      // the message back so it isn't lost.
      setMessages((m) => m.slice(0, -1));
      setInput(text);
      setError(err?.response?.data?.detail || "Couldn't send that message. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  const resolveInterrupt = async (action, feedback) => {
    setBusy(true);
    setError("");
    try {
      const { data } = await ChatAPI.resume(activeId, action, feedback);
      applyResponse(data);
    } catch (err) {
      setError(err?.response?.data?.detail || "Couldn't submit that response. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="app-shell">
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={loadConversation}
        onNew={startNewChat}
        username={username}
        isAdmin={isAdmin}
        onLogout={() => { logout(); navigate("/login"); }}
        onGoAdmin={() => navigate("/admin")}
      />
      <main className="chat-main">
        <div className="chat-scroll">
          {messages.length === 0 && (
            <div className="empty-state">
              Ask me to classify an email, draft one, book a flight, extract meetings/invoices from
              text, summarize something, answer a question from memory, or find arXiv papers.
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`msg-row ${m.role}`}>
              <div className={`msg-bubble ${m.role}`}>{m.content}</div>
              {m.role === "assistant" && <TracePanel trace={m.trace} />}
            </div>
          ))}
          {pending && <InterruptPrompt pending={pending} onResolve={resolveInterrupt} busy={busy} />}
          <div ref={bottomRef} />
        </div>
        {error && <div className="error-banner chat-error-banner">{error}</div>}
        <div className="chat-input-bar">
          <input
            value={input}
            disabled={busy || !!pending}
            placeholder={pending ? "Resolve the pending action above first…" : "Type a message…"}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
          />
          <button className="btn btn-primary" disabled={busy || !!pending} onClick={send}>Send</button>
        </div>
      </main>
    </div>
  );
}
