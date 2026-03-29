import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Layout from './components/Layout';
import AuthGuard from './components/AuthGuard';
import Login from './pages/Login';
import Chat from './pages/Chat';
import Coverage from './pages/operator/Coverage';
import Workbench from './pages/operator/Workbench';
import AgentChat from './pages/operator/AgentChat';
import Review from './pages/operator/Review';
import QueryDebugger from './pages/diagnostics/QueryDebugger';
import DatabaseExplorer from './pages/diagnostics/DatabaseExplorer';
import Publishers from './pages/admin/Publishers';
import Health from './pages/admin/Health';
import Enrichment from './pages/admin/Enrichment';
import Users from './pages/admin/Users';
import Network from './pages/Network';
import { Toaster } from 'sonner';
import { useAuthStore } from './stores/authStore';

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
            <Route path="/network" element={<Network />} />
            <Route path="/operator/coverage" element={<Coverage />} />
            <Route path="/operator/workbench" element={<Workbench />} />
            <Route path="/operator/agent" element={<AgentChat />} />
            <Route path="/operator/review" element={<Review />} />
            <Route path="/diagnostics/query" element={<QueryDebugger />} />
            <Route path="/diagnostics/db" element={<DatabaseExplorer />} />
            <Route path="/admin/publishers" element={<Publishers />} />
            <Route path="/admin/enrichment" element={<Enrichment />} />
            <Route path="/admin/users" element={<Users />} />
            <Route path="/admin/health" element={<Health />} />
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
