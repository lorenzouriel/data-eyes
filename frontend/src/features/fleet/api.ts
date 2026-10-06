import { request } from "../../shared/api/client";
import type { FleetHealth } from "./types";

export function getFleetHealth() {
  return request<FleetHealth>("/api/fleet");
}

