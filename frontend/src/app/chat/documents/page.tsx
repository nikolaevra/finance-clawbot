"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  FileText,
  Upload,
  Trash2,
  Loader2,
  CheckCircle2,
  AlertCircle,
  File,
  FileSpreadsheet,
} from "lucide-react";
import type { UserDocument } from "@/types";
import { fetchDocuments, uploadDocument, deleteDocument } from "@/lib/api";

const ACCEPTED_TYPES: Record<string, string> = {
  "application/pdf": "PDF",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
    "DOCX",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "XLSX",
  "application/msword": "DOC",
  "application/vnd.ms-excel": "XLS",
};

const ACCEPT_STRING = Object.keys(ACCEPTED_TYPES).join(",") + ",.pdf,.docx,.xlsx,.doc,.xls";

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function fileTypeLabel(fileType: string): string {
  return fileType.toUpperCase();
}

function FileIcon({ fileType }: { fileType: string }) {
  switch (fileType) {
    case "pdf":
      return <File size={18} className="text-red-400/70" strokeWidth={1.5} />;
    case "xlsx":
    case "xls":
      return <FileSpreadsheet size={18} className="text-emerald-400/70" strokeWidth={1.5} />;
    case "docx":
    case "doc":
      return <FileText size={18} className="text-blue-400/70" strokeWidth={1.5} />;
    default:
      return <FileText size={18} className="text-foreground/30" strokeWidth={1.5} />;
  }
}

