import { apiFetch } from "./client";

export type AlertItem = {
  id: number;
  file_id: string;
  level: string;
  message: string;
  created_at: string;
};

export function listAlerts(): Promise<AlertItem[]> {
  return apiFetch<AlertItem[]>("/alerts");
}
