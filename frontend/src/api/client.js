import axios from "axios";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

export const api = axios.create({ baseURL: API_BASE_URL });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export const AuthAPI = {
  register: (data) => api.post("/auth/register", data),
  login: (data) => api.post("/auth/login", data),
};

export const ChatAPI = {
  send: (message, conversationId) =>
    api.post("/chat/messages", { message, conversation_id: conversationId }),
  resume: (conversationId, action, feedback) =>
    api.post("/chat/resume", { conversation_id: conversationId, action, feedback }),
  listConversations: () => api.get("/chat/conversations"),
  getConversation: (id) => api.get(`/chat/conversations/${id}`),
};

export const AdminAPI = {
  listUsers: () => api.get("/admin/users"),
  listConversations: () => api.get("/admin/conversations"),
  conversationTrace: (id) => api.get(`/admin/conversations/${id}/trace`),
  recentLogs: (limit = 300) => api.get(`/admin/logs/recent?limit=${limit}`),
};
