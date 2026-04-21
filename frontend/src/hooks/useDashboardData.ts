import { useCallback, useEffect, useState } from "react";

import { AlertItem, listAlerts } from "../api/alerts";
import { FileItem, listFiles } from "../api/files";

type UseDashboardDataOptions = {
  onStart?: () => void;
  onError?: (message: string) => void;
};

type UseDashboardDataResult = {
  files: FileItem[];
  alerts: AlertItem[];
  isLoading: boolean;
  reload: () => Promise<void>;
};

export function useDashboardData(options: UseDashboardDataOptions = {}): UseDashboardDataResult {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const { onStart, onError } = options;

  const reload = useCallback(async () => {
    setIsLoading(true);
    onStart?.();

    try {
      const [filesData, alertsData] = await Promise.all([listFiles(), listAlerts()]);
      setFiles(filesData);
      setAlerts(alertsData);
    } catch {
      onError?.("Не удалось загрузить данные");
    } finally {
      setIsLoading(false);
    }
  }, [onStart, onError]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { files, alerts, isLoading, reload };
}
