import { useCallback, useState } from "react";

import { uploadFile } from "../api/files";

type UseFileUploadOptions = {
  onStart?: () => void;
  onError?: (message: string) => void;
  onSuccess?: () => void | Promise<void>;
};

type UseFileUploadResult = {
  title: string;
  setTitle: (value: string) => void;
  selectedFile: File | null;
  setSelectedFile: (file: File | null) => void;
  isSubmitting: boolean;
  submit: () => Promise<void>;
};

export function useFileUpload(options: UseFileUploadOptions = {}): UseFileUploadResult {
  const [title, setTitle] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { onStart, onError, onSuccess } = options;

  const submit = useCallback(async () => {
    if (!title.trim() || !selectedFile) {
      onError?.("Укажите название и выберите файл");
      return;
    }

    setIsSubmitting(true);
    onStart?.();

    try {
      await uploadFile({ title: title.trim(), file: selectedFile });
      setTitle("");
      setSelectedFile(null);
      await onSuccess?.();
    } catch {
      onError?.("Не удалось загрузить файл");
    } finally {
      setIsSubmitting(false);
    }
  }, [title, selectedFile, onStart, onError, onSuccess]);

  return {
    title,
    setTitle,
    selectedFile,
    setSelectedFile,
    isSubmitting,
    submit,
  };
}
