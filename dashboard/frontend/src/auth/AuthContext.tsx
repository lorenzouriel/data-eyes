import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from "react";
import * as api from "../api";
import type { Role } from "../types";

interface AuthState {
  username: string | null;
  role: Role | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [username, setUsername] = useState<string | null>(null);
  const [role, setRole] = useState<Role | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .me()
      .then((res) => {
        setUsername(res.username);
        setRole(res.role);
      })
      .catch(() => {
        setUsername(null);
        setRole(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (u: string, p: string) => {
    const res = await api.login(u, p);
    setUsername(res.username);
    setRole(res.role);
  }, []);

  const logout = useCallback(async () => {
    await api.logout();
    setUsername(null);
    setRole(null);
  }, []);

  return <AuthContext.Provider value={{ username, role, loading, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
