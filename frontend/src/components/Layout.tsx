import { Outlet, useLocation } from 'react-router-dom';
import { useEffect } from 'react';
import Sidebar from './Sidebar';
import { useAppStore } from '../stores/appStore';

export default function Layout() {
  const location = useLocation();
  const { setSidebarCollapsed } = useAppStore();
  const isChat = location.pathname === '/chat' || location.pathname === '/';

  // Auto-collapse sidebar on Chat route
  useEffect(() => {
    if (isChat) {
      setSidebarCollapsed(true);
    }
  }, [isChat, setSidebarCollapsed]);

  return (
    <div className="flex min-h-screen bg-gray-50">
      <Sidebar />
      <main className={`flex-1 overflow-auto min-w-0 ${isChat ? '' : 'p-4 md:p-8'}`}>
        <Outlet />
      </main>
    </div>
  );
}
