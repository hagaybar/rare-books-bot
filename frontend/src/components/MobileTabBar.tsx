import { NavLink, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { useAuthStore } from '../stores/authStore';
import { getRoleLevel } from './AuthGuard';

// ---------------------------------------------------------------------------
// Icons (Heroicons outline, 24x24 viewBox)
// ---------------------------------------------------------------------------

const TAB_ICONS = {
  chat: 'M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z',
  network: 'M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 013 12c0-1.605.42-3.113 1.157-4.418',
  coverage: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0h4',
  more: 'M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5',
  close: 'M6 18L18 6M6 6l12 12',
  back: 'M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18',
} as const;

function TabIcon({ d, className }: { d: string; className?: string }) {
  return (
    <svg
      className={className ?? 'w-6 h-6'}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      viewBox="0 0 24 24"
    >
      <path strokeLinecap="round" strokeLinejoin="round" d={d} />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// More menu nav structure (mirrors Sidebar sections)
// ---------------------------------------------------------------------------

interface MoreNavItem {
  to: string;
  label: string;
  icon: string;
  minRole: 'guest' | 'limited' | 'full' | 'admin';
}

interface MoreNavSection {
  title: string;
  items: MoreNavItem[];
}

const MORE_SECTIONS: MoreNavSection[] = [
  {
    title: 'Operator',
    items: [
      { to: '/operator/coverage', label: 'Coverage', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0h4', minRole: 'full' },
      { to: '/operator/workbench', label: 'Workbench', icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2', minRole: 'full' },
      { to: '/operator/agent', label: 'Agent Chat', icon: 'M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z', minRole: 'full' },
      { to: '/operator/review', label: 'Review', icon: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z', minRole: 'full' },
    ],
  },
  {
    title: 'Diagnostics',
    items: [
      { to: '/diagnostics/query', label: 'Query Debugger', icon: 'M12 12.75c1.148 0 2.278.08 3.383.237 1.037.146 1.866.966 1.866 2.013 0 3.728-2.35 6.75-5.25 6.75S6.75 18.728 6.75 15c0-1.046.83-1.867 1.866-2.013A24.204 24.204 0 0112 12.75zm0 0c2.883 0 5.647.508 8.207 1.44a23.91 23.91 0 01-1.152-6.135c-.117-1.94-1.176-3.555-2.555-3.555h-9c-1.379 0-2.438 1.616-2.555 3.555A23.91 23.91 0 016.793 14.19 24.232 24.232 0 0112 12.75z', minRole: 'full' },
      { to: '/diagnostics/db', label: 'DB Explorer', icon: 'M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 0v3.75m-16.5-3.75v3.75m16.5 0v3.75C20.25 16.153 16.556 18 12 18s-8.25-1.847-8.25-4.125v-3.75m16.5 0c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125', minRole: 'full' },
    ],
  },
  {
    title: 'Admin',
    items: [
      { to: '/admin/publishers', label: 'Publishers', icon: 'M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25', minRole: 'full' },
      { to: '/admin/enrichment', label: 'Enrichment', icon: 'M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z', minRole: 'guest' },
      { to: '/admin/users', label: 'Users', icon: 'M18 18.72a9.094 9.094 0 003.741-2.479 9.09 9.09 0 10-13.084.006A9.094 9.094 0 0012.75 21a9.094 9.094 0 005.25-2.28zM15.75 9.75a3 3 0 11-6 0 3 3 0 016 0z', minRole: 'admin' },
      { to: '/admin/health', label: 'Health', icon: 'M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 12 9 12s9-4.78 9-12z', minRole: 'full' },
    ],
  },
];

// ---------------------------------------------------------------------------
// More Menu (full-screen overlay)
// ---------------------------------------------------------------------------

function MoreMenu({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();
  const userLevel = getRoleLevel(user?.role ?? 'guest');

  const visibleSections = MORE_SECTIONS
    .map((section) => ({
      ...section,
      items: section.items.filter(
        (item) => userLevel >= getRoleLevel(item.minRole),
      ),
    }))
    .filter((section) => section.items.length > 0);

  return (
    <div className="fixed inset-0 z-50 bg-white flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
        <h2 className="text-lg font-semibold text-gray-900">Menu</h2>
        <button
          onClick={onClose}
          className="p-2 -mr-2 text-gray-500 hover:text-gray-700"
        >
          <TabIcon d={TAB_ICONS.close} className="w-6 h-6" />
        </button>
      </div>

      {/* Nav sections */}
      <nav className="flex-1 overflow-y-auto px-4 py-4 space-y-6">
        {visibleSections.map((section) => (
          <div key={section.title}>
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
              {section.title}
            </p>
            <div className="space-y-1">
              {section.items.map((item) => (
                <button
                  key={item.to}
                  onClick={() => {
                    navigate(item.to);
                    onClose();
                  }}
                  className="flex items-center gap-3 w-full px-3 py-3 rounded-lg text-left text-gray-700 hover:bg-gray-100 active:bg-gray-200 transition-colors"
                >
                  <TabIcon d={item.icon} className="w-5 h-5 text-gray-400" />
                  <span className="text-sm font-medium">{item.label}</span>
                </button>
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* User info footer */}
      {user && (
        <div className="px-4 py-4 border-t border-gray-200">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium text-gray-700">{user.username}</div>
              <div className="text-xs text-gray-400 capitalize">{user.role}</div>
            </div>
            <button
              onClick={() => {
                logout();
                onClose();
              }}
              className="text-sm text-red-500 hover:text-red-600 font-medium"
            >
              Logout
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Mobile Tab Bar
// ---------------------------------------------------------------------------

export default function MobileTabBar() {
  const [moreOpen, setMoreOpen] = useState(false);
  const { user } = useAuthStore();
  const userLevel = getRoleLevel(user?.role ?? 'guest');

  const tabs = [
    { to: '/chat', label: 'Chat', icon: TAB_ICONS.chat, minRole: 'limited' as const },
    { to: '/network', label: 'Network', icon: TAB_ICONS.network, minRole: 'guest' as const },
    { to: '/operator/coverage', label: 'Coverage', icon: TAB_ICONS.coverage, minRole: 'full' as const },
  ].filter((tab) => userLevel >= getRoleLevel(tab.minRole));

  return (
    <>
      {moreOpen && <MoreMenu onClose={() => setMoreOpen(false)} />}

      <nav className="fixed bottom-0 left-0 right-0 z-40 bg-white border-t border-gray-200 safe-area-bottom md:hidden">
        <div className="flex items-center justify-around h-14">
          {tabs.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              className={({ isActive }) =>
                `flex flex-col items-center justify-center flex-1 h-full gap-0.5 transition-colors ${
                  isActive
                    ? 'text-blue-600'
                    : 'text-gray-400 active:text-gray-600'
                }`
              }
            >
              <TabIcon d={tab.icon} className="w-6 h-6" />
              <span className="text-[10px] font-medium">{tab.label}</span>
            </NavLink>
          ))}

          {/* More tab */}
          <button
            onClick={() => setMoreOpen(true)}
            className={`flex flex-col items-center justify-center flex-1 h-full gap-0.5 transition-colors ${
              moreOpen ? 'text-blue-600' : 'text-gray-400 active:text-gray-600'
            }`}
          >
            <TabIcon d={TAB_ICONS.more} className="w-6 h-6" />
            <span className="text-[10px] font-medium">More</span>
          </button>
        </div>
      </nav>
    </>
  );
}
