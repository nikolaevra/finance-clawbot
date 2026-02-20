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

function formatFileSize(bytes: number): string {
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
      return <File size={20} className="text-red-400" />;
    case "xlsx":
    case "xls":
      return <FileSpreadsheet size={20} className="text-green-400" />;
    case "docx":
    case "doc":
      return <FileText size={20} className="text-blue-400" />;
    default:
      return <FileText size={20} className="text-zinc-400" />;
  }
}

function StatusBadge({ status }: { status: string }) {
  switch (status) {
    case "processing":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-yellow-500/10 px-2 py-0.5 text-[11px] font-medium text-yellow-600 dark:text-yellow-400">
          <Loader2 size={10} className="animate-spin" />
          Processing
        </span>
      );
    case "ready":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
          <CheckCircle2 size={10} />
          Ready
        </span>
      );
    case "error":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-red-500/10 px-2 py-0.5 text-[11px] font-medium text-red-600 dark:text-red-400">
          <AlertCircle size={10} />
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

  // Poll for processing documents
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

      for (const file of fileArray) {
        // Validate type
        const ext = file.name.split(".").pop()?.toLowerCase();
        const validExts = ["pdf", "docx", "xlsx", "doc", "xls"];
        if (!validExts.includes(ext || "")) {
          setError(
            `Unsupported file type: .${ext}. Accepted: PDF, DOCX, XLSX`
          );
          continue;
        }

        // Validate size (20MB)
        if (file.size > 20 * 1024 * 1024) {
          setError(`File too large: ${file.name}. Maximum size is 20MB.`);
          continue;
        }

        try {
          await uploadDocument(file);
        } catch (err) {
          setError(
            err instanceof Error ? err.message : `Failed to upload ${file.name}`
          );
        }
      }

      setUploading(false);
      await loadDocuments();
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
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-zinc-200 dark:border-zinc-800 px-6 py-4">
        <FileText size={20} className="text-emerald-400" />
        <h1 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">Documents</h1>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        <div className="mx-auto max-w-2xl space-y-6">
          {/* Error banner */}
          {error && (
            <div className="flex items-center gap-2 rounded-xl border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-900/10 px-4 py-3">
              <AlertCircle size={16} className="shrink-0 text-red-500 dark:text-red-400" />
              <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
              <button
                onClick={() => setError(null)}
                className="ml-auto text-xs text-red-400/70 hover:text-red-500 dark:hover:text-red-400"
              >
                Dismiss
              </button>
            </div>
          )}

          {/* Upload zone */}
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-10 transition-colors ${
              dragOver
                ? "border-emerald-400 bg-emerald-400/5"
                : "border-zinc-300 dark:border-zinc-700 bg-zinc-50/50 dark:bg-zinc-900/30 hover:border-zinc-400 dark:hover:border-zinc-600 hover:bg-zinc-100/50 dark:hover:bg-zinc-900/50"
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
                  size={32}
                  className="mb-3 animate-spin text-emerald-400"
                />
                <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                  Uploading...
                </p>
              </>
            ) : (
              <>
                <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-500/10">
                  <Upload size={24} className="text-emerald-400" />
                </div>
                <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                  {dragOver ? "Drop files here" : "Click or drag files to upload"}
                </p>
                <p className="mt-1 text-xs text-zinc-500">
                  PDF, Word (.docx), or Excel (.xlsx) -- up to 20MB
                </p>
              </>
            )}
          </div>

          {/* Document list */}
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="flex items-center gap-2 text-zinc-500">
                <Loader2 size={20} className="animate-spin" />
                <span className="text-sm">Loading documents...</span>
              </div>
            </div>
          ) : documents.length > 0 ? (
            <div>
              <h2 className="mb-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
                Uploaded Documents ({documents.length})
              </h2>
              <div className="space-y-2">
                {documents.map((doc) => (
                  <div
                    key={doc.id}
                    className="flex items-center gap-3 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/50 px-4 py-3 transition-colors hover:bg-zinc-100/50 dark:hover:bg-zinc-800/50"
                  >
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-zinc-200 dark:bg-zinc-800">
                      <FileIcon fileType={doc.file_type} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-zinc-800 dark:text-zinc-200">
                        {doc.filename}
                      </p>
                      <div className="flex items-center gap-2 text-xs text-zinc-500">
                        <span>{fileTypeLabel(doc.file_type)}</span>
                        <span>&middot;</span>
                        <span>{formatFileSize(doc.file_size)}</span>
                        <span>&middot;</span>
                        <span>
                          {new Date(doc.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    </div>
                    <StatusBadge status={doc.status} />
                    <button
                      onClick={() => handleDelete(doc.id, doc.filename)}
                      className="shrink-0 rounded-lg p-2 text-zinc-500 transition-colors hover:bg-zinc-200 dark:hover:bg-zinc-800 hover:text-red-500 dark:hover:text-red-400"
                      title="Delete document"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-zinc-200/50 dark:bg-zinc-800/50">
                <FileText size={28} className="text-zinc-400 dark:text-zinc-600" />
              </div>
              <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
                No documents uploaded yet
              </p>
              <p className="mt-1 max-w-xs text-xs text-zinc-500">
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
