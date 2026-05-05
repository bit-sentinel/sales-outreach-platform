import { Sidebar } from '@/components/layout/sidebar';
import { Header } from '@/components/layout/header';
import { ChatPanel } from '@/components/chat/chat-panel';

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col overflow-hidden lg:flex-row">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto px-4 pb-6 pt-4 sm:px-5 lg:px-7 lg:pb-8 lg:pt-5">
          <div className="mx-auto w-full max-w-[1480px]">{children}</div>
        </main>
      </div>
      <ChatPanel />
    </div>
  );
}
