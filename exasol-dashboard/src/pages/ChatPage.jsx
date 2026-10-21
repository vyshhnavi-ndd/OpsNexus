
import React from "react";
import { MessageSquare, Send, LoaderCircle } from "lucide-react";
import Card from "../components/Card";
import SectionTitle from "../components/SectionTitle";

export default function ChatPage({
  messages,
  chatText,
  setChatText,
  sendChat,
  busy
}) {
  return (
    <div className="chat-layout">
      <Card className="chat-card">
        <div className="chat-header">
          <div className="chat-avatar">
            <MessageSquare size={19} />
          </div>

          <div>
            <strong>OpsNexus Data Assistant</strong>
            <small>Local Llama 3 · grounded in OPS_INTEL findings</small>
          </div>
        </div>

        <div className="chat-messages">
          {messages.map((m, i) => (
            <div key={i} className={`bubble ${m.role}`}>
              {m.text}
            </div>
          ))}

          {busy && (
            <div className="bubble assistant">
              <LoaderCircle
                size={15}
                className="thinking-icon"
              />
              Thinking…
            </div>
          )}
        </div>

        <form className="chat-form" onSubmit={sendChat}>
          <input
            value={chatText}
            onChange={(e) => setChatText(e.target.value)}
            placeholder="Ask about current findings and their evidence…"
            disabled={busy}
          />

          <button
            type="submit"
            className="btn btn-primary"
            disabled={busy || !chatText.trim()}
            aria-label="Send message"
          >
            {busy ? (
              <LoaderCircle size={14} className="thinking-icon" />
            ) : (
              <Send size={14} />
            )}
          </button>
        </form>
      </Card>

      <Card>
        <SectionTitle
          title="Try asking"
          subtitle="Example prompts"
        />

        <div className="suggestions">
          {[
            "Summarize the current findings.",
            "Which findings have the strongest evidence?",
            "What evidence is missing from the findings?"
          ].map((q) => (
            <button
              key={q}
              type="button"
              className="suggestion"
              disabled={busy}
              onClick={() => setChatText(q)}
            >
              {q}
            </button>
          ))}
        </div>
      </Card>
    </div>
  );
}
