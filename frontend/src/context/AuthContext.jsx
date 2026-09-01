import { createContext, useContext, useState, useCallback } from "react";
import { AuthAPI } from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(localStorage.getItem("token"));
  const [username, setUsername] = useState(localStorage.getItem("username"));
  const [isAdmin, setIsAdmin] = useState(localStorage.getItem("isAdmin") === "true");

  const persist = (data) => {
    localStorage.setItem("token", data.access_token);
    localStorage.setItem("username", data.username);
    localStorage.setItem("isAdmin", String(data.is_admin));
    setToken(data.access_token);
    setUsername(data.username);
    setIsAdmin(data.is_admin);
  };

  const login = useCallback(async (usernameInput, password) => {
    const { data } = await AuthAPI.login({ username: usernameInput, password });
    persist(data);
  }, []);

  const register = useCallback(async (payload) => {
    const { data } = await AuthAPI.register(payload);
    persist(data);
  }, []);

  const logout = useCallback(() => {
    localStorage.clear();
    setToken(null);
    setUsername(null);
    setIsAdmin(false);
  }, []);

  return (
    <AuthContext.Provider value={{ token, username, isAdmin, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
