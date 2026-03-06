type LogLevel = "debug" | "info" | "warn" | "error";

const DEBUG_ENABLED = process.env.NODE_ENV !== "production";

function write(level: LogLevel, message: string, meta?: Record<string, unknown>) {
  if (level === "debug" && !DEBUG_ENABLED) return;
  const payload = meta ? { ...meta } : undefined;
  if (level === "error") {
    console.error(`[app:${level}] ${message}`, payload ?? "");
  } else if (level === "warn") {
    console.warn(`[app:${level}] ${message}`, payload ?? "");
  } else if (level === "info") {
    console.info(`[app:${level}] ${message}`, payload ?? "");
  } else {
    console.debug(`[app:${level}] ${message}`, payload ?? "");
  }
}

export const logger = {
  debug: (message: string, meta?: Record<string, unknown>) =>
    write("debug", message, meta),
  info: (message: string, meta?: Record<string, unknown>) =>
    write("info", message, meta),
  warn: (message: string, meta?: Record<string, unknown>) =>
    write("warn", message, meta),
  error: (message: string, meta?: Record<string, unknown>) =>
    write("error", message, meta),
};
