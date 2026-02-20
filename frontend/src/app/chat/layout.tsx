"use client";

import NavBar from "@/components/NavBar";
import ActivityProvider from "@/components/ActivityProvider";
import { useActivityInternal } from "@/components/ActivityProvider";
import ActivityPanel, {
  ActivityToggleButton,
} from "@/components/ActivityPanel";
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable";

function ChatLayoutInner({ children }: { children: React.ReactNode }) {
  const { panelRef, isPanelOpen, onPanelResize } = useActivityInternal();

  return (
    <div className="flex h-screen bg-white dark:bg-zinc-950">
      <NavBar />
      <ResizablePanelGroup orientation="horizontal" className="flex-1">
        <ResizablePanel defaultSize="100%" minSize="50%">
          <main className="flex h-full flex-col overflow-hidden pb-16 md:pb-0">
            {children}
          </main>
        </ResizablePanel>

        <ResizableHandle
          withHandle={isPanelOpen}
          className={isPanelOpen ? "" : "w-0 opacity-0"}
        />

        <ResizablePanel
          panelRef={panelRef}
          defaultSize="0%"
          minSize="20%"
          maxSize="40%"
          collapsible
          collapsedSize="0%"
          onResize={onPanelResize}
        >
          <ActivityPanel />
        </ResizablePanel>
      </ResizablePanelGroup>

      <ActivityToggleButton />
    </div>
  );
}

export default function ChatLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ActivityProvider>
      <ChatLayoutInner>{children}</ChatLayoutInner>
    </ActivityProvider>
  );
}
