import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

class EventSourceStub {
  url: string;
  onopen: ((event?: Event) => void) | null = null;
  onerror: ((event?: Event) => void) | null = null;
  readyState = 0;
  private listeners = new Map<string, Set<(event: MessageEvent) => void>>();

  constructor(url: string) {
    this.url = url;
  }

  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set());
    }
    this.listeners.get(type)?.add(listener);
  }

  removeEventListener(type: string, listener: (event: MessageEvent) => void) {
    this.listeners.get(type)?.delete(listener);
  }

  emit(type: string, data: unknown) {
    const event = { data: JSON.stringify(data) } as MessageEvent;
    this.listeners.get(type)?.forEach((listener) => listener(event));
  }

  open() {
    this.readyState = 1;
    this.onopen?.(new Event("open"));
  }

  fail() {
    this.readyState = 2;
    this.onerror?.(new Event("error"));
  }

  close() {
    this.readyState = 2;
  }
}

Object.defineProperty(globalThis, "EventSource", {
  configurable: true,
  writable: true,
  value: EventSourceStub,
});

Object.defineProperty(window.HTMLElement.prototype, "scrollIntoView", {
  configurable: true,
  value: vi.fn(),
});

Object.defineProperty(navigator, "clipboard", {
  configurable: true,
  value: {
    writeText: vi.fn(),
  },
});

Object.defineProperty(window, "matchMedia", {
  configurable: true,
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

Object.defineProperty(window, "requestAnimationFrame", {
  configurable: true,
  writable: true,
  value: (callback: FrameRequestCallback) => window.setTimeout(() => callback(0), 0),
});

Object.defineProperty(window, "cancelAnimationFrame", {
  configurable: true,
  writable: true,
  value: (id: number) => window.clearTimeout(id),
});

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

Object.defineProperty(globalThis, "ResizeObserver", {
  configurable: true,
  writable: true,
  value: ResizeObserverStub,
});

beforeEach(() => {
  vi.useRealTimers();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
});

export { EventSourceStub };
