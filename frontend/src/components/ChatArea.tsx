"use client";

import { useState } from "react";
import type { Message, StreamingMessage, PendingToolApproval } from "@/types";
import MessageList from "./MessageList";
import MessageInput from "./MessageInput";
import { useSkills } from "@/lib/hooks/useSkills";

interface ChatAreaProps {
  messages: Message[];
  streamingMessage: StreamingMessage | null;
  onSend: (
    message: string,
    options?: { forcedSkill?: string }
  ) => void;
  isLoading: boolean;
  pendingApproval?: PendingToolApproval | null;
  onResolveApproval?: (approved: boolean) => void;
  conversationId?: string | null;
}

export default function ChatArea({
  messages, streamingMessage, onSend, isLoading, pendingApproval, onResolveApproval, conversationId,
}: ChatAreaProps) {
  const [input, setInput] = useState("");
  const [selectedSkillName, setSelectedSkillName] = useState<string | null>(null);
  const { skills, loading: skillsLoading } = useSkills();

  const enabledSkills = skills.filter((skill) => skill.enabled);

  const handlePasteMessageBody = (body: string) => {
    setInput((prev) => (prev ? `${prev}\n\n${body}` : body));
  };

  return (
    <div className="flex flex-1 flex-col min-h-0">
      <MessageList
        messages={messages}
        streamingMessage={streamingMessage}
        pendingApproval={pendingApproval}
        onResolveApproval={onResolveApproval}
        conversationId={conversationId}
        onPasteMessageBody={handlePasteMessageBody}
      />
      <MessageInput
        onSend={onSend}
        disabled={isLoading}
        value={input}
        onChange={setInput}
        skills={enabledSkills}
        skillsLoading={skillsLoading}
        selectedSkillName={selectedSkillName}
        onSelectSkill={setSelectedSkillName}
      />
    </div>
  );
}
