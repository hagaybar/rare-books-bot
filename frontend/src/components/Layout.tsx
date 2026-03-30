import { Outlet, useLocation } from 'react-router-dom';
import { useEffect } from 'react';
import Sidebar from './Sidebar';
import MobileTabBar from './MobileTabBar';
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
      {/* Desktop sidebar — hidden on mobile */}
      <div className="hidden md:block">
        <Sidebar />
      </div>

      {/* Main content — bottom padding on mobile for tab bar */}
      <main className={`flex-1 overflow-auto min-w-0 ${isChat ? '' : 'p-4 md:p-8'} pb-16 md:pb-0`}>
        <Outlet />
      </main>

      {/* Mobile bottom tab bar — hidden on desktop */}
      <MobileTabBar />
    </div>
  );
}
