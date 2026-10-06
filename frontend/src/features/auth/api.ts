import { request } from "../../shared/api/client";
import type { Role } from "./types";

export function login(username: string, password: string) {
  return request<{ username: string; role: Role }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function logout() {
  return request<{ ok: boolean }>("/api/auth/logout", { method: "POST" });
}

export function me() {
  return request<{ username: string; role: Role }>("/api/auth/me");
}

