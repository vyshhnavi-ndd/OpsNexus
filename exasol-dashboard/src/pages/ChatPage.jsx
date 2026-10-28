
import React, { useEffect, useRef } from "react";
import {
  MessageSquare,
  Send,
  LoaderCircle,
  Bot,
  Sparkles,
  User,
  Database,
  RotateCcw,
} from "lucide-react";

import Card from "../components/Card";
import SectionTitle from "../components/SectionTitle";
const suggestions = [
  {
    title: "Pipeline failures",
    description: "Find failed pipeline runs",
    prompt: "Which pipelines failed recently, and why?",
    icon: "pipeline",
  },
  {
    title: "Data trust",
    description: "Investigate data quality",
    prompt: "Which datasets have low trust scores?",
    icon: "trust",
  },
  {
    title: "Cloud costs",
    description: "Understand platform usage",
    prompt: "Summarize platform cost and usage.",
    icon: "cost",
  },
  {
    title: "Data warehouse",
    description: "Explore schemas and tables",
    prompt: "Show me the available schemas and important tables.",
    icon: "database",
  },
];

export default function ChatPage({
  messages = [],
  chatText,
  setChatText,
  sendChat,
  busy,
}) {
  const messagesEndRef = useRef(null);
  const messagesContainerRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    const container = messagesContainerRef.current;

    if (container) {
      container.scrollTo({
        top: container.scrollHeight,
        behavior: "smooth",
      });
    }
  }, [messages, busy]);

  const handleSubmit = (event) => {
    event.preventDefault();

    if (busy || !chatText?.trim()) return;

    sendChat(event);
  };

  const choosePrompt = (prompt) => {
    setChatText(prompt);
    inputRef.current?.focus();
  };

  const hasMessages = messages.length > 0;

  return (
    <div className="ops-chat-page">
      <Card className="ops-chat-card">
        {/* Header */}
        <header className="ops-chat-header">
          <div className="ops-chat-brand">
            <div className="ops-chat-brand-icon">
              <Bot size={25} />
            </div>

            <div className="ops-chat-brand-text">
              <div className="ops-chat-title-row">
                <h2>OpsNexus AI</h2>
                <span className="ops-chat-version">ASSISTANT</span>
              </div>

              <p>
                <span className="ops-chat-online-dot" />
                Data intelligence powered by Ollama
              </p>
            </div>
          </div>

          <div className="ops-chat-header-right">
            <span className="ops-chat-connection">
              <Database size={14} />
              Exasol RAG
            </span>

            <button
              type="button"
              className="ops-chat-reset"
              title="Start a new conversation"
              aria-label="Clear chat input"
              onClick={() => {
                setChatText("");
                inputRef.current?.focus();
              }}
            >
              <RotateCcw size={16} />
            </button>
          </div>
        </header>

        {/* Conversation */}
        <div
          className={`ops-chat-conversation ${
            hasMessages ? "has-messages" : "is-empty"
          }`}
          ref={messagesContainerRef}
          aria-live="polite"
          aria-label="Chat conversation"
        >
          {!hasMessages && (
            <div className="ops-chat-welcome">
              <div className="ops-chat-welcome-icon">
                <Sparkles size={30} />
              </div>

              <h1>Your data, understood.</h1>

              <p>
                Ask questions about your pipelines, data quality, Exasol
                warehouse, and Azure costs. I'll help you investigate your
                platform data.
              </p>

              <div className="ops-chat-capabilities">
                <span>
                  <Database size={15} />
                  Exasol data
                </span>

                <span>
                  <Sparkles size={15} />
                  AI-powered answers
                </span>
              </div>
            </div>
          )}

          {hasMessages && (
            <div className="ops-chat-date-label">
              <span>CONVERSATION</span>
            </div>
          )}

          {messages.map((message, index) => {
            const isUser = message.role === "user";

            return (
              <div
                key={message.id || `${message.role}-${index}`}
                className={`ops-chat-message ${
                  isUser ? "user-message" : "assistant-message"
                }`}
              >
                <div className="ops-chat-message-avatar">
                  {isUser ? <User size={17} /> : <Bot size={19} />}
                </div>

                <div className="ops-chat-message-content">
                  <div className="ops-chat-message-author">
                    {isUser ? "You" : "OpsNexus AI"}
                  </div>

                  <div className="ops-chat-bubble">
                    {message.text}
                  </div>
                </div>
              </div>
            );
          })}

          {busy && (
            <div className="ops-chat-message assistant-message">
              <div className="ops-chat-message-avatar">
                <Bot size={19} />
              </div>

              <div className="ops-chat-message-content">
                <div className="ops-chat-message-author">
                  OpsNexus AI
                </div>

                <div className="ops-chat-bubble ops-chat-thinking">
                  <span>Analyzing your data</span>

                  <span className="ops-chat-thinking-dots">
                    <i />
                    <i />
                    <i />
                  </span>

                  <LoaderCircle
                    size={15}
                    className="ops-chat-spinner"
                  />
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Suggested questions */}
        {!hasMessages && (
          <div className="ops-chat-suggestions">
            <div className="ops-chat-suggestions-heading">
              <Sparkles size={15} />
              <span>TRY ASKING</span>
            </div>

            <div className="ops-chat-suggestions-grid">
              {suggestions.map((item) => (
                <button
                  key={item.title}
                  type="button"
                  className="ops-chat-suggestion"
                  disabled={busy}
                  onClick={() => choosePrompt(item.prompt)}
                >
                  <span className="ops-chat-suggestion-icon">
                    {item.icon === "database" ? (
                      <Database size={18} />
                    ) : item.icon === "trust" ? (
                      <Sparkles size={18} />
                    ) : item.icon === "pipeline" ? (
                      <RotateCcw size={18} />
                    ) : (
                      <MessageSquare size={18} />
                    )}
                  </span>

                  <span className="ops-chat-suggestion-text">
                    <strong>{item.title}</strong>
                    <small>{item.description}</small>
                  </span>

                  <span className="ops-chat-suggestion-arrow">↗</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Message composer */}
        <div className="ops-chat-composer-area">
          <form
            className="ops-chat-composer"
            onSubmit={handleSubmit}
          >
            <textarea
              ref={inputRef}
              value={chatText}
              onChange={(event) => setChatText(event.target.value)}
              placeholder="Ask anything about your data..."
              aria-label="Message OpsNexus AI"
              rows={1}
              disabled={busy}
              onKeyDown={(event) => {
                if (
                  event.key === "Enter" &&
                  !event.shiftKey &&
                  !event.nativeEvent.isComposing
                ) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
            />

            <button
              type="submit"
              className="ops-chat-send"
              disabled={busy || !chatText?.trim()}
              aria-label="Send message"
              title="Send message"
            >
              {busy ? (
                <LoaderCircle
                  size={19}
                  className="ops-chat-spinner"
                />
              ) : (
                <Send size={18} />
              )}
            </button>
          </form>

          <div className="ops-chat-composer-footer">
            <span>
              <Sparkles size={12} />
              Powered by local AI
            </span>

            <span>Enter to send · Shift + Enter for a new line</span>
          </div>
        </div>
      </Card>

      {/* Optional side information */}
      <aside className="ops-chat-sidebar">
        <Card>
          <SectionTitle
            title="Your AI workspace"
            subtitle="What you can investigate"
          />

          <div className="ops-chat-info-list">
            <div className="ops-chat-info-item">
              <div className="ops-chat-info-icon purple">
                <RotateCcw size={18} />
              </div>

              <div>
                <strong>Pipeline monitoring</strong>
                <p>Review execution history and failures.</p>
              </div>
            </div>

            <div className="ops-chat-info-item">
              <div className="ops-chat-info-icon green">
                <Sparkles size={18} />
              </div>

              <div>
                <strong>Data trust</strong>
                <p>Investigate quality checks and trust metrics.</p>
              </div>
            </div>

            <div className="ops-chat-info-item">
              <div className="ops-chat-info-icon blue">
                <Database size={18} />
              </div>

              <div>
                <strong>Warehouse insights</strong>
                <p>Ask questions about available Exasol data.</p>
              </div>
            </div>
          </div>

          <div className="ops-chat-privacy-note">
            <Database size={16} />
            <p>
              Responses depend on your configured local Ollama model,
              RAG retrieval, and connected data sources.
            </p>
          </div>
        </Card>
      </aside>
    </div>
  );
}