function StatusBadge({ status }: { status: string }) {
  switch (status) {
    case "processing":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-amber-400/10 px-2 py-0.5 text-[10px] font-medium text-amber-400/80">
          <Loader2 size={9} className="animate-spin" />
          Processing
        </span>
      );
    case "ready":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-400/10 px-2 py-0.5 text-[10px] font-medium text-emerald-400/80">
          <CheckCircle2 size={9} />
          Ready
        </span>
      );
    case "error":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-red-400/10 px-2 py-0.5 text-[10px] font-medium text-red-400/80">
          <AlertCircle size={9} />
          Error
        </span>
      );
    default:
      return null;
  }
}

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<UserDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadDocuments = useCallback(async () => {
    try {
      setError(null);
      const docs = await fetchDocuments();
      setDocuments(docs);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load documents"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  useEffect(() => {
    const hasProcessing = documents.some((d) => d.status === "processing");
    if (!hasProcessing) return;

    const interval = setInterval(async () => {
      try {
        const docs = await fetchDocuments();
        setDocuments(docs);
        if (!docs.some((d) => d.status === "processing")) {
          clearInterval(interval);
        }
      } catch {
        // silent
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [documents]);

  const handleUpload = useCallback(
    async (files: FileList | File[]) => {
      const fileArray = Array.from(files);
      if (fileArray.length === 0) return;

      setUploading(true);
      setError(null);
      let uploadedAny = false;

      for (const file of fileArray) {
        const ext = file.name.split(".").pop()?.toLowerCase();
        const validExts = ["pdf", "docx", "xlsx", "doc", "xls"];
        if (!validExts.includes(ext || "")) {
          setError(
            `Unsupported file type: .${ext}. Accepted: PDF, DOCX, XLSX`
          );
          continue;
        }

        if (file.size > 20 * 1024 * 1024) {
          setError(`File too large: ${file.name}. Maximum size is 20MB.`);
          continue;
        }

        try {
          await uploadDocument(file);
          uploadedAny = true;
        } catch (err) {
          setError(
            err instanceof Error ? err.message : `Failed to upload ${file.name}`
          );
        }
      }

      setUploading(false);
      if (uploadedAny) {
        await loadDocuments();
      }
    },
    [loadDocuments]
  );

  const handleDelete = useCallback(
    async (id: string, filename: string) => {
      if (!confirm(`Delete "${filename}"? This cannot be undone.`)) return;

      try {
        await deleteDocument(id);
        setDocuments((prev) => prev.filter((d) => d.id !== id));
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to delete document"
        );
      }
    },
    []
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragOver(false);
      if (e.dataTransfer.files.length > 0) {
        handleUpload(e.dataTransfer.files);
      }
    },
    [handleUpload]
  );

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 px-6 py-5">
        <FileText size={18} className="text-blue-400" strokeWidth={1.5} />
        <h1 className="text-lg font-semibold text-foreground/85 tracking-tight">Documents</h1>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-2">
        <div className="mx-auto max-w-2xl space-y-6">
          {error && (
            <div className="flex items-center gap-2 rounded-2xl bg-red-400/[0.06] ring-1 ring-red-400/10 px-4 py-3">
              <AlertCircle size={14} className="shrink-0 text-red-400/70" strokeWidth={1.5} />
              <p className="text-sm text-red-400/80">{error}</p>
              <button
                onClick={() => setError(null)}
                className="ml-auto text-xs text-red-400/40 hover:text-red-400/60"
              >
                Dismiss
              </button>
            </div>
          )}

          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-12 transition-all ${
              dragOver
                ? "border-blue-400/40 bg-blue-400/[0.04]"
                : "border-foreground/[0.08] bg-foreground/[0.02] hover:border-foreground/[0.15] hover:bg-foreground/[0.04]"
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPT_STRING}
              multiple
              className="hidden"
              onChange={(e) => {
                if (e.target.files) handleUpload(e.target.files);
                e.target.value = "";
              }}
            />
            {uploading ? (
              <>
                <Loader2
                  size={28}
                  className="mb-3 animate-spin text-blue-400"
                  strokeWidth={1.5}
                />
                <p className="text-sm font-medium text-foreground/50">
                  Uploading...
                </p>
              </>
            ) : (
              <>
                <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-foreground/[0.06]">
                  <Upload size={20} className="text-foreground/30" strokeWidth={1.5} />
                </div>
                <p className="text-sm font-medium text-foreground/50">
                  {dragOver ? "Drop files here" : "Click or drag files to upload"}
                </p>
                <p className="mt-1.5 text-xs text-foreground/20">
                  PDF, Word (.docx), or Excel (.xlsx) -- up to 20MB
                </p>
              </>
            )}
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 size={20} className="animate-spin text-foreground/20" />
            </div>
          ) : documents.length > 0 ? (
            <div>
              <h2 className="mb-3 text-[11px] font-medium uppercase tracking-wider text-foreground/25">
                Uploaded Documents ({documents.length})
              </h2>
              <div className="space-y-1.5">
                {documents.map((doc) => (
                  <div
                    key={doc.id}
                    className="flex items-center gap-3 rounded-2xl bg-foreground/[0.04] ring-1 ring-foreground/[0.06] px-4 py-3.5 transition-all hover:bg-foreground/[0.07]"
                  >
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-foreground/[0.06]">
                      <FileIcon fileType={doc.file_type} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-foreground/75">
                        {doc.filename}
                      </p>
                      <div className="flex items-center gap-2 text-xs text-foreground/30">
                        <span>{fileTypeLabel(doc.file_type)}</span>
                        <span className="text-foreground/10">/</span>
                        <span>{formatFileSize(doc.file_size)}</span>
                        <span className="text-foreground/10">/</span>
                        <span>
                          {new Date(doc.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    </div>
                    <StatusBadge status={doc.status} />
                    <button
                      onClick={() => handleDelete(doc.id, doc.filename)}
                      className="shrink-0 rounded-lg p-2 text-foreground/20 hover:text-red-400 hover:bg-red-400/10"
                      title="Delete document"
                    >
                      <Trash2 size={14} strokeWidth={1.5} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-foreground/[0.04]">
                <FileText size={24} className="text-foreground/15" strokeWidth={1.5} />
              </div>
              <p className="text-sm font-medium text-foreground/40">
                No documents uploaded yet
              </p>
              <p className="mt-1.5 max-w-xs text-xs text-foreground/20">
                Upload PDF, Word, or Excel files. The AI assistant will be able
                to read and reference them in conversations.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
