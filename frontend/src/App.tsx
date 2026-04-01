import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Layout from './components/Layout';
import AuthGuard from './components/AuthGuard';
import Login from './pages/Login';
import Chat from './pages/Chat';
import { Toaster } from 'sonner';
import { useAuthStore } from './stores/authStore';

// Lazy-loaded pages — code-split into separate chunks
const Network = lazy(() => import('./pages/Network'));
const Coverage = lazy(() => import('./pages/operator/Coverage'));
const Workbench = lazy(() => import('./pages/operator/Workbench'));
const AgentChat = lazy(() => import('./pages/operator/AgentChat'));
const Review = lazy(() => import('./pages/operator/Review'));
const QueryDebugger = lazy(() => import('./pages/diagnostics/QueryDebugger'));
const DatabaseExplorer = lazy(() => import('./pages/diagnostics/DatabaseExplorer'));
const Publishers = lazy(() => import('./pages/admin/Publishers'));
const Health = lazy(() => import('./pages/admin/Health'));
const Enrichment = lazy(() => import('./pages/admin/Enrichment'));
const Users = lazy(() => import('./pages/admin/Users'));

function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center h-full">
      <div className="animate-spin h-8 w-8 border-2 border-blue-500 border-t-transparent rounded-full" />
    </div>
  );
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

/**
 * Root redirect: guests go to /network, authenticated users go to /chat.
 */
function RootRedirect() {
  const user = useAuthStore((s) => s.user);
  if (user?.role === 'guest') {
    return <Navigate to="/network" replace />;
  }
  return <Chat />;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Toaster position="top-right" richColors />
      <BrowserRouter>
        <Routes>
          {/* Login page — outside Layout (no sidebar) */}
          <Route path="/login" element={<Login />} />

          {/* All other routes — protected by AuthGuard */}
          <Route
            element={
              <AuthGuard>
                <Layout />
              </AuthGuard>
            }
          >
            {/* Primary: / redirects based on role */}
            <Route path="/" element={<RootRedirect />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/network" element={<Suspense fallback={<LoadingSpinner />}><Network /></Suspense>} />
            <Route path="/operator/coverage" element={<Suspense fallback={<LoadingSpinner />}><Coverage /></Suspense>} />
            <Route path="/operator/workbench" element={<Suspense fallback={<LoadingSpinner />}><Workbench /></Suspense>} />
            <Route path="/operator/agent" element={<Suspense fallback={<LoadingSpinner />}><AgentChat /></Suspense>} />
            <Route path="/operator/review" element={<Suspense fallback={<LoadingSpinner />}><Review /></Suspense>} />
            <Route path="/diagnostics/query" element={<Suspense fallback={<LoadingSpinner />}><QueryDebugger /></Suspense>} />
            <Route path="/diagnostics/db" element={<Suspense fallback={<LoadingSpinner />}><DatabaseExplorer /></Suspense>} />
            <Route path="/admin/publishers" element={<Suspense fallback={<LoadingSpinner />}><Publishers /></Suspense>} />
            <Route path="/admin/enrichment" element={<Suspense fallback={<LoadingSpinner />}><Enrichment /></Suspense>} />
            <Route path="/admin/users" element={<Suspense fallback={<LoadingSpinner />}><Users /></Suspense>} />
            <Route path="/admin/health" element={<Suspense fallback={<LoadingSpinner />}><Health /></Suspense>} />
            {/* Legacy redirects */}
            <Route
              path="/workbench"
              element={<Navigate to="/operator/workbench" replace />}
            />
            <Route
              path="/agent"
              element={<Navigate to="/operator/agent" replace />}
            />
            <Route
              path="/review"
              element={<Navigate to="/operator/review" replace />}
            />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
