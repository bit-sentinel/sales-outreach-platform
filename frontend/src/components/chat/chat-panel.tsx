'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';
import { Send, Sparkles, RotateCcw, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/stores/chat-store';

// ── Types ─────────────────────────────────────────────────────────────────────

interface ToolActivity {
  name: string;
  status: 'running' | 'done';
  count: number;
}

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  streaming?: boolean;
  tools?: ToolActivity[];
}

const TOOL_LABELS: Record<string, string> = {
  docker_ps:     'Checking containers',
  docker_logs:   'Reading logs',
  db_query:      'Querying database',
  redis_info:    'Checking queues',
  system_health: 'Checking system health',
};

const FLAVOR_PHRASES = [
  'Thinking…',
  'Let me check…',
  'On it…',
  'Analyzing…',
  'One moment…',
  'Looking into that…',
];

const TOOL_FLAVOR: Record<string, string> = {
  docker_ps:     'Checking containers…',
  docker_logs:   'Pulling logs…',
  db_query:      'Querying the database…',
  redis_info:    'Checking queue depths…',
  system_health: 'Running health check…',
};

// ── Inline markdown renderer ──────────────────────────────────────────────────

function renderInline(text: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*\n]+\*\*|\*[^*\n]+\*|`[^`\n]+`)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**'))
      return <strong key={i} className="font-semibold text-white">{part.slice(2, -2)}</strong>;
    if (part.startsWith('*') && part.endsWith('*'))
      return <em key={i} className="italic">{part.slice(1, -1)}</em>;
    if (part.startsWith('`') && part.endsWith('`'))
      return (
        <code key={i} className="rounded bg-gray-900 px-1 py-0.5 font-mono text-[11px] text-violet-300">
          {part.slice(1, -1)}
        </code>
      );
    return part;
  });
}

function MarkdownContent({ text, streaming }: { text: string; streaming?: boolean }) {
  const lines = text.split('\n');
  const nodes: React.ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Fenced code block
    if (line.startsWith('```')) {
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith('```')) {
        codeLines.push(lines[i]);
        i++;
      }
      nodes.push(
        <pre key={`code-${i}`} className="my-2 overflow-x-auto rounded-lg bg-gray-900/80 p-3 text-[11px] leading-relaxed text-gray-200">
          <code>{codeLines.join('\n')}</code>
        </pre>,
      );
    }
    // Heading 3
    else if (line.startsWith('### ')) {
      nodes.push(
        <p key={i} className="mt-3 mb-1 font-semibold text-white text-[13px]">
          {renderInline(line.slice(4))}
        </p>,
      );
    }
    // Heading 2
    else if (line.startsWith('## ')) {
      nodes.push(
        <p key={i} className="mt-3 mb-1 font-semibold text-white text-[13px]">
          {renderInline(line.slice(3))}
        </p>,
      );
    }
    // Heading 1
    else if (line.startsWith('# ')) {
      nodes.push(
        <p key={i} className="mt-2 mb-1 font-bold text-white text-[13px]">
          {renderInline(line.slice(2))}
        </p>,
      );
    }
    // Unordered list
    else if (/^[-*•]\s/.test(line)) {
      nodes.push(
        <div key={i} className="my-0.5 flex gap-2 leading-relaxed">
          <span className="mt-[3px] shrink-0 text-gray-500">•</span>
          <span>{renderInline(line.slice(2))}</span>
        </div>,
      );
    }
    // Numbered list
    else if (/^\d+\.\s/.test(line)) {
      const m = line.match(/^(\d+)\.\s(.*)$/);
      if (m) {
        nodes.push(
          <div key={i} className="my-0.5 flex gap-2 leading-relaxed">
            <span className="mt-[3px] min-w-[1.25rem] shrink-0 text-gray-500 text-right">{m[1]}.</span>
            <span>{renderInline(m[2])}</span>
          </div>,
        );
      }
    }
    // Horizontal rule
    else if (/^---+$/.test(line.trim())) {
      nodes.push(<hr key={i} className="my-2 border-gray-700" />);
    }
    // Blank line → small spacer
    else if (line.trim() === '') {
      nodes.push(<div key={i} className="h-1.5" />);
    }
    // Normal text
    else {
      nodes.push(
        <p key={i} className="my-0.5 leading-relaxed">
          {renderInline(line)}
        </p>,
      );
    }

    i++;
  }

  return (
    <div className="text-[13px] text-gray-300">
      {nodes}
      {streaming && (
        <span className="ml-0.5 inline-block h-3.5 w-0.5 translate-y-0.5 animate-pulse rounded-sm bg-indigo-400" />
      )}
    </div>
  );
}

// ── Streaming fetch helper ────────────────────────────────────────────────────

