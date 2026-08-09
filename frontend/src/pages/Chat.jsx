import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { supabase } from "../lib/supabaseClient";
import { apiGet, apiPost } from "../lib/api";

import Sidebar from "../components/Sidebar";
import ChatWindow from "../components/ChatWindow";
import GroundednessPanel from "../components/GroundednessPanel";

export default function Chat() {
  const navigate = useNavigate();

  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [messages, setMessages] = useState([]);
  const [activeCitations, setActiveCitations] = useState(null); // null | { grounded, score, citations }
  const [loadingSessions, setLoadingSessions] = useState(true);

  const loadSessions = useCallback(async () => {
    const data = await apiGet("/sessions");
    setSessions(data);
    return data;
  }, []);

  const loadDocuments = useCallback(async (sessionId) => {
    if (!sessionId) return;
    const data = await apiGet(`/sessions/${sessionId}/documents`);
    setDocuments(data);
  }, []);

  const loadMessages = useCallback(async (sessionId) => {
    if (!sessionId) return;
    const data = await apiGet(`/sessions/${sessionId}/messages`);
    setMessages(data);

    // Populate the right panel with the latest assistant message, if any
    const lastAssistant = [...data].reverse().find((m) => m.role === "assistant");
    if (lastAssistant) {
      setActiveCitations({
        grounded: lastAssistant.is_grounded,
        score: lastAssistant.groundedness_score,
        citations: lastAssistant.citations || [],
      });
    } else {
      setActiveCitations(null);
    }
  }, []);

  // Initial load: fetch sessions, select the first one (or create one if none exist)
  useEffect(() => {
    (async () => {
      setLoadingSessions(true);
      const data = await loadSessions();
      if (data.length > 0) {
        setActiveSessionId(data[0].id);
      } else {
        const newSession = await apiPost("/sessions", {});
        setSessions([newSession]);
        setActiveSessionId(newSession.id);
      }
      setLoadingSessions(false);
    })();
  }, [loadSessions]);

  // When active session changes, load its documents + messages
  useEffect(() => {
    if (activeSessionId) {
      loadDocuments(activeSessionId);
      loadMessages(activeSessionId);
    }
  }, [activeSessionId, loadDocuments, loadMessages]);

  async function handleNewChat() {
    const newSession = await apiPost("/sessions", {});
    setSessions((prev) => [newSession, ...prev]);
    setActiveSessionId(newSession.id);
    setMessages([]);
    setDocuments([]);
    setActiveCitations(null);
  }

  async function handleSelectSession(sessionId) {
    setActiveSessionId(sessionId);
  }

  async function handleLogout() {
    await supabase.auth.signOut();
    navigate("/login");
  }

  if (loadingSessions) {
    return <div className="app-loading">Loading your chats...</div>;
  }

  return (
    <div className="chat-layout">
      <Sidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        documents={documents}
        onSelectSession={handleSelectSession}
        onNewChat={handleNewChat}
        onSessionsChange={loadSessions}
        onDocumentsChange={() => loadDocuments(activeSessionId)}
        onLogout={handleLogout}
      />

      <ChatWindow
        sessionId={activeSessionId}
        messages={messages}
        onMessagesChange={() => loadMessages(activeSessionId)}
        setActiveCitations={setActiveCitations}
      />

      <GroundednessPanel data={activeCitations} />
    </div>
  );
}