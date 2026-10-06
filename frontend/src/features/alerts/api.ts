import { request } from "../../shared/api/client";
import type { AlertCatalog, AlertEvent, AlertSetting, AlertState, DigestSetting } from "./types";

export const getAlertCatalog = () => request<AlertCatalog>("/api/alerts/catalog");

export const getAlertStates = () => request<AlertState[]>("/api/alerts/state");

export const getAlertEvents = (limit = 50) => request<AlertEvent[]>(`/api/alerts/events?limit=${limit}`);

export const saveAlertSetting = (setting: AlertSetting) =>
  request<AlertSetting>("/api/alerts/settings", { method: "PUT", body: JSON.stringify(setting) });

export const resetAlertSetting = (alertKey: string, instanceName: string) =>
  request<void>(`/api/alerts/settings?alert_key=${encodeURIComponent(alertKey)}&instance_name=${encodeURIComponent(instanceName)}`, {
    method: "DELETE",
  });

export const getDigestSetting = () => request<DigestSetting>("/api/alerts/digest");

export const saveDigestSetting = (setting: DigestSetting) =>
  request<DigestSetting>("/api/alerts/digest", { method: "PUT", body: JSON.stringify(setting) });
