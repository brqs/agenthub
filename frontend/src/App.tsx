import { Routes, Route, Navigate } from 'react-router-dom';
import { LoginPage } from './pages/LoginPage';
import { ChatPage } from './pages/ChatPage';
import { AgentsPage } from './pages/AgentsPage';
import { ArchivePage } from './pages/ArchivePage';
import { MarkdownTestPage } from './pages/MarkdownTestPage';
import { AppLayout } from './components/layout/AppLayout';
import { AuthGuard } from './components/layout/AuthGuard';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <AuthGuard>
            <AppLayout />
          </AuthGuard>
        }
      >
        <Route path="/" element={<Navigate to="/chat" replace />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/chat/:conversationId" element={<ChatPage />} />
        <Route path="/agents" element={<AgentsPage />} />
        <Route path="/archive" element={<ArchivePage />} />
        <Route path="/markdown-test" element={<MarkdownTestPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
