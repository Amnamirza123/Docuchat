import { useState, useRef, useEffect } from "react";
import { MessageCircleMore } from "lucide-react";
import { supabase } from "../lib/supabaseClient";
import { API_URL } from "../lib/api";
import MessageBubble from "./MessageBubble";

export default function ChatWindow({ sessionId, messages, onMessagesChange, setActiveCitations }) {
  const [input, setInput] = useState("");
  const [pendingUserMessage, setPendingUserMessage] = useState(null);
  const [streamingText, setStreamingText] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamError, setStreamError] = useState(null);
  const lastIndexRef = useRef(-1);
  const scrollRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText, pendingUserMessage]);

  async function handleSend(e) {
    e.preventDefault();
    const message = input.trim();
    if (!message || !sessionId || isStreaming) return;

    setInput("");
    setPendingUserMessage(message);
    setIsStreaming(true);
    setStreamingText("");
    setStreamError(null);
    lastIndexRef.current = -1;

    try {
      const { data: sessionData } = await supabase.auth.getSession();
      const token = sessionData?.session?.access_token;

      const response = await fetch(`${API_URL}/sessions/${sessionId}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ message }),
      });

      if (!response.ok) {
        throw new Error(`Server responded with ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let accumulated = "";
      let receivedDone = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop(); // keep any incomplete trailing line

        for (const line of lines) {
          if (!line.trim()) continue;
          const payload = JSON.parse(line);

          if (payload.done) {
            receivedDone = true;
            setIsStreaming(false);
            setStreamingText("");
            setPendingUserMessage(null);
            await onMessagesChange();
          } else if (payload.index > lastIndexRef.current) {
            lastIndexRef.current = payload.index;
            accumulated += payload.text;
            setStreamingText(accumulated);
          }
        }
      }

      // Stream ended without ever sending "done" — something broke server-side mid-response
      if (!receivedDone) {
        throw new Error(
          accumulated
            ? "Connection dropped mid-response."
            : "The model didn't respond — it may be rate-limited or unavailable right now."
        );
      }
    } catch (err) {
      setStreamError(err.message || "Something went wrong. Please try again.");
      setIsStreaming(false);
      setStreamingText("");
    }
  }

  const hasAnyMessages = messages.length > 0 || pendingUserMessage;

  return (
    <main className="chat-window">
      <div className="chat-messages">
        {!hasAnyMessages && (
          <div className="chat-empty-state">
            <MessageCircleMore size={40} strokeWidth={1.5} />
            <p>Ask me anything, or upload a document to get started.</p>
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            onClick={() =>
              msg.role === "assistant" &&
              setActiveCitations({
                grounded: msg.is_grounded,
                score: msg.groundedness_score,
                citations: msg.citations || [],
              })
            }
          />
        ))}

        {pendingUserMessage && (
          <MessageBubble message={{ role: "user", content: pendingUserMessage }} />
        )}

        {isStreaming && (
          <MessageBubble
            message={{ role: "assistant", content: streamingText || "…" }}
            streaming
          />
        )}

        {streamError && (
          <div className="stream-error">
            <span>{streamError}</span>
            <button onClick={() => setStreamError(null)}>Dismiss</button>
          </div>
        )}

        <div ref={scrollRef} />
      </div>

      <form className="chat-input-bar" onSubmit={handleSend}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about your documents, or just chat..."
          disabled={!sessionId || isStreaming}
        />
        <button type="submit" disabled={!sessionId || isStreaming || !input.trim()}>
          Send
        </button>
      </form>
    </main>
  );
}