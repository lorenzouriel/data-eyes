import { request } from "../../shared/api/client";
import type { NotificationChannel, NotificationRule, NotificationLog } from "./types";

export const getNotificationChannels = () => request<NotificationChannel[]>("/api/notifications/channels");

export const saveNotificationChannel = (channel: Omit<NotificationChannel, "id">, id?: number) =>
  request<NotificationChannel>(`/api/notifications/channels${id ? `/${id}` : ""}`, { method: id ? "PUT" : "POST", body: JSON.stringify(channel) });

export const getNotificationRules = () => request<NotificationRule[]>("/api/notifications/rules");

export const saveNotificationRule = (rule: Omit<NotificationRule, "id">, id?: number) =>
  request<NotificationRule>(`/api/notifications/rules${id ? `/${id}` : ""}`, { method: id ? "PUT" : "POST", body: JSON.stringify(rule) });

export const getNotificationLogs = (offset = 0) => request<NotificationLog[]>(`/api/notifications/logs?limit=50&offset=${offset}`);

export const deleteNotification = (kind: "channels" | "rules" | "logs", id: number) =>
  request<void>(`/api/notifications/${kind}/${id}`, { method: "DELETE" });

export const testNotificationChannel = (id: number) =>
  request<{ ok: boolean; message: string }>(`/api/notifications/channels/${id}/test`, { method: "POST" });

