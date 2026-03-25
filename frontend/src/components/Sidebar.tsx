import { useState, useEffect, useCallback, useLayoutEffect } from 'react';
import { NavLink } from 'react-router-dom';
import { useAppStore } from '../stores/appStore';

// ---------------------------------------------------------------------------
// Icon paths (Heroicons outline style)
// ---------------------------------------------------------------------------

const ICONS = {
  chat: 'M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z',
  coverage: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0h4',
  workbench: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2',
  agent: 'M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z',
  review: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z',
  queryDebugger: 'M12 12.75c1.148 0 2.278.08 3.383.237 1.037.146 1.866.966 1.866 2.013 0 3.728-2.35 6.75-5.25 6.75S6.75 18.728 6.75 15c0-1.046.83-1.867 1.866-2.013A24.204 24.204 0 0112 12.75zm0 0c2.883 0 5.647.508 8.207 1.44a23.91 23.91 0 01-1.152-6.135c-.117-1.94-1.176-3.555-2.555-3.555h-9c-1.379 0-2.438 1.616-2.555 3.555A23.91 23.91 0 016.793 14.19 24.232 24.232 0 0112 12.75z',
  dbExplorer: 'M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 0v3.75m-16.5-3.75v3.75m16.5 0v3.75C20.25 16.153 16.556 18 12 18s-8.25-1.847-8.25-4.125v-3.75m16.5 0c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125',
  publishers: 'M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25',
  health: 'M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 12 9 12s9-4.78 9-12z',
  collapse: 'M11 19l-7-7 7-7m8 14l-7-7 7-7',
  expand: 'M13 5l7 7-7 7M5 5l7 7-7 7',
} as const;

// ---------------------------------------------------------------------------
// Navigation structure
// ---------------------------------------------------------------------------

interface NavItem {
  to: string;
  label: string;
  icon: string;
  healthDot?: boolean;
}

interface NavSection {
  title: string;
  items: NavItem[];
}

const NAV_SECTIONS: NavSection[] = [
  {
    title: 'Primary',
    items: [
      { to: '/chat', label: 'Chat', icon: ICONS.chat },
    ],
  },
  {
    title: 'Operator',
    items: [
      { to: '/operator/coverage', label: 'Coverage', icon: ICONS.coverage },
      { to: '/operator/workbench', label: 'Workbench', icon: ICONS.workbench },
      { to: '/operator/agent', label: 'Agent Chat', icon: ICONS.agent },
      { to: '/operator/review', label: 'Review', icon: ICONS.review },
    ],
  },
  {
    title: 'Diagnostics',
    items: [
      { to: '/diagnostics/query', label: 'Query Debugger', icon: ICONS.queryDebugger },
      { to: '/diagnostics/db', label: 'DB Explorer', icon: ICONS.dbExplorer },
    ],
  },
  {
    title: 'Admin',
    items: [
      { to: '/admin/publishers', label: 'Publishers', icon: ICONS.publishers },
      { to: '/admin/enrichment', label: 'Enrichment', icon: ICONS.agent },
      { to: '/admin/health', label: 'Health', icon: ICONS.health, healthDot: true },
    ],
  },
];

// ---------------------------------------------------------------------------
// Health status hook
// ---------------------------------------------------------------------------

function useHealthStatus() {
  const [healthy, setHealthy] = useState<boolean | null>(null);

  const check = useCallback(async () => {
    try {
      const res = await fetch('/health');
      if (!res.ok) { setHealthy(false); return; }
      const data = await res.json();
      setHealthy(data.status === 'healthy');
    } catch {
      setHealthy(false);
    }
  }, []);

  useEffect(() => {
    check();
    const interval = setInterval(check, 30_000);
    return () => clearInterval(interval);
  }, [check]);

  return healthy;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

function NavIcon({ d, className }: { d: string; className?: string }) {
  return (
    <svg
      className={className ?? 'w-5 h-5 shrink-0'}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      viewBox="0 0 24 24"
    >
      <path strokeLinecap="round" strokeLinejoin="round" d={d} />
    </svg>
  );
}

export default function Sidebar() {
  const { sidebarCollapsed, toggleSidebar, setSidebarCollapsed } = useAppStore();
  const healthy = useHealthStatus();

  // Auto-collapse on narrow viewports
  useLayoutEffect(() => {
    const mql = window.matchMedia('(max-width: 767px)');
    const handleChange = (e: MediaQueryListEvent | MediaQueryList) => {
      if (e.matches) {
        setSidebarCollapsed(true);
      }
    };
    handleChange(mql);
    mql.addEventListener('change', handleChange);
    return () => mql.removeEventListener('change', handleChange);
  }, [setSidebarCollapsed]);

  const dotColor =
    healthy === null
      ? 'bg-gray-500'
      : healthy
        ? 'bg-green-500'
        : 'bg-red-500';

  return (
    <aside
      className={`${
        sidebarCollapsed ? 'w-16 max-md:hidden' : 'w-64'
      } bg-gray-900 text-gray-300 flex flex-col min-h-screen transition-all duration-200 shrink-0`}
    >
      {/* Header */}
      <div className="px-4 py-5 border-b border-gray-800 flex items-center justify-between">
        {!sidebarCollapsed && (
          <div>
            <h1 className="text-lg font-semibold text-white tracking-tight">
              Rare Books
            </h1>
            <p className="text-xs text-gray-500 mt-0.5">Metadata Quality</p>
          </div>
        )}
        <button
          type="button"
          onClick={toggleSidebar}
          className="text-gray-400 hover:text-white p-1 rounded transition-colors"
          title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          <NavIcon
            d={sidebarCollapsed ? ICONS.expand : ICONS.collapse}
            className="w-4 h-4"
          />
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2 py-4 space-y-6 overflow-y-auto">
        {NAV_SECTIONS.map((section) => (
          <div key={section.title}>
            {!sidebarCollapsed && (
              <p className="px-3 mb-2 text-[10px] font-semibold text-gray-500 uppercase tracking-wider">
                {section.title}
              </p>
            )}
            {sidebarCollapsed && (
              <div className="mx-auto w-6 border-t border-gray-700 mb-2" />
            )}
            <div className="space-y-0.5">
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                      isActive
                        ? 'bg-gray-800 text-white'
                        : 'text-gray-400 hover:bg-gray-800/50 hover:text-gray-200'
                    } ${sidebarCollapsed ? 'justify-center' : ''}`
                  }
                  title={sidebarCollapsed ? item.label : undefined}
                >
                  <NavIcon d={item.icon} />
                  {!sidebarCollapsed && (
                    <span className="flex items-center gap-2">
                      {item.label}
                      {item.healthDot && (
                        <span
                          className={`inline-block w-2 h-2 rounded-full ${dotColor}`}
                          title={healthy === null ? 'Checking...' : healthy ? 'Healthy' : 'Unhealthy'}
                        />
                      )}
                    </span>
                  )}
                  {sidebarCollapsed && item.healthDot && (
                    <span
                      className={`absolute ml-6 mt-[-12px] inline-block w-1.5 h-1.5 rounded-full ${dotColor}`}
                    />
                  )}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className={`px-4 py-4 border-t border-gray-800 text-xs text-gray-600 ${sidebarCollapsed ? 'text-center' : ''}`}>
        {sidebarCollapsed ? 'v0.2' : 'v0.2.0'}
      </div>
    </aside>
  );
}