async function streamChat(
  messages: { role: string; content: string }[],
  onChunk: (text: string) => void,
  onDone: () => void,
  onError: (msg: string) => void,
  onToolStart: (name: string) => void,
  onToolDone: (name: string) => void,
  signal: AbortSignal,
) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;

  let res: Response;
  try {
    res = await fetch('/api/v1/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ messages }),
      signal,
    });
  } catch (err: unknown) {
    if ((err as Error).name !== 'AbortError') onError('Network error — please try again.');
    return;
  }

  if (!res.ok) {
    onError(`Server error ${res.status}`);
    return;
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  // eslint-disable-next-line no-constant-condition
  while (true) {
    let done = false;
    let value: Uint8Array | undefined;
    try {
      ({ done, value } = await reader.read());
    } catch {
      break;
    }
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const data = line.slice(6).trim();
      if (data === '[DONE]') { onDone(); return; }
      try {
        const parsed = JSON.parse(data) as { text?: string; error?: string; type?: string; name?: string };
        if (parsed.error) { onError(parsed.error); return; }
        if (parsed.text) onChunk(parsed.text);
        if (parsed.type === 'tool_start' && parsed.name) onToolStart(parsed.name);
        if (parsed.type === 'tool_done' && parsed.name) onToolDone(parsed.name);
      } catch { /* partial chunk, keep buffering */ }
    }
  }

  onDone();
}

// ── Page context hints ────────────────────────────────────────────────────────

const PAGE_HINTS: Record<string, string> = {
  '/dashboard':  'You are viewing the Dashboard.',
  '/leads':      'You are viewing the Leads list.',
  '/campaigns':  'You are viewing Campaigns.',
  '/replies':    'You are viewing the Reply inbox.',
  '/analytics':  'You are viewing Analytics.',
  '/settings':   'You are viewing Settings.',
};

// ── Main component ────────────────────────────────────────────────────────────

