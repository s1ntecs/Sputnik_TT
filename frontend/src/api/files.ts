import { API_BASE_URL, apiFetch } from "./client";

export type FileItem = {
  id: string;
  title: string;
  original_name: string;
  mime_type: string;
  size: number;
  processing_status: string;
  scan_status: string | null;
  scan_details: string | null;
  metadata_json: Record<string, unknown> | null;
  requires_attention: boolean;
  created_at: string;
  updated_at: string;
};

export function listFiles(): Promise<FileItem[]> {
  return apiFetch<FileItem[]>("/files");
}

export async function uploadFile(params: { title: string; file: File }): Promise<FileItem> {
  const formData = new FormData();
  formData.append("title", params.title);
  formData.append("file", params.file);

  const response = await fetch(`${API_BASE_URL}/files`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error("upload_failed");
  }

  return (await response.json()) as FileItem;
}

export function getDownloadUrl(fileId: string): string {
  return `${API_BASE_URL}/files/${fileId}/download`;
}
