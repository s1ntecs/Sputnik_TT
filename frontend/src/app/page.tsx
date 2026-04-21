"use client";

import { useCallback, useState } from "react";
import { Alert, Col, Container, Row } from "react-bootstrap";

import { AlertsTable } from "../components/AlertsTable";
import { FilesTable } from "../components/FilesTable";
import { PageHeader } from "../components/PageHeader";
import { UploadModal } from "../components/UploadModal";
import { useDashboardData } from "../hooks/useDashboardData";
import { useFileUpload } from "../hooks/useFileUpload";

export default function Page() {
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);

  const clearError = useCallback(() => setErrorMessage(null), []);
  const reportError = useCallback((message: string) => setErrorMessage(message), []);

  const data = useDashboardData({ onStart: clearError, onError: reportError });
  const upload = useFileUpload({
    onStart: clearError,
    onError: reportError,
    onSuccess: async () => {
      setShowModal(false);
      await data.reload();
    },
  });

  return (
    <Container fluid className="py-4 px-4 bg-light min-vh-100">
      <Row className="justify-content-center">
        <Col xxl={10} xl={11}>
          <PageHeader
            onReload={() => void data.reload()}
            onAddFile={() => setShowModal(true)}
          />

          {errorMessage ? (
            <Alert variant="danger" className="shadow-sm">
              {errorMessage}
            </Alert>
          ) : null}

          <FilesTable files={data.files} isLoading={data.isLoading} />
          <AlertsTable alerts={data.alerts} isLoading={data.isLoading} />
        </Col>
      </Row>

      <UploadModal
        show={showModal}
        title={upload.title}
        isSubmitting={upload.isSubmitting}
        onTitleChange={upload.setTitle}
        onFileChange={upload.setSelectedFile}
        onHide={() => setShowModal(false)}
        onSubmit={upload.submit}
      />
    </Container>
  );
}