export function ChatPanel() {
  const pathname = usePathname();
  const { open, setOpen, setHasMessages } = useChatStore();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [flavorIdx, setFlavorIdx] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Keep store in sync so header button can show unread dot
  useEffect(() => { setHasMessages(messages.length > 0); }, [messages.length, setHasMessages]);

  // Cycle flavor text every 2 s while loading
  useEffect(() => {
    if (!loading) { setFlavorIdx(0); return; }
    const id = setInterval(() => setFlavorIdx(i => (i + 1) % FLAVOR_PHRASES.length), 2000);
    return () => clearInterval(id);
  }, [loading]);

  const getFlavorText = (msg: Message) => {
    const running = msg.tools?.find(t => t.status === 'running');
    return running ? (TOOL_FLAVOR[running.name] ?? 'Working…') : FLAVOR_PHRASES[flavorIdx];
  };

  // Auto-scroll on new content
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Minimize on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 120)}px`;
    }
  }, [input]);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    // Build context prefix for first message
    const pageHint = PAGE_HINTS[pathname] ?? '';
    const content = messages.length === 0 && pageHint ? `[${pageHint}]\n\n${text}` : text;

    const userMsg: Message = { id: crypto.randomUUID(), role: 'user', content: text };
    const assistantMsg: Message = { id: crypto.randomUUID(), role: 'assistant', content: '', streaming: true };

    setMessages(prev => [...prev, userMsg, assistantMsg]);
    setInput('');
    setLoading(true);

    const history = [
      ...messages.map(m => ({ role: m.role, content: m.content })),
      { role: 'user' as const, content },
    ];

    abortRef.current = new AbortController();

    await streamChat(
      history,
      (chunk) => {
        setMessages(prev =>
          prev.map(m => m.id === assistantMsg.id ? { ...m, content: m.content + chunk } : m),
        );
      },
      () => {
        setMessages(prev =>
          prev.map(m => m.id === assistantMsg.id ? { ...m, streaming: false } : m),
        );
        setLoading(false);
      },
      (err) => {
        setMessages(prev =>
          prev.map(m =>
            m.id === assistantMsg.id
              ? { ...m, content: `Error: ${err}`, streaming: false }
              : m,
          ),
        );
        setLoading(false);
      },
      (toolName) => {
        setMessages(prev =>
          prev.map(m => {
            if (m.id !== assistantMsg.id) return m;
            const tools = m.tools ?? [];
            const idx = tools.findIndex(t => t.name === toolName);
            if (idx >= 0) {
              // Re-activate existing badge and increment its counter
              const updated = [...tools];
              updated[idx] = { ...updated[idx], status: 'running', count: updated[idx].count + 1 };
              return { ...m, tools: updated };
            }
            return { ...m, tools: [...tools, { name: toolName, status: 'running', count: 1 }] };
          }),
        );
      },
      (toolName) => {
        setMessages(prev =>
          prev.map(m =>
            m.id === assistantMsg.id
              ? { ...m, tools: (m.tools ?? []).map(t => t.name === toolName && t.status === 'running' ? { ...t, status: 'done' } : t) }
              : m,
          ),
        );
      },
      abortRef.current.signal,
    );
  }, [input, loading, messages, pathname]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const clearChat = () => {
    abortRef.current?.abort();
    setMessages([]);
    setLoading(false);
  };

  return (
    <>
      {/* Chat panel — drops down from the header (top-right) */}
      <div
        className={cn(
          'fixed right-4 top-[60px] z-50 flex w-[420px] flex-col overflow-hidden rounded-2xl border border-gray-700/60 bg-gray-900 shadow-2xl transition-all duration-300',
          open ? 'translate-y-0 opacity-100' : 'pointer-events-none -translate-y-2 opacity-0',
        )}
        style={{ height: 580, maxHeight: 'calc(100vh - 72px)' }}
      >
        {/* Header */}
        <div className="flex items-center gap-2.5 border-b border-gray-700/60 px-4 py-3">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-600/20">
            <Sparkles className="h-4 w-4 text-indigo-400" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[13px] font-semibold text-white">OutreachAI Assistant</p>
            <p className="text-[11px] text-gray-500">Powered by Claude</p>
          </div>
          {messages.length > 0 && (
            <button
              onClick={clearChat}
              className="rounded-md p-1.5 text-gray-500 transition-colors hover:bg-gray-800 hover:text-gray-300"
              title="Clear conversation"
            >
              <RotateCcw className="h-3.5 w-3.5" />
            </button>
          )}
          <button
            onClick={() => setOpen(false)}
            className="rounded-md p-1.5 text-gray-500 transition-colors hover:bg-gray-800 hover:text-gray-300"
            title="Minimise"
          >
            <ChevronDown className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-center px-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600/15">
                <Sparkles className="h-5 w-5 text-indigo-400" />
              </div>
              <p className="text-[13px] font-medium text-white">How can I help?</p>
              <p className="text-[12px] text-gray-500 leading-relaxed">
                Ask me to draft a reply, analyse a lead, review campaign performance, or debug any issue.
              </p>
              <div className="mt-1 flex flex-col gap-1.5 w-full">
                {[
                  'Draft a reply to an interested lead',
                  'Why is my campaign not sending?',
                  'How should I handle an objection?',
                ].map(hint => (
                  <button
                    key={hint}
                    onClick={() => { setInput(hint); textareaRef.current?.focus(); }}
                    className="rounded-lg border border-gray-700/60 bg-gray-800/50 px-3 py-2 text-left text-[12px] text-gray-400 transition-colors hover:border-gray-600 hover:text-gray-300"
                  >
                    {hint}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map(msg => (
            <div
              key={msg.id}
              className={cn('flex', msg.role === 'user' ? 'justify-end' : 'justify-start')}
            >
              {msg.role === 'assistant' && (
                <div className="mr-2 mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-600/20">
                  <Sparkles className="h-3.5 w-3.5 text-indigo-400" />
                </div>
              )}
              <div
                className={cn(
                  'max-w-[85%] rounded-2xl px-3.5 py-2.5',
                  msg.role === 'user'
                    ? 'rounded-tr-sm bg-indigo-600 text-[13px] text-white'
                    : 'rounded-tl-sm bg-gray-800/70',
                )}
              >
                {msg.role === 'user' ? (
                  <p className="text-[13px] leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                ) : (
                  <>
                    {msg.tools && msg.tools.length > 0 && (
                      <div className="mb-2 flex flex-wrap gap-1.5">
                        {msg.tools.map((t, i) => (
                          <span
                            key={i}
                            className={cn(
                              'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium',
                              t.status === 'running'
                                ? 'bg-indigo-500/20 text-indigo-300'
                                : 'bg-gray-700/60 text-gray-500',
                            )}
                          >
                            {t.status === 'running' && (
                              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-indigo-400" />
                            )}
                            {t.status === 'done' && (
                              <span className="h-1.5 w-1.5 rounded-full bg-gray-500" />
                            )}
                            {TOOL_LABELS[t.name] ?? t.name}{t.count > 1 ? ` ×${t.count}` : ''}
                          </span>
                        ))}
                      </div>
                    )}
                    <MarkdownContent
                      text={msg.content || (msg.streaming ? getFlavorText(msg) : '')}
                      streaming={msg.streaming && !msg.content}
                    />
                  </>
                )}
              </div>
            </div>
          ))}

          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="border-t border-gray-700/60 p-3">
          <div className="flex items-end gap-2 rounded-xl border border-gray-700 bg-gray-800/60 px-3 py-2 focus-within:border-indigo-500/50 transition-colors">
            <textarea
              ref={textareaRef}
              rows={1}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask anything… (Enter to send)"
              disabled={loading}
              className="max-h-[120px] min-h-[20px] flex-1 resize-none bg-transparent text-[13px] text-white placeholder-gray-500 outline-none disabled:opacity-50"
            />
            <button
              onClick={send}
              disabled={!input.trim() || loading}
              className="mb-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-indigo-600 text-white transition-colors hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Send className="h-3.5 w-3.5" />
            </button>
          </div>
          <p className="mt-1.5 text-center text-[10px] text-gray-600">
            Shift+Enter for newline · Esc to close
          </p>
        </div>
      </div>
    </>
  );
}
