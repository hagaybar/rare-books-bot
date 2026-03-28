import { useEffect } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';

// Role hierarchy for page access
const PAGE_ROLES: Record<string, string> = {
  '/chat': 'limited',
  '/network': 'guest',
  '/operator/coverage': 'full',
  '/operator/workbench': 'full',
  '/operator/agent': 'full',
  '/operator/review': 'full',
  '/diagnostics/query': 'full',
  '/diagnostics/db': 'full',
  '/admin/publishers': 'full',
  '/admin/enrichment': 'guest',
  '/admin/health': 'full',
  '/admin/users': 'admin',
};

const ROLE_LEVEL: Record<string, number> = {
  admin: 4,
  full: 3,
  limited: 2,
  guest: 1,
};

export function getRoleLevel(role: string): number {
  return ROLE_LEVEL[role] ?? 0;
}

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const { user, loading, initialize } = useAuthStore();
  const location = useLocation();

  useEffect(() => {
    initialize();
  }, [initialize]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-gray-400">Loading...</div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Check page-level access
  const path = location.pathname;
  const requiredRole = Object.entries(PAGE_ROLES).find(([prefix]) =>
    path.startsWith(prefix),
  );
  if (requiredRole) {
    const userLevel = ROLE_LEVEL[user.role] ?? 0;
    const requiredLevel = ROLE_LEVEL[requiredRole[1]] ?? 0;
    if (userLevel < requiredLevel) {
      // Redirect to the highest page they can access
      return <Navigate to={user.role === 'guest' ? '/network' : '/'} replace />;
    }
  }

  return <>{children}</>;
}
