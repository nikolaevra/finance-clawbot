"use client";

import { usePathname } from "next/navigation";
import NavBar from "@/components/NavBar";
import ActivityProvider from "@/components/ActivityProvider";
import { useActivityInternal } from "@/components/ActivityProvider";
import ActivityPanel, {
  ActivityToggleButton,
} from "@/components/ActivityPanel";
import ConversationProvider from "@/components/ConversationProvider";
import ChatSidebar, {
  ChatSidebarToggle,
  MobileChatSidebar,
  MobileChatSidebarToggle,
} from "@/components/ChatSidebar";
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable";

const NON_CHAT_PREFIXES = [
  "/chat/memories",
  "/chat/documents",
  "/chat/skills",
  "/chat/inbox",
  "/chat/integrations",
];

function isChatRoute(pathname: string) {
  return !NON_CHAT_PREFIXES.some((p) => pathname.startsWith(p));
}

function AppShellInner({ children }: { children: React.ReactNode }) {
  const { panelRef, isPanelOpen, onPanelResize } = useActivityInternal();
  const pathname = usePathname();
  const showChatSidebar = pathname !== "/" && isChatRoute(pathname);

  return (
    <div className="flex h-screen bg-background">
      <NavBar />
      {showChatSidebar && <ChatSidebar />}
      {showChatSidebar && <MobileChatSidebar />}
      {showChatSidebar && <MobileChatSidebarToggle />}
      <ResizablePanelGroup orientation="horizontal" className="flex-1">
        <ResizablePanel defaultSize="100%" minSize="50%">
          <main className="flex h-full flex-col overflow-hidden pb-16 md:pb-0">
            {showChatSidebar && <ChatSidebarToggle />}
            {children}
          </main>
        </ResizablePanel>

        <ResizableHandle
          withHandle={isPanelOpen}
          className={
            isPanelOpen ? "opacity-30 hover:opacity-60 transition-opacity" : "w-0 opacity-0"
          }
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

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <ConversationProvider>
      <ActivityProvider>
        <AppShellInner>{children}</AppShellInner>
      </ActivityProvider>
    </ConversationProvider>
  );
}
