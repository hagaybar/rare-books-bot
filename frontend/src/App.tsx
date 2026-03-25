import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Layout from './components/Layout';
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

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            {/* Primary: / and /chat both serve the Chat screen */}
            <Route path="/" element={<Chat />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/operator/coverage" element={<Coverage />} />
            <Route path="/operator/workbench" element={<Workbench />} />
            <Route path="/operator/agent" element={<AgentChat />} />
            <Route path="/operator/review" element={<Review />} />
            <Route path="/diagnostics/query" element={<QueryDebugger />} />
            <Route path="/diagnostics/db" element={<DatabaseExplorer />} />
            <Route path="/admin/publishers" element={<Publishers />} />
            <Route path="/admin/enrichment" element={<Enrichment />} />
            <Route path="/admin/health" element={<Health />} />
            {/* Legacy redirects */}
            <Route path="/workbench" element={<Navigate to="/operator/workbench" replace />} />
            <Route path="/agent" element={<Navigate to="/operator/agent" replace />} />
            <Route path="/review" element={<Navigate to="/operator/review" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
