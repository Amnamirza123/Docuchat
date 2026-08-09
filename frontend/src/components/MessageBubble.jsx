import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function MessageBubble({ message, streaming = false, onClick }) {
  const isUser = message.role === "user";

  return (
    <div
      className={`message-bubble ${isUser ? "message-user" : "message-assistant"} ${
        streaming ? "message-streaming" : ""
      }`}
      onClick={onClick}
    >
      <div className="message-role">{isUser ? "You" : "DocuChat"}</div>

      <div className="message-content">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {message.content}
        </ReactMarkdown>
      </div>

      {!isUser && !streaming && message.is_grounded && (
        <div className="message-grounded-badge">
          ✓ Grounded in your documents
        </div>
      )}

      {streaming && <span className="typing-cursor">▍</span>}
    </div>
  );
}