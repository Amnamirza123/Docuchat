import { useState, useRef } from "react";
import { apiPost, apiPatch, apiDelete, apiUpload } from "../lib/api";

export default function Sidebar({
  sessions,
  activeSessionId,
  documents,
  onSelectSession,
  onNewChat,
  onSessionsChange,
  onDocumentsChange,
  onLogout,
}) {
  const [renamingId, setRenamingId] = useState(null);
  const [renameValue, setRenameValue] = useState("");
  const [uploadingFiles, setUploadingFiles] = useState({}); // { [filename]: status }
  const fileInputRef = useRef(null);

  async function handleRenameSubmit(sessionId) {
    if (renameValue.trim()) {
      await apiPatch(`/sessions/${sessionId}`, { title: renameValue.trim() });
      onSessionsChange();
    }
    setRenamingId(null);
  }

  async function handleDeleteSession(sessionId, e) {
    e.stopPropagation();
    if (!confirm("Delete this chat and all its documents?")) return;
    await apiDelete(`/sessions/${sessionId}`);
    onSessionsChange();
    if (sessionId === activeSessionId) {
      onNewChat();
    }
  }

  async function handleFileSelect(e) {
    const files = Array.from(e.target.files || []);
    e.target.value = ""; // allow re-selecting the same file later

    for (const file of files) {
      setUploadingFiles((prev) => ({ ...prev, [file.name]: "processing docs" }));

      try {
        const result = await apiUpload(`/sessions/${activeSessionId}/documents`, file);
        const status = result.document.status;

        setUploadingFiles((prev) => ({
          ...prev,
          [file.name]: status === "duplicate" ? "duplicate doc" : "successful",
        }));

        onDocumentsChange();

        // Clear the status badge after a few seconds
        setTimeout(() => {
          setUploadingFiles((prev) => {
            const next = { ...prev };
            delete next[file.name];
            return next;
          });
        }, 3000);
      } catch (err) {
        setUploadingFiles((prev) => ({ ...prev, [file.name]: "failed" }));
      }
    }
  }

  async function handleDeleteDocument(documentId) {
    await apiDelete(`/sessions/${activeSessionId}/documents/${documentId}`);
    onDocumentsChange();
  }

  return (
    <aside className="sidebar sidebar-left">
      <button className="new-chat-btn" onClick={onNewChat}>
        + New Chat
      </button>

      <div className="sidebar-section">
        <h3>Chats</h3>
        <ul className="session-list">
          {sessions.map((session) => (
            <li
              key={session.id}
              className={session.id === activeSessionId ? "active" : ""}
              onClick={() => onSelectSession(session.id)}
            >
              {renamingId === session.id ? (
                <input
                  autoFocus
                  value={renameValue}
                  onChange={(e) => setRenameValue(e.target.value)}
                  onBlur={() => handleRenameSubmit(session.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleRenameSubmit(session.id);
                    if (e.key === "Escape") setRenamingId(null);
                  }}
                  onClick={(e) => e.stopPropagation()}
                />
              ) : (
                <>
                  <span className="session-title">{session.title}</span>
                  <div className="session-actions">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setRenamingId(session.id);
                        setRenameValue(session.title);
                      }}
                      title="Rename"
                    >
                      ✎
                    </button>
                    <button
                      onClick={(e) => handleDeleteSession(session.id, e)}
                      title="Delete"
                    >
                      🗑
                    </button>
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>
      </div>

      <div className="sidebar-section">
        <h3>Documents</h3>
        <button
          className="upload-btn"
          onClick={() => fileInputRef.current?.click()}
          disabled={!activeSessionId}
        >
          + Add document
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx"
          multiple
          hidden
          onChange={handleFileSelect}
        />

        <ul className="document-list">
          {Object.entries(uploadingFiles).map(([filename, status]) => (
            <li key={filename} className={`doc-status doc-status-${status.replace(/\s/g, "-")}`}>
              <span className="doc-name">{filename}</span>
              <span className="doc-badge">{status}</span>
            </li>
          ))}

          {documents
            .filter((doc) => !uploadingFiles[doc.filename])
            .map((doc) => (
              <li key={doc.id} className="document-item">
                <span className="doc-name">{doc.filename}</span>
                <button onClick={() => handleDeleteDocument(doc.id)} title="Delete document">
                  ✕
                </button>
              </li>
            ))}
        </ul>
      </div>

      <button className="logout-btn" onClick={onLogout}>
        Log out
      </button>
    </aside>
  );
}