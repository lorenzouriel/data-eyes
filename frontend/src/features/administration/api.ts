import { request } from "../../shared/api/client";
import type { Role } from "../auth/types";
import type { AppUser } from "./types";

// --- User management (admin-only, except changeMyPassword) ---

export function getUsers() {
  return request<AppUser[]>("/api/users");
}

export function createUser(input: { username: string; password: string; role: Role }) {
  return request<AppUser>("/api/users", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function deleteUser(username: string) {
  return request<void>(`/api/users/${encodeURIComponent(username)}`, { method: "DELETE" });
}

