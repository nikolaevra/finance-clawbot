"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  BookOpenText,
  Calendar,
  CheckCircle2,
  File,
  FileSpreadsheet,
  FileText,
  LibraryBig,
  Loader2,
  Trash2,
  Upload,
  Link2,
  ExternalLink,
  Cloud,
} from "lucide-react";
import { useMemories } from "@/lib/hooks/useMemories";
import type { UserDocument } from "@/types";
import {
  deleteDocument,
  fetchDocuments,
  uploadDocument,
  linkGoogleDriveDocument,
} from "@/lib/api";
import { formatFileSize } from "@/app/chat/documents/page";
import { groupMemoriesByDate } from "@/app/chat/memories/page";

const ACCEPTED_TYPES: Record<string, string> = {
  "application/pdf": "PDF",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
    "DOCX",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "XLSX",
  "application/msword": "DOC",
  "application/vnd.ms-excel": "XLS",
};

const ACCEPT_STRING = Object.keys(ACCEPTED_TYPES).join(",") + ",.pdf,.docx,.xlsx,.doc,.xls";

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

function DriveIcon() {
  return <Cloud size={18} className="text-sky-400/80" strokeWidth={1.5} />;
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

export default function ContextPage() {
  const router = useRouter();
  const { memories, loading: memoriesLoading } = useMemories();
  const [documents, setDocuments] = useState<UserDocument[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [driveInput, setDriveInput] = useState("");
  const [linkingDrive, setLinkingDrive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const memoryGroups = memories ? groupMemoriesByDate(memories.daily) : [];

  const loadDocuments = useCallback(async () => {
    try {
      setDocumentsError(null);
      const docs = await fetchDocuments();
      setDocuments(docs);
    } catch (err) {
      setDocumentsError(
        err instanceof Error ? err.message : "Failed to load documents"
      );
    } finally {
      setDocumentsLoading(false);
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
        // silent polling retry
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [documents]);

  const handleUpload = useCallback(
    async (files: FileList | File[]) => {
      const fileArray = Array.from(files);
      if (fileArray.length === 0) return;

      setUploading(true);
      setDocumentsError(null);
      let uploadedAny = false;

      for (const file of fileArray) {
        const ext = file.name.split(".").pop()?.toLowerCase();
        const validExts = ["pdf", "docx", "xlsx", "doc", "xls"];
        if (!validExts.includes(ext || "")) {
          setDocumentsError(
            `Unsupported file type: .${ext}. Accepted: PDF, DOCX, XLSX`
          );
          continue;
        }

        if (file.size > 20 * 1024 * 1024) {
          setDocumentsError(`File too large: ${file.name}. Maximum size is 20MB.`);
          continue;
        }

        try {
          await uploadDocument(file);
          uploadedAny = true;
        } catch (err) {
          setDocumentsError(
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

  const handleDelete = useCallback(async (id: string, filename: string) => {
    if (!confirm(`Delete "${filename}"? This cannot be undone.`)) return;
    try {
      await deleteDocument(id);
      setDocuments((prev) => prev.filter((d) => d.id !== id));
    } catch (err) {
      setDocumentsError(
        err instanceof Error ? err.message : "Failed to delete document"
      );
    }
  }, []);

  const handleLinkGoogleDrive = useCallback(async () => {
    if (!driveInput.trim()) {
      setDocumentsError("Paste a Google Drive file URL or file ID first.");
      return;
    }
    setLinkingDrive(true);
    setDocumentsError(null);
    try {
      await linkGoogleDriveDocument(driveInput);
      setDriveInput("");
      await loadDocuments();
    } catch (err) {
      setDocumentsError(
        err instanceof Error ? err.message : "Failed to link Google Drive file"
      );
    } finally {
      setLinkingDrive(false);
    }
  }, [driveInput, loadDocuments]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 px-6 py-5">
        <LibraryBig size={18} className="text-blue-400" strokeWidth={1.5} />
        <h1 className="text-lg font-semibold text-foreground/85 tracking-tight">Context</h1>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-2">
        <div className="mx-auto grid max-w-6xl grid-cols-1 gap-6 lg:grid-cols-2">
          <section className="rounded-2xl bg-foreground/[0.03] p-4 ring-1 ring-foreground/[0.08]">
            <div className="mb-4 flex items-center gap-2">
              <BookOpenText size={16} className="text-blue-400/80" strokeWidth={1.5} />
              <h2 className="text-sm font-semibold text-foreground/80">Memories</h2>
            </div>

            {memoriesLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 size={20} className="animate-spin text-foreground/20" />
              </div>
            ) : memories ? (
              <div className="space-y-6">
                {memories.long_term.exists && (
                  <button
                    onClick={() => router.push("/chat/memories/long-term")}
                    className="flex w-full items-center gap-3 rounded-2xl bg-foreground/[0.04] ring-1 ring-foreground/[0.06] px-4 py-3.5 text-left transition-all hover:bg-foreground/[0.07] hover:ring-foreground/[0.1]"
                  >
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-blue-400/10">
                      <BookOpenText size={16} className="text-blue-400" strokeWidth={1.5} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-foreground/75">MEMORY.md</p>
                      <p className="text-xs text-foreground/30">
                        Curated long-term facts and preferences
                      </p>
                    </div>
                  </button>
                )}

                {memoryGroups.map((group) => (
                  <div key={group.label}>
                    <h3 className="mb-2 text-[11px] font-medium uppercase tracking-wider text-foreground/25">
                      {group.label}
                    </h3>
                    <div className="space-y-1.5">
                      {group.items.map((mem) => (
                        <button
                          key={mem.date}
                          onClick={() => router.push(`/chat/memories/daily/${mem.date}`)}
                          className="flex w-full items-center gap-3 rounded-2xl bg-foreground/[0.04] ring-1 ring-foreground/[0.06] px-4 py-3.5 text-left transition-all hover:bg-foreground/[0.07] hover:ring-foreground/[0.1]"
                        >
                          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-foreground/[0.06]">
                            <Calendar size={16} className="text-foreground/40" strokeWidth={1.5} />
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-medium text-foreground/75">{mem.date}</p>
                            <p className="text-xs text-foreground/30">Daily log</p>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                ))}

                {memoryGroups.length === 0 && !memories.long_term.exists && (
                  <div className="py-8 text-center text-sm text-foreground/40">
                    No memories yet.
                  </div>
                )}
              </div>
            ) : null}
          </section>

          <section className="rounded-2xl bg-foreground/[0.03] p-4 ring-1 ring-foreground/[0.08]">
            <div className="mb-4 flex items-center gap-2">
              <FileText size={16} className="text-blue-400/80" strokeWidth={1.5} />
              <h2 className="text-sm font-semibold text-foreground/80">Documents</h2>
            </div>

            {documentsError && (
              <div className="mb-3 flex items-center gap-2 rounded-xl bg-red-400/[0.06] ring-1 ring-red-400/10 px-3 py-2">
                <AlertCircle size={14} className="shrink-0 text-red-400/70" strokeWidth={1.5} />
                <p className="text-xs text-red-400/80">{documentsError}</p>
              </div>
            )}

            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={(e) => {
                e.preventDefault();
                setDragOver(false);
              }}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                if (e.dataTransfer.files.length > 0) {
                  handleUpload(e.dataTransfer.files);
                }
              }}
              onClick={() => fileInputRef.current?.click()}
              className={`mb-4 flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-4 py-8 transition-all ${
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
                <Loader2 size={24} className="animate-spin text-blue-400" strokeWidth={1.5} />
              ) : (
                <>
                  <Upload size={18} className="mb-2 text-foreground/30" strokeWidth={1.5} />
                  <p className="text-xs font-medium text-foreground/50">
                    Click or drag files to upload
                  </p>
                </>
              )}
            </div>
            <div className="mb-4 space-y-2 rounded-2xl bg-foreground/[0.03] ring-1 ring-foreground/[0.08] p-3">
              <p className="text-xs font-medium text-foreground/45">
                Link from Google Drive
              </p>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={driveInput}
                  onChange={(e) => setDriveInput(e.target.value)}
                  placeholder="Paste Google Drive URL or file ID"
                  className="min-w-0 flex-1 rounded-xl bg-foreground/[0.03] px-3 py-2 text-sm text-foreground/80 ring-1 ring-foreground/[0.08] outline-none placeholder:text-foreground/30 focus:ring-blue-400/40"
                />
                <button
                  onClick={handleLinkGoogleDrive}
                  disabled={linkingDrive}
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-xl bg-blue-500/15 px-3 py-2 text-xs font-medium text-blue-300 ring-1 ring-blue-400/20 hover:bg-blue-500/20 disabled:opacity-50"
                >
                  {linkingDrive ? (
                    <Loader2 size={12} className="animate-spin" strokeWidth={1.5} />
                  ) : (
                    <Link2 size={12} strokeWidth={1.5} />
                  )}
                  Link
                </button>
              </div>
            </div>

            {documentsLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 size={20} className="animate-spin text-foreground/20" />
              </div>
            ) : documents.length > 0 ? (
              <div className="space-y-1.5">
                {documents.map((doc) => (
                  <div
                    key={doc.id}
                    className="flex items-center gap-3 rounded-2xl bg-foreground/[0.04] ring-1 ring-foreground/[0.06] px-4 py-3.5"
                  >
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-foreground/[0.06]">
                      {doc.source === "google_drive" ? (
                        <DriveIcon />
                      ) : (
                        <FileIcon fileType={doc.file_type} />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-foreground/75">
                        {doc.filename}
                      </p>
                      <div className="flex items-center gap-2 text-xs text-foreground/30">
                        <span>{fileTypeLabel(doc.file_type)}</span>
                        <span className="text-foreground/10">/</span>
                        <span>{formatFileSize(doc.file_size)}</span>
                      </div>
                    </div>
                    <StatusBadge status={doc.status} />
                    {doc.source === "google_drive" && doc.source_web_url && (
                      <button
                        onClick={() => window.open(doc.source_web_url || "", "_blank", "noopener,noreferrer")}
                        className="shrink-0 rounded-lg p-2 text-foreground/30 hover:text-sky-300 hover:bg-sky-400/10"
                        title="Open in Google Drive"
                      >
                        <ExternalLink size={14} strokeWidth={1.5} />
                      </button>
                    )}
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
            ) : (
              <div className="py-8 text-center text-sm text-foreground/40">
                No documents uploaded yet.
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
