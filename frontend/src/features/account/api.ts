import { request } from "../../shared/api/client";

export function changeMyPassword(password: string, current_password: string) {
  return request<{ ok: boolean }>("/api/users/me/password", {
    method: "POST",
    body: JSON.stringify({ password, current_password }),
  });
}

