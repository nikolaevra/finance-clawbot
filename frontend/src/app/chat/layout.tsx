import AppShell from "@/components/AppShell";

export default function ChatLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <AppShell>{children}</AppShell>;
}
