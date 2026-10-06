import type { Role } from "../auth/types";

export interface AppUser {
  username: string;
  role: Role;
  created_at: string;
}

