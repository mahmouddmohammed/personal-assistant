import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ username: "", email: "", password: "", admin_code: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const update = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const payload = { ...form, admin_code: form.admin_code || undefined };
      await register(payload);
      navigate("/chat");
    } catch (err) {
      setError(err?.response?.data?.detail || "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <h1>Create account</h1>
        <p className="subtitle">Join the personal assistant</p>
        {error && <div className="error-banner">{error}</div>}
        <label>Username</label>
        <input value={form.username} onChange={update("username")} required minLength={3} />
        <label>Email</label>
        <input type="email" value={form.email} onChange={update("email")} required />
        <label>Password</label>
        <input type="password" value={form.password} onChange={update("password")} required minLength={6} />
        <label>Admin code (optional)</label>
        <input value={form.admin_code} onChange={update("admin_code")} placeholder="leave blank for a normal account" />
        <button type="submit" disabled={loading}>{loading ? "Creating..." : "Create account"}</button>
        <p className="hint">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </form>
    </div>
  );
}
