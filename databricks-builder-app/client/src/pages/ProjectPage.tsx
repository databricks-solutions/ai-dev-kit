import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useUser } from '@/contexts/UserContext';
import {
  ArrowUp,
  Brain,
  Check,
  ChevronDown,
  ExternalLink,
  FileText,
  Image as ImageIcon,
  Loader2,
  Paperclip,
  Pencil,
  Send,
  Settings2,
  Sparkles,
  Square,
  Trash2,
  Wrench,
  X,
} from 'lucide-react';
import { toast } from 'sonner';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { PrismLight as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import sqlLang from 'react-syntax-highlighter/dist/esm/languages/prism/sql';
import pythonLang from 'react-syntax-highlighter/dist/esm/languages/prism/python';
import bashLang from 'react-syntax-highlighter/dist/esm/languages/prism/bash';
import jsonLang from 'react-syntax-highlighter/dist/esm/languages/prism/json';
import javascriptLang from 'react-syntax-highlighter/dist/esm/languages/prism/javascript';
import typescriptLang from 'react-syntax-highlighter/dist/esm/languages/prism/typescript';
import { MainLayout } from '@/components/layout/MainLayout';
import { Sidebar } from '@/components/layout/Sidebar';
import { SkillsExplorer } from '@/components/SkillsExplorer';
import { FunLoader } from '@/components/FunLoader';
import { Button } from '@/components/ui/Button';
import {
  createConversation,
  deleteConversation,
  fetchClusters,
  fetchConversation,
  fetchConversations,
  fetchExecutions,
  fetchProject,
  fetchUserSettings,
  fetchWarehouses,
  invokeAgent,
  reconnectToExecution,
  stopExecution,
  uploadProjectFile,
} from '@/lib/api';
import type { Cluster, Conversation, Execution, Message, Project, UserSettings, Warehouse, TodoItem } from '@/lib/types';
import type { ImageAttachment } from '@/lib/api';
import { cn } from '@/lib/utils';

// Local attachment types
interface AttachedImage {
  id: string;
  file: File;
  preview: string;    // ObjectURL for display
  data: string;       // base64 for API
  mediaType: 'image/jpeg' | 'image/png' | 'image/gif' | 'image/webp';
}

interface AttachedFile {
  id: string;
  file: File;
}

interface QueuedMessage {
  conversationId: string | null;
  userMessage: string;
  displayContent: string;
  imagesToSend: ImageAttachment[];
  queuedMessageId?: string;
}

interface InProgressConversationState {
  userMessage?: Message;
  streamingText: string;
  activityItems?: ActivityItem[];
  queuedMessages?: Message[];
}

const PENDING_CONVERSATION_KEY = '__pending__';

const SUPPORTED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
const MAX_IMAGE_SIZE = 20 * 1024 * 1024; // 20MB

SyntaxHighlighter.registerLanguage('sql', sqlLang);
SyntaxHighlighter.registerLanguage('python', pythonLang);
SyntaxHighlighter.registerLanguage('bash', bashLang);
SyntaxHighlighter.registerLanguage('shell', bashLang);
SyntaxHighlighter.registerLanguage('json', jsonLang);
SyntaxHighlighter.registerLanguage('javascript', javascriptLang);
SyntaxHighlighter.registerLanguage('typescript', typescriptLang);

async function readImageAsBase64(file: File): Promise<{ data: string; mediaType: AttachedImage['mediaType'] }> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const dataUrl = e.target?.result as string;
      const [prefix, data] = dataUrl.split(',');
      const mediaType = prefix.split(':')[1].split(';')[0] as AttachedImage['mediaType'];
      resolve({ data, mediaType });
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

// Combined activity item for display
interface ActivityItem {
  id: string;
  type: 'thinking' | 'tool_use' | 'tool_result' | 'keepalive';
  content: string;
  toolName?: string;
  toolInput?: Record<string, unknown>;
  isError?: boolean;
  timestamp: number;
}

function buildActivityItemsFromExecutionEvents(events: unknown[]): ActivityItem[] {
  const items: ActivityItem[] = [];
  for (const rawEvent of events) {
    if (!rawEvent || typeof rawEvent !== 'object') continue;
    const event = rawEvent as Record<string, unknown>;
    const type = String(event.type ?? '');
    if (!type) continue;

    if (type === 'thinking' || type === 'thinking_delta') {
      const thinking = String(event.thinking ?? '');
      if (!thinking) continue;
      const last = items[items.length - 1];
      if (last?.type === 'thinking') {
        last.content = type === 'thinking_delta' ? last.content + thinking : thinking;
      } else {
        items.push({
          id: `thinking-${items.length}`,
          type: 'thinking',
          content: thinking,
          timestamp: Date.now(),
        });
      }
      continue;
    }

    if (type === 'tool_use') {
      const toolUseItem: ActivityItem = {
        id: String(event.tool_id ?? `tool-${items.length}`),
        type: 'tool_use',
        content: '',
        toolName: String(event.tool_name ?? ''),
        toolInput: (event.tool_input as Record<string, unknown> | undefined) ?? {},
        timestamp: Date.now(),
      };
      const existingIdx = items.findIndex((item) => item.id === toolUseItem.id);
      if (existingIdx >= 0) items[existingIdx] = toolUseItem;
      else items.push(toolUseItem);
      continue;
    }

    if (type === 'tool_result') {
      const toolUseId = String(event.tool_use_id ?? '');
      const resultItem: ActivityItem = {
        id: `result-${toolUseId || items.length}`,
        type: 'tool_result',
        content: typeof event.content === 'string' ? event.content : JSON.stringify(event.content),
        isError: Boolean(event.is_error),
        timestamp: Date.now(),
      };
      const existingIdx = items.findIndex((item) => item.id === resultItem.id);
      if (existingIdx >= 0) items[existingIdx] = resultItem;
      else items.push(resultItem);
      continue;
    }
  }
  return items;
}

function buildTraceHistoryFromExecutions(executions: Execution[]): ActivityItem[][] {
  return [...executions]
    .reverse()
    .map((e) => buildActivityItemsFromExecutionEvents(e.events ?? []))
    .filter((items) => items.length > 0);
}

function tracesEqual(a: ActivityItem[], b: ActivityItem[]): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

function mergeTraceHistories(
  persisted: ActivityItem[][],
  cached: ActivityItem[][]
): ActivityItem[][] {
  if (persisted.length === 0) return cached;
  if (cached.length === 0) return persisted;

  const merged = [...persisted];
  for (const trace of cached) {
    if (!merged.some((existing) => tracesEqual(existing, trace))) {
      merged.push(trace);
    }
  }
  return merged;
}

function improveReadabilityForStreaming(text: string): string {
  if (!text) return text;
  // Some stream chunks arrive glued together (e.g. "done.Still ...").
  // Add paragraph breaks at likely sentence boundaries for better readability.
  return text.replace(/([.!?…])([A-Z])/g, '$1\n\n$2');
}

function applyThinkingEventToItems(
  items: ActivityItem[],
  eventType: 'thinking' | 'thinking_delta',
  thinking: string
): ActivityItem[] {
  if (!thinking) return items;
  const lastItem = items.length > 0 ? items[items.length - 1] : null;
  if (lastItem?.type === 'thinking') {
    const updated = [...items];
    updated[updated.length - 1] = {
      ...lastItem,
      content: eventType === 'thinking_delta' ? lastItem.content + thinking : thinking,
    };
    return updated;
  }
  return [
    ...items,
    {
      id: `thinking-${Date.now()}`,
      type: 'thinking',
      content: thinking,
      timestamp: Date.now(),
    },
  ];
}

function upsertActivityItem(items: ActivityItem[], nextItem: ActivityItem): ActivityItem[] {
  const idx = items.findIndex((item) => item.id === nextItem.id);
  return idx >= 0
    ? items.map((item, itemIdx) => (itemIdx === idx ? nextItem : item))
    : [...items, nextItem];
}

// Minimal activity indicator - shows only current tool being executed (non-verbose)
function ActivitySection({
  items,
  isStreaming,
}: {
  items: ActivityItem[];
  isStreaming: boolean;
}) {
  if (items.length === 0) return null;

  const currentTool = [...items].reverse().find((item) => item.type === 'tool_use');
  if (!currentTool) return null;

  return (
    <div className="mb-2 flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
      <Wrench className={cn('h-3 w-3 text-[var(--color-accent-primary)]', isStreaming && 'animate-pulse')} />
      <span className="truncate">
        Using {currentTool.toolName?.replace('mcp__databricks__', '')}...
      </span>
    </div>
  );
}

// Extract code and language from tool inputs for the 3 code-execution MCP tools.
function getCodeFromToolInput(
  toolName: string | undefined,
  toolInput: Record<string, unknown> | undefined,
): { code: string; language: string; params?: Record<string, unknown> } | null {
  if (!toolName || !toolInput) return null;
  const name = toolName.replace('mcp__databricks__', '');
  if (name === 'execute_sql') {
    const code = toolInput.sql_query as string;
    if (code) {
      const { sql_query, ...params } = toolInput;
      return { code, language: 'sql', params: Object.keys(params).length > 0 ? params : undefined };
    }
  } else if (name === 'execute_sql_multi') {
    const code = toolInput.sql_content as string;
    if (code) {
      const { sql_content, ...params } = toolInput;
      return { code, language: 'sql', params: Object.keys(params).length > 0 ? params : undefined };
    }
  } else if (name === 'execute_databricks_command') {
    const code = toolInput.code as string;
    if (code) {
      const { code: _code, language: lang, ...params } = toolInput;
      return { code, language: (lang as string) || 'python', params: Object.keys(params).length > 0 ? params : undefined };
    }
  }
  return null;
}

// Single item in the verbose trace
function VerboseItem({ item }: { item: ActivityItem }) {
  const [expanded, setExpanded] = useState(item.type === 'thinking');

  if (item.type === 'thinking') {
    const readableThinking = improveReadabilityForStreaming(item.content);
    return (
      <div className="border-b border-[var(--color-border)]/20 last:border-0">
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-[var(--color-bg-secondary)]/40 transition-colors"
        >
          <Brain className="h-3 w-3 flex-shrink-0 text-purple-400" />
          <span className="text-[11px] text-[var(--color-text-muted)] flex-1 truncate">
            {expanded
              ? `Thinking · ${readableThinking.length} chars`
              : readableThinking.slice(0, 220).replace(/\n/g, ' ')}
          </span>
          <ChevronDown className={cn('h-3 w-3 flex-shrink-0 text-[var(--color-text-muted)] transition-transform', expanded && 'rotate-180')} />
        </button>
        {expanded && (
          <div className="px-3 pb-2 ml-5 font-mono text-[10px] text-[var(--color-text-muted)] whitespace-pre-wrap leading-relaxed max-h-96 overflow-y-auto">
            {readableThinking}
          </div>
        )}
      </div>
    );
  }

  if (item.type === 'tool_use') {
    const toolName = item.toolName?.replace('mcp__databricks__', '') ?? '';
    const codeInfo = getCodeFromToolInput(item.toolName, item.toolInput);
    const inputStr = !codeInfo && item.toolInput ? JSON.stringify(item.toolInput, null, 2) : '';
    const hasExpandable = !!(codeInfo || inputStr);
    return (
      <div className="border-b border-[var(--color-border)]/20 last:border-0">
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-[var(--color-bg-secondary)]/40 transition-colors"
        >
          <Wrench className="h-3 w-3 flex-shrink-0 text-[var(--color-accent-primary)]" />
          <span className="font-mono text-[11px] text-[var(--color-text-primary)]">{toolName}</span>
          {codeInfo && (
            <span className="ml-1 px-1 py-0.5 rounded text-[9px] font-mono uppercase tracking-wide bg-[var(--color-accent-primary)]/10 text-[var(--color-accent-primary)]">
              {codeInfo.language}
            </span>
          )}
          {hasExpandable && (
            <ChevronDown className={cn('h-3 w-3 ml-auto flex-shrink-0 text-[var(--color-text-muted)] transition-transform', expanded && 'rotate-180')} />
          )}
        </button>
        {expanded && codeInfo?.params && (
          <div className="flex flex-wrap gap-1 mx-3 mb-1.5">
            {Object.entries(codeInfo.params).map(([key, val]) => (
              <span key={key} className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono bg-[var(--color-bg-secondary)]/60 text-[var(--color-text-muted)] border border-[var(--color-border)]/30">
                <span className="text-[var(--color-text-muted)]/70">{key}:</span>
                <span className="text-[var(--color-text-primary)]">{String(val)}</span>
              </span>
            ))}
          </div>
        )}
        {expanded && codeInfo && (
          <div className="mx-3 mb-2 max-h-64 overflow-y-auto rounded text-[10px]">
            <SyntaxHighlighter
              language={codeInfo.language}
              style={oneDark}
              customStyle={{ margin: 0, borderRadius: '0.25rem', fontSize: '10px', lineHeight: '1.5' }}
              wrapLongLines
            >
              {codeInfo.code}
            </SyntaxHighlighter>
          </div>
        )}
        {expanded && inputStr && (
          <div className="px-3 pb-2 ml-5 font-mono text-[10px] text-[var(--color-text-muted)] whitespace-pre-wrap leading-relaxed max-h-32 overflow-y-auto bg-[var(--color-bg-secondary)]/30 rounded mx-3 mb-1 p-1.5">
            {inputStr}
          </div>
        )}
      </div>
    );
  }

  if (item.type === 'tool_result') {
    const preview = item.content.slice(0, 120).replace(/\n/g, ' ');
    const hasMore = item.content.length > 120;
    const imagePaths = extractDatabricksImagePaths(item.content);
    return (
      <div className={cn('border-b border-[var(--color-border)]/20 last:border-0', item.isError && 'bg-[var(--color-error)]/5')}>
        <button
          onClick={() => (hasMore ? setExpanded(!expanded) : undefined)}
          className={cn(
            'w-full flex items-start gap-2 px-3 py-1.5 text-left transition-colors',
            hasMore && 'hover:bg-[var(--color-bg-secondary)]/40 cursor-pointer',
            !hasMore && 'cursor-default',
          )}
        >
          <span className={cn('text-[10px] flex-shrink-0 mt-0.5 font-mono', item.isError ? 'text-[var(--color-error)]' : 'text-[var(--color-success)]')}>
            {item.isError ? '✕' : '✓'}
          </span>
          <span className="font-mono text-[10px] text-[var(--color-text-muted)] flex-1 truncate">{preview}</span>
          {hasMore && (
            <ChevronDown className={cn('h-3 w-3 flex-shrink-0 text-[var(--color-text-muted)] transition-transform', expanded && 'rotate-180')} />
          )}
        </button>
        {expanded && (
          <div className="px-3 pb-2 ml-5 text-[10px] text-[var(--color-text-muted)] leading-relaxed max-h-48 overflow-y-auto bg-[var(--color-bg-secondary)]/30 rounded mx-3 mb-1 p-1.5">
            <div className="font-mono whitespace-pre-wrap">{item.content}</div>
            {imagePaths.length > 0 && (
              <div className="mt-2 space-y-2">
                {imagePaths.map((path) => (
                  <DatabricksImage key={path} path={path} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  if (item.type === 'keepalive') {
    return (
      <div className="border-b border-[var(--color-border)]/20 last:border-0">
        <div className="w-full flex items-center gap-2 px-3 py-1.5 text-left">
          <Loader2 className="h-3 w-3 flex-shrink-0 animate-spin text-[var(--color-accent-primary)]" />
          <span className="text-[10px] font-mono text-[var(--color-text-muted)]">{item.content}</span>
        </div>
      </div>
    );
  }

  return null;
}

// Full verbose trace panel (thinking + tool calls + results in order)
function VerboseActivityLog({
  items,
  isStreaming,
}: {
  items: ActivityItem[];
  isStreaming: boolean;
}) {
  const [collapsed, setCollapsed] = useState(false);

  if (items.length === 0) return null;

  const currentTool = isStreaming ? [...items].reverse().find((i) => i.type === 'tool_use') : null;

  return (
    <div className="mb-2 max-w-[85%] rounded-lg border border-[var(--color-border)]/50 bg-[var(--color-bg-secondary)]/20 overflow-hidden text-xs">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center gap-2 px-3 py-2 text-[var(--color-text-muted)] hover:bg-[var(--color-bg-secondary)]/50 transition-colors"
      >
        <Wrench className={cn('h-3 w-3 text-[var(--color-accent-primary)]', isStreaming && currentTool && 'animate-pulse')} />
        <span className="font-medium text-[var(--color-text-muted)]">
          {isStreaming && currentTool
            ? `Using ${currentTool.toolName?.replace('mcp__databricks__', '')}…`
            : `Agent trace · ${items.length} step${items.length !== 1 ? 's' : ''}`}
        </span>
        <ChevronDown className={cn('h-3 w-3 ml-auto transition-transform', !collapsed && 'rotate-180')} />
      </button>
      {!collapsed && (
        <div className="border-t border-[var(--color-border)]/30 max-h-96 overflow-y-auto">
          {items.map((item) => (
            <VerboseItem key={item.id} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}

// Determine the proxy URL for a Databricks file path
function toDatabricksProxyUrl(path: string): string {
  return `/api/workspace/file?path=${encodeURIComponent(path)}`;
}

function isDatabricksFilePath(src: string): boolean {
  return (
    src.startsWith('/Workspace/') ||
    src.startsWith('/Users/') ||
    src.startsWith('/Shared/') ||
    src.startsWith('dbfs:/') ||
    src.startsWith('/dbfs/') ||
    src.startsWith('/Volumes/')
  );
}

function extractDatabricksImagePaths(text: string): string[] {
  if (!text) return [];
  const re = /(?:dbfs:\/|\/(?:Volumes|Workspace|Users|Shared|dbfs)\/)[^\s"'`<>]+?\.(?:png|jpe?g|gif|webp)/gi;
  const matches = text.match(re) ?? [];
  return Array.from(new Set(matches));
}

function normalizeImagePathsToMarkdown(text: string): string {
  if (!text) return text;
  const markdownImagePaths = new Set(
    Array.from(text.matchAll(/!\[[^\]]*\]\(([^)]+)\)/g)).map((match) => match[1])
  );
  return text
    .split('\n')
    .map((line) => {
      const trimmed = line.trim();
      if (!trimmed) return line;
      if (trimmed.startsWith('![') || /^\[[^\]]*\]\([^)]+\)$/.test(trimmed)) return line;
      const matches = extractDatabricksImagePaths(trimmed);
      if (matches.length === 1 && matches[0] === trimmed) {
        if (markdownImagePaths.has(trimmed)) return line;
        return line.replace(trimmed, `![](${trimmed})`);
      }
      return line;
    })
    .join('\n');
}

// Renders a Databricks-hosted image via the workspace proxy.
// Fetches via JS (not <img src>) so we can capture server error details.
function DatabricksImage({
  path,
  alt,
  className,
}: {
  path: string;
  alt?: string;
  className?: string;
}) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const proxyUrl = toDatabricksProxyUrl(path);

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    fetch(proxyUrl, { credentials: 'include' })
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error((body as Record<string, string>).detail || res.statusText);
        }
        return res.blob();
      })
      .then((blob) => {
        if (!cancelled) {
          objectUrl = URL.createObjectURL(blob);
          setBlobUrl(objectUrl);
          setError(null);
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [proxyUrl]);

  if (error) {
    return (
      <div className="flex items-center gap-2 text-xs text-[var(--color-text-muted)] bg-[var(--color-bg-secondary)] rounded-md px-3 py-2 my-2 border border-[var(--color-border)]/30">
        <ImageIcon className="h-4 w-4 flex-shrink-0" />
        <span className="truncate">Image error ({path}): {error}</span>
      </div>
    );
  }
  if (!blobUrl) return null; // Loading

  return (
    <img
      src={blobUrl}
      alt={alt ?? ''}
      className={className ?? 'max-w-full rounded-md border border-[var(--color-border)]/30 my-2'}
    />
  );
}

// Image component for ReactMarkdown — proxies Databricks paths, falls back to
// a fetch()-based loader so errors are visible rather than silent broken icons.
function MarkdownImg({
  src,
  alt,
}: {
  src?: string;
  alt?: string;
}) {
  if (!src) return null;

  // All Databricks paths go through the proxy with error visibility
  if (isDatabricksFilePath(src) || src.startsWith('/api/workspace/file')) {
    const path = src.startsWith('/api/workspace/file')
      ? decodeURIComponent(new URL(src, window.location.origin).searchParams.get('path') ?? src)
      : src;
    return <DatabricksImage path={path} alt={alt} />;
  }

  // Regular URLs — plain img, retry via proxy on error
  return (
    <img
      src={src}
      alt={alt ?? ''}
      className="max-w-full rounded-md border border-[var(--color-border)]/30 my-2"
      loading="lazy"
      onError={(e) => {
        const img = e.currentTarget;
        if (!img.src.includes('/api/workspace/file')) {
          img.src = toDatabricksProxyUrl(src);
        }
      }}
    />
  );
}

// Shared ReactMarkdown component overrides for all chat bubbles
const markdownComponents: React.ComponentProps<typeof ReactMarkdown>['components'] = {
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-[var(--color-accent-primary)] underline hover:text-[var(--color-accent-secondary)]"
    >
      {children}
    </a>
  ),
  table: ({ children }) => (
    <div className="overflow-x-auto w-full my-2">
      <table className="min-w-max w-full border-collapse text-[13px]">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-[var(--color-bg-secondary)]">{children}</thead>
  ),
  th: ({ children }) => (
    <th className="border border-[var(--color-border)] px-3 py-1.5 text-left font-semibold text-[var(--color-text-heading)] whitespace-nowrap">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-[var(--color-border)] px-3 py-1.5 text-[var(--color-text-primary)] whitespace-nowrap">
      {children}
    </td>
  ),
  img: ({ src, alt }) => <MarkdownImg src={src} alt={alt} />,
};

function ResourceDropdown<T extends { state: string }>({
  label,
  items,
  selectedId,
  onSelect,
  nameKey,
  idKey,
}: {
  label: string;
  items: T[];
  selectedId?: string;
  onSelect: (id: string | undefined) => void;
  nameKey: keyof T;
  idKey: keyof T;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    if (open) { document.addEventListener('mousedown', handler); return () => document.removeEventListener('mousedown', handler); }
  }, [open]);

  const selected = items.find((i) => String(i[idKey]) === selectedId);
  const selectedName = selected ? String(selected[nameKey] || '') : '';

  return (
    <div ref={ref} className="relative">
      <label className="text-xs font-medium text-[var(--color-text-muted)] uppercase tracking-wider">{label}</label>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="mt-1.5 w-full flex items-center justify-between h-10 px-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] text-sm hover:border-[var(--color-accent-primary)]/40 focus:outline-none focus:ring-2 focus:ring-[var(--color-accent-primary)]/30 transition-colors"
      >
        <div className="flex items-center gap-2 min-w-0">
          {selected && (
            <span className={cn('w-2.5 h-2.5 rounded-full flex-shrink-0 ring-2 ring-offset-1 ring-offset-[var(--color-background)]',
              selected.state === 'RUNNING' ? 'bg-[var(--color-success)] ring-[var(--color-success)]/30' : 'bg-[var(--color-text-muted)]/50 ring-[var(--color-text-muted)]/20'
            )} />
          )}
          <span className={cn('truncate', selected ? 'text-[var(--color-text-primary)]' : 'text-[var(--color-text-muted)]')}>
            {selectedName || `Select ${label.toLowerCase()}...`}
          </span>
        </div>
        <ChevronDown className={cn('h-4 w-4 text-[var(--color-text-muted)] transition-transform flex-shrink-0', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="absolute left-0 right-0 top-full mt-1 max-h-52 overflow-y-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-elevated)] shadow-lg z-[60]">
          {items.map((item) => {
            const id = String(item[idKey]);
            const name = String(item[nameKey] || '');
            const isSelected = id === selectedId;
            return (
              <button
                key={id}
                onClick={() => { onSelect(id); setOpen(false); }}
                className={cn(
                  'w-full flex items-center gap-2.5 px-3 py-2.5 text-sm text-left transition-colors',
                  isSelected ? 'bg-[var(--color-accent-primary)]/5 text-[var(--color-accent-primary)]' : 'text-[var(--color-text-primary)] hover:bg-[var(--color-bg-secondary)]'
                )}
              >
                <span className={cn('w-2.5 h-2.5 rounded-full flex-shrink-0 ring-2 ring-offset-1 ring-offset-[var(--color-bg-elevated)]',
                  item.state === 'RUNNING' ? 'bg-[var(--color-success)] ring-[var(--color-success)]/30' : 'bg-[var(--color-text-muted)]/50 ring-[var(--color-text-muted)]/20'
                )} />
                <div className="flex-1 min-w-0">
                  <span className="truncate block">{name}</span>
                  <span className={cn('text-[10px] uppercase tracking-wider', item.state === 'RUNNING' ? 'text-[var(--color-success)]' : 'text-[var(--color-text-muted)]')}>
                    {item.state}
                  </span>
                </div>
                {isSelected && <Check className="h-4 w-4 flex-shrink-0 text-[var(--color-accent-primary)]" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ConfigPanel({
  isOpen,
  onClose,
  defaultCatalog,
  setDefaultCatalog,
  defaultSchema,
  setDefaultSchema,
  clusters,
  selectedClusterId,
  setSelectedClusterId,
  warehouses,
  selectedWarehouseId,
  setSelectedWarehouseId,
  workspaceFolder,
  setWorkspaceFolder,
  mlflowExperimentName,
  setMlflowExperimentName,
  workspaceUrl,
}: {
  isOpen: boolean;
  onClose: () => void;
  defaultCatalog: string;
  setDefaultCatalog: (v: string) => void;
  defaultSchema: string;
  setDefaultSchema: (v: string) => void;
  clusters: Cluster[];
  selectedClusterId?: string;
  setSelectedClusterId: (v: string | undefined) => void;
  warehouses: Warehouse[];
  selectedWarehouseId?: string;
  setSelectedWarehouseId: (v: string | undefined) => void;
  workspaceFolder: string;
  setWorkspaceFolder: (v: string) => void;
  mlflowExperimentName: string;
  setMlflowExperimentName: (v: string) => void;
  workspaceUrl: string | null;
}) {
  if (!isOpen) return null;

  return (
    <div className="absolute right-0 top-full mt-2 w-96 rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-elevated)] shadow-2xl z-50 overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-[var(--color-border)]/50 bg-[var(--color-bg-secondary)]/30">
        <h3 className="text-sm font-semibold text-[var(--color-text-heading)]">Configuration</h3>
        <button onClick={onClose} className="p-1 rounded-md hover:bg-[var(--color-bg-secondary)] transition-colors">
          <X className="h-4 w-4 text-[var(--color-text-muted)]" />
        </button>
      </div>
      <div className="p-5 space-y-5">
        <div>
          <label className="text-xs font-medium text-[var(--color-text-muted)] uppercase tracking-wider">Catalog / Schema</label>
          <div className="mt-1.5 flex items-center gap-0 rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] overflow-hidden focus-within:ring-2 focus-within:ring-[var(--color-accent-primary)]/30 focus-within:border-[var(--color-accent-primary)]/50">
            <input
              type="text"
              value={defaultCatalog}
              onChange={(e) => setDefaultCatalog(e.target.value)}
              placeholder="catalog"
              className="flex-1 h-10 px-3 bg-transparent text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)]/50 focus:outline-none min-w-0"
            />
            <span className="text-[var(--color-text-muted)] font-bold text-lg leading-none select-none">.</span>
            <input
              type="text"
              value={defaultSchema}
              onChange={(e) => setDefaultSchema(e.target.value)}
              placeholder="schema"
              className="flex-1 h-10 px-3 bg-transparent text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)]/50 focus:outline-none min-w-0"
            />
            {workspaceUrl && defaultCatalog && defaultSchema && (
              <a
                href={`${workspaceUrl}/explore/data/${defaultCatalog}/${defaultSchema}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-center h-10 w-10 flex-shrink-0 border-l border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-[var(--color-accent-primary)] hover:bg-[var(--color-bg-secondary)]/50 transition-colors"
                title="Open in Catalog Explorer"
              >
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            )}
          </div>
        </div>

        {clusters.length > 0 && (
          <ResourceDropdown
            label="Cluster"
            items={clusters}
            selectedId={selectedClusterId}
            onSelect={setSelectedClusterId}
            nameKey="cluster_name"
            idKey="cluster_id"
          />
        )}

        {warehouses.length > 0 && (
          <ResourceDropdown
            label="SQL Warehouse"
            items={warehouses}
            selectedId={selectedWarehouseId}
            onSelect={setSelectedWarehouseId}
            nameKey="warehouse_name"
            idKey="warehouse_id"
          />
        )}

        <div>
          <label className="text-xs font-medium text-[var(--color-text-muted)] uppercase tracking-wider">Workspace Folder</label>
          <input
            type="text"
            value={workspaceFolder}
            onChange={(e) => setWorkspaceFolder(e.target.value)}
            placeholder="/Workspace/Users/..."
            className="mt-1.5 w-full h-10 px-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)]/50 focus:outline-none focus:ring-2 focus:ring-[var(--color-accent-primary)]/30 focus:border-[var(--color-accent-primary)]/50"
          />
        </div>

        <div>
          <label className="text-xs font-medium text-[var(--color-text-muted)] uppercase tracking-wider">MLflow Experiment</label>
          <input
            type="text"
            value={mlflowExperimentName}
            onChange={(e) => setMlflowExperimentName(e.target.value)}
            placeholder="Experiment ID or name"
            className="mt-1.5 w-full h-10 px-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)]/50 focus:outline-none focus:ring-2 focus:ring-[var(--color-accent-primary)]/30 focus:border-[var(--color-accent-primary)]/50"
          />
        </div>
      </div>
    </div>
  );
}

export default function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { user, workspaceUrl } = useUser();

  // State
  const [project, setProject] = useState<Project | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentConversation, setCurrentConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [activityItems, setActivityItems] = useState<ActivityItem[]>([]);
  const [todos, setTodos] = useState<TodoItem[]>([]);
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [selectedClusterId, setSelectedClusterId] = useState<string | undefined>();
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [selectedWarehouseId, setSelectedWarehouseId] = useState<string | undefined>();
  const [userConfig, setUserConfig] = useState<UserSettings | null>(null);
  const [defaultCatalog, setDefaultCatalog] = useState<string>('');
  const [defaultSchema, setDefaultSchema] = useState<string>('');
  const [workspaceFolder, setWorkspaceFolder] = useState<string>('');
  const [mlflowExperimentName, setMlflowExperimentName] = useState<string>('');
  const [skillsExplorerOpen, setSkillsExplorerOpen] = useState(false);
  const [activeExecutionId, setActiveExecutionId] = useState<string | null>(null);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [verbose, setVerbose] = useState(true);
  const [configPanelOpen, setConfigPanelOpen] = useState(false);
  const [traceHistoryItems, setTraceHistoryItems] = useState<ActivityItem[][]>([]);
  const [attachedImages, setAttachedImages] = useState<AttachedImage[]>([]);
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);

  // Refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const queuedMessagesRef = useRef<QueuedMessage[]>([]);
  const currentConversationIdRef = useRef<string | null>(null);
  const activeStreamingConversationIdRef = useRef<string | null>(null);
  const streamingConversationIdsRef = useRef<Set<string>>(new Set());
  const executionIdByConversationRef = useRef<Record<string, string>>({});
  const inProgressByConversationRef = useRef<Record<string, InProgressConversationState>>({});
  const traceHistoryByConversationRef = useRef<Record<string, ActivityItem[][]>>({});
  const activeQueuedMessageIdRef = useRef<string | null>(null);
  const configPanelRef = useRef<HTMLDivElement>(null);
  const reconnectAttemptedRef = useRef<string | null>(null); // Track which conversation we've checked
  // True when current conversation was auto-selected (not explicitly chosen by user).
  // If true, first prompt should start a new conversation by default.
  const shouldAutoCreateOnNextSendRef = useRef(false);
  // Accumulates inline image paths during streaming; images are appended after text in the final message.
  const streamingImagesRef = useRef<string[]>([]);
  // Set to true when user sends a new message while streaming (interrupt-and-resend), suppresses cancel toast.
  const isInterruptingRef = useRef(false);
  const [streamingConversationIds, setStreamingConversationIds] = useState<string[]>([]);
  // Stores response stats (duration, tokens, cost) keyed by assistant message ID.
  const responseStatsRef = useRef<Record<string, {
    duration_ms?: number;
    num_turns?: number;
    total_cost_usd?: number;
    input_tokens?: number;
    output_tokens?: number;
    cache_read_tokens?: number;
    cache_creation_tokens?: number;
  }>>({});
  // Pending result event data captured during streaming, associated in onDone.
  const pendingResultRef = useRef<Record<string, unknown> | null>(null);

  const formatTokenCount = useCallback((n: number | undefined): string => {
    if (n == null) return '';
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
    return String(n);
  }, []);

  const formatDuration = useCallback((ms: number | undefined): string => {
    if (ms == null) return '';
    if (ms < 1_000) return `${ms}ms`;
    const s = ms / 1_000;
    if (s < 60) return `${s.toFixed(1)}s`;
    const m = Math.floor(s / 60);
    const rem = Math.round(s % 60);
    return `${m}m ${rem}s`;
  }, []);

  const formatTimestamp = useCallback((ts: string | null): string => {
    if (!ts) return '';
    const d = new Date(ts);
    return d.toLocaleString([], {
      year: 'numeric',
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  }, []);

  const appendTraceHistoryForConversation = useCallback((conversationId: string, trace: ActivityItem[]) => {
    if (trace.length === 0) return;
    const existing = traceHistoryByConversationRef.current[conversationId] || [];
    const last = existing[existing.length - 1];
    const next = last && tracesEqual(last, trace)
      ? existing
      : [...existing, trace].slice(-50);
    traceHistoryByConversationRef.current[conversationId] = next;
    if (currentConversationIdRef.current === conversationId) {
      setTraceHistoryItems(next);
    }
  }, []);

  const setConversationStreamingState = useCallback((
    conversationId: string,
    streaming: boolean,
    executionId?: string | null
  ) => {
    if (!conversationId) return;
    if (streaming) {
      streamingConversationIdsRef.current.add(conversationId);
      if (executionId) {
        executionIdByConversationRef.current[conversationId] = executionId;
      }
    } else {
      streamingConversationIdsRef.current.delete(conversationId);
      delete executionIdByConversationRef.current[conversationId];
    }
    setStreamingConversationIds(Array.from(streamingConversationIdsRef.current));

    if (currentConversationIdRef.current === conversationId) {
      setIsStreaming(streaming);
      if (streaming) {
        activeStreamingConversationIdRef.current = conversationId;
        setActiveExecutionId(executionId ?? executionIdByConversationRef.current[conversationId] ?? null);
      } else {
        if (activeStreamingConversationIdRef.current === conversationId) {
          activeStreamingConversationIdRef.current = null;
        }
        setActiveExecutionId(null);
      }
    }
  }, []);

  const updateConversationActivityItems = useCallback((
    conversationId: string | null | undefined,
    updater: (items: ActivityItem[]) => ActivityItem[]
  ): void => {
    const progressKey = conversationId ?? PENDING_CONVERSATION_KEY;
    const existing = inProgressByConversationRef.current[progressKey] ?? { streamingText: '' };
    const nextItems = updater(existing.activityItems ?? []);
    inProgressByConversationRef.current[progressKey] = {
      ...existing,
      activityItems: nextItems,
    };
    if (currentConversationIdRef.current === conversationId) {
      setActivityItems(nextItems);
    }
  }, []);

  // Keep queued user messages visually below the response that is currently finishing.
  const insertAssistantBeforeQueued = useCallback(
    (prev: Message[], assistant: Message, conversationId: string | null): Message[] => {
      const activeQueuedMessageId = activeQueuedMessageIdRef.current;
      if (activeQueuedMessageId) {
        const queuedIdx = prev.findIndex((m) => m.id === activeQueuedMessageId);
        if (queuedIdx >= 0) {
          return [...prev.slice(0, queuedIdx), assistant, ...prev.slice(queuedIdx)];
        }
      }
      if (!conversationId) return [...prev, assistant];
      const pendingForConversation = queuedMessagesRef.current.filter(
        (m) => m.conversationId === conversationId
      ).length;
      if (pendingForConversation <= 0) return [...prev, assistant];
      const insertAt = Math.max(prev.length - pendingForConversation, 0);
      return [...prev.slice(0, insertAt), assistant, ...prev.slice(insertAt)];
    },
    []
  );
  // Load project and conversations
  useEffect(() => {
    if (!projectId) return;

    const loadData = async () => {
      try {
        setIsLoading(true);
        const [projectData, conversationsData, clustersData, warehousesData, userSettingsData] = await Promise.all([
          fetchProject(projectId),
          fetchConversations(projectId),
          fetchClusters().catch(() => []), // Don't fail if clusters can't be loaded
          fetchWarehouses().catch(() => []), // Don't fail if warehouses can't be loaded
          fetchUserSettings().catch(() => null),
        ]);
        setProject(projectData);
        setConversations(conversationsData);
        setClusters(clustersData);
        setWarehouses(warehousesData);
        setUserConfig(userSettingsData);

        // Load first conversation by default, but prefer one with an active execution
        // so refresh restores the in-progress thread immediately.
        if (conversationsData.length > 0) {
          let preferredConversationId = conversationsData[0].id;
          let preferredExecutionState: { active: Execution | null; recent: Execution[] } | null = null;

          for (const summary of conversationsData.slice(0, 20)) {
            const state = await fetchExecutions(projectId, summary.id).catch(() => null);
            if (!state) continue;
            if (summary.id === preferredConversationId && !preferredExecutionState) {
              preferredExecutionState = state;
            }
            if (state.active) {
              preferredConversationId = summary.id;
              preferredExecutionState = state;
              break;
            }
          }

          const conv = await fetchConversation(projectId, preferredConversationId);
          const executionState = preferredExecutionState
            ?? await fetchExecutions(projectId, conv.id).catch(() => ({ active: null, recent: [] }));
          const hasActiveExecution = executionState.active?.status === 'running';
          if (hasActiveExecution && executionState.active?.id) {
            // Recover per-conversation streaming state after refresh/navigation.
            setConversationStreamingState(conv.id, true, executionState.active.id);
          }
          const persistedTraceHistory = buildTraceHistoryFromExecutions(executionState.recent);
          setCurrentConversation(conv);
          setMessages(conv.messages || []);
          const cachedTraceHistory = traceHistoryByConversationRef.current[conv.id] || [];
          const runTraceHistory = mergeTraceHistories(persistedTraceHistory, cachedTraceHistory);
          if (runTraceHistory.length > 0) {
            traceHistoryByConversationRef.current[conv.id] = runTraceHistory;
          }
          setTraceHistoryItems(runTraceHistory);
          // Keep sending in the selected conversation by default.
          // Previously we auto-created a new conversation on first send.
          shouldAutoCreateOnNextSendRef.current = false;
          // Restore cluster selection from conversation, or default to first cluster
          if (conv.cluster_id) {
            setSelectedClusterId(conv.cluster_id);
          } else if (clustersData.length > 0) {
            setSelectedClusterId(clustersData[0].cluster_id);
          }
          // Restore warehouse selection from conversation, or default to first warehouse
          if (conv.warehouse_id) {
            setSelectedWarehouseId(conv.warehouse_id);
          } else if (warehousesData.length > 0) {
            setSelectedWarehouseId(warehousesData[0].warehouse_id);
          }
          // Restore catalog/schema/folder from conversation, then user config, then empty
          setDefaultCatalog(conv.default_catalog || userSettingsData?.default_catalog || '');
          setDefaultSchema(conv.default_schema || userSettingsData?.default_schema || '');
          setWorkspaceFolder(conv.workspace_folder || userSettingsData?.workspace_folder || '');
        } else {
          shouldAutoCreateOnNextSendRef.current = false;
          // No conversation yet — apply user config defaults
          if (clustersData.length > 0) {
            setSelectedClusterId(clustersData[0].cluster_id);
          }
          if (warehousesData.length > 0) {
            setSelectedWarehouseId(warehousesData[0].warehouse_id);
          }
          setDefaultCatalog(userSettingsData?.default_catalog || '');
          setDefaultSchema(userSettingsData?.default_schema || '');
          setWorkspaceFolder(userSettingsData?.workspace_folder || '');
        }
      } catch (error) {
        console.error('Failed to load project:', error);
        toast.error('Failed to load project');
        navigate('/');
      } finally {
        setIsLoading(false);
      }
    };

    loadData();
  }, [projectId, navigate, setConversationStreamingState]);

  // Keep selected conversation ID available to async stream callbacks.
  useEffect(() => {
    currentConversationIdRef.current = currentConversation?.id ?? null;
  }, [currentConversation?.id]);

  useEffect(() => {
    const conversationId = currentConversation?.id;
    if (!conversationId) {
      setIsStreaming(false);
      activeStreamingConversationIdRef.current = null;
      setActiveExecutionId(null);
      return;
    }
    const isActive = streamingConversationIdsRef.current.has(conversationId);
    setIsStreaming(isActive);
    activeStreamingConversationIdRef.current = isActive ? conversationId : null;
    setActiveExecutionId(isActive ? (executionIdByConversationRef.current[conversationId] ?? null) : null);
  }, [currentConversation?.id]);

  // Keep left sidebar conversation title in sync with the chat header.
  useEffect(() => {
    if (!currentConversation?.id || !currentConversation.title) return;
    setConversations((prev) =>
      prev.map((conv) =>
        conv.id === currentConversation.id && conv.title !== currentConversation.title
          ? { ...conv, title: currentConversation.title }
          : conv
      )
    );
  }, [currentConversation?.id, currentConversation?.title]);

  // Check for active execution when conversation loads and reconnect if needed
  useEffect(() => {
    if (!projectId || !currentConversation?.id || isLoading || isStreaming) return;

    // Skip if we've already checked this conversation
    if (reconnectAttemptedRef.current === currentConversation.id) return;
    reconnectAttemptedRef.current = currentConversation.id;

    const checkAndReconnect = async () => {
      try {
        const { active } = await fetchExecutions(projectId, currentConversation.id);

        if (active && active.status === 'running') {
          console.log('[RECONNECT] Found active execution:', active.id);
          setIsReconnecting(true);
          setIsStreaming(true);
          activeStreamingConversationIdRef.current = currentConversation.id;
          setActiveExecutionId(active.id);

          // Create abort controller for reconnection
          abortControllerRef.current = new AbortController();

          let confirmedText = '';
          let deltaText = '';

          const buildDisplayText = () => {
            const base = !confirmedText ? deltaText
              : !deltaText ? confirmedText
              : confirmedText + (confirmedText.endsWith('\n') || deltaText.startsWith('\n') ? '' : '\n\n') + deltaText;
            const imgs = streamingImagesRef.current.map(p => `\n\n![](${p})`).join('');
            return base + imgs;
          };

          await reconnectToExecution({
            executionId: active.id,
            storedEvents: active.events,
            signal: abortControllerRef.current.signal,
            onEvent: (event) => {
              const type = event.type as string;

              if (type === 'text_delta') {
                const text = event.text as string;
                deltaText += text;
                setStreamingText(buildDisplayText());
              } else if (type === 'text') {
                const text = event.text as string;
                if (text) {
                  if (confirmedText && !confirmedText.endsWith('\n') && !text.startsWith('\n')) {
                    confirmedText += '\n\n';
                  }
                  confirmedText += text;
                  deltaText = '';
                  setStreamingText(buildDisplayText());
                }
              } else if (type === 'tool_use') {
                const toolItem: ActivityItem = {
                  id: event.tool_id as string,
                  type: 'tool_use',
                  content: '',
                  toolName: event.tool_name as string,
                  toolInput: event.tool_input as Record<string, unknown>,
                  timestamp: Date.now(),
                };
                updateConversationActivityItems(
                  currentConversation.id,
                  (items) => upsertActivityItem(items, toolItem)
                );
              } else if (type === 'tool_result') {
                const resultItem = {
                  id: `result-${event.tool_use_id}`,
                  type: 'tool_result' as const,
                  content: typeof event.content === 'string' ? event.content : JSON.stringify(event.content),
                  isError: event.is_error as boolean,
                  timestamp: Date.now(),
                };
                updateConversationActivityItems(
                  currentConversation.id,
                  (items) => upsertActivityItem(items, resultItem)
                );
              } else if (type === 'inline_image') {
                const path = event.path as string;
                if (!streamingImagesRef.current.includes(path)) {
                  streamingImagesRef.current = [...streamingImagesRef.current, path];
                  setStreamingText(buildDisplayText());
                }
              } else if (type === 'todos') {
                const todoItems = event.todos as TodoItem[];
                if (todoItems) {
                  setTodos(todoItems);
                }
              } else if (type === 'keepalive') {
                const elapsed = Number(event.elapsed_since_last_event ?? 0);
                const keepaliveItem: ActivityItem = {
                  id: 'keepalive-latest',
                  type: 'keepalive',
                  content: `Waiting on long-running step... ${Math.max(0, Math.round(elapsed))}s since last update`,
                  timestamp: Date.now(),
                };
                setActivityItems((prev) => {
                  const idx = prev.findIndex((i) => i.id === keepaliveItem.id);
                  if (idx >= 0) {
                    const updated = [...prev];
                    updated[idx] = keepaliveItem;
                    return updated;
                  }
                  return [...prev, keepaliveItem];
                });
              } else if (type === 'result') {
                pendingResultRef.current = event;
              } else if (type === 'error') {
                toast.error(event.error as string, { duration: 8000 });
              }
            },
            onError: (error) => {
              console.error('Reconnect error:', error);
              setIsStreaming(false);
              activeStreamingConversationIdRef.current = null;
              setIsReconnecting(false);
              setActiveExecutionId(null);
              setStreamingText('');
              setActivityItems([]);
              const msg = error.message ?? '';
              if (!msg.includes('Stream not found') && !msg.includes('404')) {
                toast.error('Lost connection to agent execution', { duration: 5000 });
              }
            },
            onDone: async () => {
              try {
                const conv = await fetchConversation(projectId, currentConversation.id);
                setCurrentConversation(conv);
                if (pendingResultRef.current) {
                  const r = pendingResultRef.current;
                  const lastAssistant = (conv.messages || []).filter(m => m.role === 'assistant').pop();
                  if (lastAssistant) {
                    responseStatsRef.current[lastAssistant.id] = {
                      duration_ms: r.duration_ms as number | undefined,
                      num_turns: r.num_turns as number | undefined,
                      total_cost_usd: r.total_cost_usd as number | undefined,
                      input_tokens: r.input_tokens as number | undefined,
                      output_tokens: r.output_tokens as number | undefined,
                      cache_read_tokens: r.cache_read_tokens as number | undefined,
                      cache_creation_tokens: r.cache_creation_tokens as number | undefined,
                    };
                  }
                  pendingResultRef.current = null;
                }
                setMessages(conv.messages || []);
              } catch (e) {
                console.error('Failed to reload conversation after reconnect:', e);
              }
              setStreamingText('');
              setIsStreaming(false);
              setIsReconnecting(false);
              setActiveExecutionId(null);
              setActivityItems((current) => {
                if (currentConversation.id) {
                  appendTraceHistoryForConversation(currentConversation.id, current);
                }
                return [];
              });
            },
          });
        }
      } catch (error) {
        console.error('Failed to check for active executions:', error);
        // Always clean up streaming state so UI doesn't get stuck
        setIsStreaming(false);
        activeStreamingConversationIdRef.current = null;
        setIsReconnecting(false);
        setActiveExecutionId(null);
        setStreamingText('');
        setActivityItems([]);
      }
    };

    checkAndReconnect();
  }, [projectId, currentConversation?.id, isLoading, isStreaming]);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingText, activityItems]);

  // Close config panel on outside click
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (configPanelRef.current && !configPanelRef.current.contains(event.target as Node)) {
        setConfigPanelOpen(false);
      }
    };
    if (configPanelOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [configPanelOpen]);

  // Select a conversation
  const handleSelectConversation = async (conversationId: string) => {
    if (!projectId || currentConversation?.id === conversationId) return;

    // Reset reconnect tracking for the new conversation
    reconnectAttemptedRef.current = null;

    try {
      shouldAutoCreateOnNextSendRef.current = false;
      const conv = await fetchConversation(projectId, conversationId);
      const executionState = await fetchExecutions(projectId, conversationId).catch(() => ({ active: null, recent: [] }));
      const hasActiveExecution = executionState.active?.status === 'running';
      if (hasActiveExecution && executionState.active?.id) {
        // If local refs were reset, rebuild streaming ownership from backend truth.
        setConversationStreamingState(conversationId, true, executionState.active.id);
      }
      const persistedTraceHistory = buildTraceHistoryFromExecutions(executionState.recent);
      const inProgress = inProgressByConversationRef.current[conversationId];
      const isConvStreaming = streamingConversationIdsRef.current.has(conversationId) || hasActiveExecution;
      const activeExecutionItems = executionState.active
        ? buildActivityItemsFromExecutionEvents(executionState.active.events || [])
        : [];
      const baseMessages = conv.messages || [];
      const viewMessages = inProgress?.userMessage
        ? [...baseMessages, inProgress.userMessage, ...(inProgress.queuedMessages || [])]
        : baseMessages;

      setCurrentConversation(conv);
      setMessages(viewMessages);
      setStreamingText(
        inProgress && streamingConversationIdsRef.current.has(conversationId)
          ? inProgress.streamingText
          : ''
      );
      setActivityItems(
        isConvStreaming
          ? (inProgress?.activityItems && inProgress.activityItems.length > 0
              ? inProgress.activityItems
              : activeExecutionItems)
          : []
      );
      const cachedTraceHistory = traceHistoryByConversationRef.current[conversationId] || [];
      const runTraceHistory = mergeTraceHistories(persistedTraceHistory, cachedTraceHistory);
      if (runTraceHistory.length > 0) {
        traceHistoryByConversationRef.current[conversationId] = runTraceHistory;
      }
      setTraceHistoryItems(runTraceHistory);
      // Restore cluster selection from conversation, or default to first cluster
      setSelectedClusterId(conv.cluster_id || (clusters.length > 0 ? clusters[0].cluster_id : undefined));
      // Restore warehouse selection from conversation, or default to first warehouse
      setSelectedWarehouseId(conv.warehouse_id || (warehouses.length > 0 ? warehouses[0].warehouse_id : undefined));
      // Restore catalog/schema/folder from conversation, then user config, then empty
      setDefaultCatalog(conv.default_catalog || userConfig?.default_catalog || '');
      setDefaultSchema(conv.default_schema || userConfig?.default_schema || '');
      setWorkspaceFolder(conv.workspace_folder || userConfig?.workspace_folder || '');
      setIsStreaming(isConvStreaming);
      activeStreamingConversationIdRef.current = isConvStreaming ? conversationId : null;
      setActiveExecutionId(
        isConvStreaming
          ? (executionIdByConversationRef.current[conversationId] ?? executionState.active?.id ?? null)
          : null
      );
    } catch (error) {
      console.error('Failed to load conversation:', error);
      toast.error('Failed to load conversation');
    }
  };

  // Create new conversation
  const handleNewConversation = async () => {
    if (!projectId) return;

    try {
      shouldAutoCreateOnNextSendRef.current = false;
      const conv = await createConversation(projectId);
      setConversations((prev) => [conv, ...prev]);
      setCurrentConversation(conv);
      setMessages([]);
      setActivityItems([]);
      setTraceHistoryItems([]);
      // Reset to user config defaults for new conversations
      setDefaultCatalog(userConfig?.default_catalog || '');
      setDefaultSchema(userConfig?.default_schema || '');
      setWorkspaceFolder(userConfig?.workspace_folder || '');
      inputRef.current?.focus();
    } catch (error) {
      console.error('Failed to create conversation:', error);
      toast.error('Failed to create conversation');
    }
  };

  // Delete conversation
  const handleDeleteConversation = async (conversationId: string) => {
    if (!projectId) return;

    try {
      await deleteConversation(projectId, conversationId);
      setConversations((prev) => prev.filter((c) => c.id !== conversationId));
      delete traceHistoryByConversationRef.current[conversationId];

      if (currentConversation?.id === conversationId) {
        const remaining = conversations.filter((c) => c.id !== conversationId);
        if (remaining.length > 0) {
          const conv = await fetchConversation(projectId, remaining[0].id);
          const executionState = await fetchExecutions(projectId, remaining[0].id).catch(() => ({ active: null, recent: [] }));
          const persistedTraceHistory = buildTraceHistoryFromExecutions(executionState.recent);
          setCurrentConversation(conv);
          setMessages(conv.messages || []);
          const cachedTraceHistory = traceHistoryByConversationRef.current[conv.id] || [];
          const runTraceHistory = mergeTraceHistories(persistedTraceHistory, cachedTraceHistory);
          if (runTraceHistory.length > 0) {
            traceHistoryByConversationRef.current[conv.id] = runTraceHistory;
          }
          setTraceHistoryItems(runTraceHistory);
          // After deleting the active conversation, continue in the newly selected one.
          shouldAutoCreateOnNextSendRef.current = false;
        } else {
          setCurrentConversation(null);
          setMessages([]);
          setTraceHistoryItems([]);
          shouldAutoCreateOnNextSendRef.current = false;
        }
        setActivityItems([]);
      }
      toast.success('Conversation deleted');
    } catch (error) {
      console.error('Failed to delete conversation:', error);
      toast.error('Failed to delete conversation');
    }
  };

  const sendPreparedMessage = useCallback(async (
    prepared: QueuedMessage,
    addUserMessage: boolean = true,
    queuedMessageId?: string
  ) => {
    const { conversationId: targetConversationId, userMessage, displayContent, imagesToSend } = prepared;
    if (!projectId) return;

    isInterruptingRef.current = false;
    let activeQueuedMessageId = addUserMessage ? null : (queuedMessageId ?? null);
    if (!addUserMessage && queuedMessageId) {
      const runningQueuedMessageId = `temp-running-${Date.now()}`;
      activeQueuedMessageId = runningQueuedMessageId;
      setMessages((prev) =>
        prev.map((message) =>
          message.id === queuedMessageId
            ? { ...message, id: runningQueuedMessageId }
            : message
        )
      );
      if (targetConversationId) {
        const progressState = inProgressByConversationRef.current[targetConversationId];
        if (progressState?.queuedMessages) {
          inProgressByConversationRef.current[targetConversationId] = {
            ...progressState,
            queuedMessages: progressState.queuedMessages
              .filter((message) => message.id !== queuedMessageId)
              .map((message) =>
                message.id === queuedMessageId
                  ? { ...message, id: runningQueuedMessageId }
                  : message
              ),
          };
        }
      }
    }
    activeQueuedMessageIdRef.current = activeQueuedMessageId;
    activeStreamingConversationIdRef.current = targetConversationId;
    setIsStreaming(true);
    setStreamingText('');
    setActivityItems([]);
    streamingImagesRef.current = [];
    setTodos([]);

    if (addUserMessage) {
      const tempUserMessage: Message = {
        id: `temp-${Date.now()}`,
        conversation_id: targetConversationId || '',
        role: 'user',
        content: displayContent,
        timestamp: new Date().toISOString(),
        is_error: false,
      };
      setMessages((prev) => [...prev, tempUserMessage]);
      const progressKey = targetConversationId ?? PENDING_CONVERSATION_KEY;
      const existing = inProgressByConversationRef.current[progressKey] ?? { streamingText: '' };
      inProgressByConversationRef.current[progressKey] = {
        ...existing,
        activityItems: existing.activityItems ?? [],
        userMessage: tempUserMessage,
      };

    }

    abortControllerRef.current = new AbortController();

    try {
      let conversationId = targetConversationId;
      let executionIdForRun: string | null = null;
      // confirmedText: authoritative text from completed text events (with proper separators)
      // deltaText: accumulated text_delta tokens for the current in-progress block
      let confirmedText = '';
      let deltaText = '';

      const buildDisplayText = () => {
        const base = !confirmedText ? deltaText
          : !deltaText ? confirmedText
          : confirmedText + (confirmedText.endsWith('\n') || deltaText.startsWith('\n') ? '' : '\n\n') + deltaText;
        const imgs = streamingImagesRef.current.map(p => `\n\n![](${p})`).join('');
        return base + imgs;
      };

      await invokeAgent({
        projectId,
        conversationId,
        message: userMessage,
        images: imagesToSend.length > 0 ? imagesToSend : null,
        clusterId: selectedClusterId,
        defaultCatalog,
        defaultSchema,
        warehouseId: selectedWarehouseId,
        workspaceFolder,
        mlflowExperimentName: mlflowExperimentName || null,
        signal: abortControllerRef.current.signal,
        onExecutionId: (executionId) => {
          executionIdForRun = executionId;
          setActiveExecutionId(executionId);
          if (conversationId) {
            setConversationStreamingState(conversationId, true, executionId);
          }
        },
        onEvent: (event) => {
          const type = event.type as string;

          if (type === 'conversation.created') {
            conversationId = event.conversation_id as string;
            setConversationStreamingState(conversationId, true, executionIdForRun);
            shouldAutoCreateOnNextSendRef.current = false;
            // If this execution started before the conversation was created
            // (conversationId was null), bind streaming ownership to the new ID
            // so onDone/onError can clear streaming state correctly.
            if (activeStreamingConversationIdRef.current === null) {
              activeStreamingConversationIdRef.current = conversationId;
            }
            const pending = inProgressByConversationRef.current[PENDING_CONVERSATION_KEY];
            if (pending) {
              inProgressByConversationRef.current[conversationId] = pending;
              delete inProgressByConversationRef.current[PENDING_CONVERSATION_KEY];
            }
            // Only bind UI to the newly-created conversation when this run still
            // belongs to the currently viewed chat. If the user switched chats
            // meanwhile, don't force navigation and risk cross-chat mingling.
            if (
              currentConversationIdRef.current === targetConversationId
              || (targetConversationId === null && currentConversationIdRef.current === null)
            ) {
              setCurrentConversation({
                id: conversationId,
                project_id: projectId,
                title: 'New Chat',
                created_at: new Date().toISOString(),
              });
            }
            // Rebind any queued messages that were created before the
            // conversation existed (conversationId was null).
            for (const qm of queuedMessagesRef.current) {
              if (qm.conversationId === null) {
                qm.conversationId = conversationId;
              }
            }
            // Update temp-queued message objects in the message list too.
            setMessages((prev) =>
              prev.map((m) =>
                m.id.startsWith('temp-queued-') && !m.conversation_id
                  ? { ...m, conversation_id: conversationId }
                  : m
              )
            );
          } else if (type === 'text_delta') {
            // Token-by-token streaming - accumulate delta for current block
            const text = event.text as string;
            deltaText += text;
            if (conversationId) {
              const existing = inProgressByConversationRef.current[conversationId] ?? { streamingText: '' };
              inProgressByConversationRef.current[conversationId] = {
                ...existing,
                streamingText: buildDisplayText(),
              };
            }
            if (currentConversationIdRef.current === conversationId) setStreamingText(buildDisplayText());
          } else if (type === 'text') {
            // Complete text block from AssistantMessage - authoritative content for one block.
            // Add it to confirmedText (with separator) and reset the delta so that
            // future text_delta events for the NEXT block don't concatenate directly.
            const text = event.text as string;
            if (text) {
              if (confirmedText && !confirmedText.endsWith('\n') && !text.startsWith('\n')) {
                confirmedText += '\n\n';
              }
              confirmedText += text;
              deltaText = '';  // Block confirmed - clear delta so next block starts fresh
              if (conversationId) {
                const existing = inProgressByConversationRef.current[conversationId] ?? { streamingText: '' };
                inProgressByConversationRef.current[conversationId] = {
                  ...existing,
                  streamingText: buildDisplayText(),
                };
              }
              if (currentConversationIdRef.current === conversationId) setStreamingText(buildDisplayText());
            }
          } else if (type === 'thinking' || type === 'thinking_delta') {
            // Handle both complete thinking blocks and streaming thinking deltas.
            // The SDK emits thinking_delta events first (streaming), then a complete
            // thinking event from AssistantMessage. We must not add a second item —
            // instead replace the delta-built item with the authoritative complete block.
            const thinking = (event.thinking as string) || '';
            if (thinking) {
              updateConversationActivityItems(
                conversationId,
                (items) => applyThinkingEventToItems(items, type as 'thinking' | 'thinking_delta', thinking)
              );
            }
          } else if (type === 'tool_use') {
            const toolItem: ActivityItem = {
              id: event.tool_id as string,
              type: 'tool_use',
              content: '',
              toolName: event.tool_name as string,
              toolInput: event.tool_input as Record<string, unknown>,
              timestamp: Date.now(),
            };
            updateConversationActivityItems(conversationId, (items) => upsertActivityItem(items, toolItem));
          } else if (type === 'tool_result') {
            let content = event.content as string;

            // Parse and improve error messages
            if (event.is_error && typeof content === 'string') {
              // Extract error from XML-style tags like <tool_use_error>...</tool_use_error>
              const errorMatch = content.match(/<tool_use_error>(.*?)<\/tool_use_error>/s);
              if (errorMatch) {
                content = errorMatch[1].trim();
              }

              // Improve generic "Stream closed" errors
              if (content === 'Stream closed' || content.includes('Stream closed')) {
                content = 'Tool execution interrupted: The operation took too long or the connection was lost. This may happen when operations exceed the 50-second timeout window. Check backend logs for details.';
              }
            }

            const resultItem = {
              id: `result-${event.tool_use_id}`,
              type: 'tool_result' as const,
              content: typeof content === 'string' ? content : JSON.stringify(content),
              isError: event.is_error as boolean,
              timestamp: Date.now(),
            };
            updateConversationActivityItems(conversationId, (items) => upsertActivityItem(items, resultItem));
          } else if (type === 'error') {
            let errorMsg = event.error as string;

            // Improve generic error messages
            if (errorMsg === 'Stream closed' || errorMsg.includes('Stream closed')) {
              errorMsg = 'Execution interrupted: The operation took too long or the connection was lost. Operations exceeding 50 seconds may be interrupted. Check backend logs for details.';
            }

            toast.error(errorMsg, {
              duration: 8000,
            });
          } else if (type === 'inline_image') {
            const path = event.path as string;
            if (!streamingImagesRef.current.includes(path)) {
              streamingImagesRef.current = [...streamingImagesRef.current, path];
              if (currentConversationIdRef.current === conversationId) setStreamingText(buildDisplayText());
            }
          } else if (type === 'cancelled') {
            // Suppress toast when user cancelled by sending a new message
            if (!isInterruptingRef.current) toast.info('Generation stopped');
          } else if (type === 'todos') {
            // Update todo list from agent
            const todoItems = event.todos as TodoItem[];
            if (todoItems && currentConversationIdRef.current === conversationId) {
              setTodos(todoItems);
            }
          } else if (type === 'keepalive') {
            const elapsed = Number(event.elapsed_since_last_event ?? 0);
            if (currentConversationIdRef.current === conversationId) {
              const keepaliveItem: ActivityItem = {
                id: 'keepalive-latest',
                type: 'keepalive',
                content: `Waiting on long-running step... ${Math.max(0, Math.round(elapsed))}s since last update`,
                timestamp: Date.now(),
              };
              setActivityItems((prev) => {
                const idx = prev.findIndex((i) => i.id === keepaliveItem.id);
                if (idx >= 0) {
                  const updated = [...prev];
                  updated[idx] = keepaliveItem;
                  return updated;
                }
                return [...prev, keepaliveItem];
              });
            }
          } else if (type === 'result') {
            pendingResultRef.current = event;
          }
        },
        onError: (error) => {
          console.error('Stream error:', error);
          // Show the actual error message instead of generic text
          const errorMessage = error.message || 'Failed to get response';
          toast.error(errorMessage, {
            duration: 8000, // Show error for 8 seconds
          });
        },
        onDone: async () => {
          const fullText = confirmedText || deltaText;
          const images = streamingImagesRef.current;
          streamingImagesRef.current = [];
          const imageMarkdown = images
            .filter((p) => !fullText.includes(`](${p})`) && !fullText.includes(`(${p})`))
            .map((p) => `![](${p})`)
            .join('\n\n');
          const content = [fullText, imageMarkdown].filter(Boolean).join('\n\n');
          const assistantMsgId = `msg-${Date.now()}`;
          if (content && currentConversationIdRef.current === conversationId) {
            setMessages((prev) =>
              insertAssistantBeforeQueued(
                prev,
                {
                  id: assistantMsgId,
                  conversation_id: conversationId || '',
                  role: 'assistant',
                  content,
                  timestamp: new Date().toISOString(),
                  is_error: false,
                },
                conversationId
              )
            );
          }
          if (pendingResultRef.current) {
            const r = pendingResultRef.current;
            responseStatsRef.current[assistantMsgId] = {
              duration_ms: r.duration_ms as number | undefined,
              num_turns: r.num_turns as number | undefined,
              total_cost_usd: r.total_cost_usd as number | undefined,
              input_tokens: r.input_tokens as number | undefined,
              output_tokens: r.output_tokens as number | undefined,
              cache_read_tokens: r.cache_read_tokens as number | undefined,
              cache_creation_tokens: r.cache_creation_tokens as number | undefined,
            };
            pendingResultRef.current = null;
          }
          if (currentConversationIdRef.current === conversationId) setStreamingText('');
          if (conversationId) setConversationStreamingState(conversationId, false);
          activeQueuedMessageIdRef.current = null;
          if (conversationId) {
            delete inProgressByConversationRef.current[conversationId];
          }
          delete inProgressByConversationRef.current[PENDING_CONVERSATION_KEY];
          setActiveExecutionId(null);
          if (currentConversationIdRef.current === conversationId) {
            setActivityItems((current) => {
              if (conversationId) {
                appendTraceHistoryForConversation(conversationId, current);
              }
              return [];
            });
          }

          if (conversationId) {
            const conv = await fetchConversation(projectId, conversationId);
            if (currentConversationIdRef.current === conversationId) {
              setCurrentConversation(conv);
            }
          }

          // Refresh conversations after the run finishes so sidebar updates
          // follow the finalized header/title timing.
          fetchConversations(projectId).then(setConversations).catch(() => undefined);

          // Queue is per-conversation. Only continue queued messages for this chat.
          const nextIdx = queuedMessagesRef.current.findIndex((m) => m.conversationId === conversationId);
          const next = nextIdx >= 0 ? queuedMessagesRef.current.splice(nextIdx, 1)[0] : undefined;
          if (next) {
            toast.info(`Sending queued message (${queuedMessagesRef.current.length} remaining)...`);
            void sendPreparedMessage(next, false, next.queuedMessageId);
          }
        },
      });
    } catch (error) {
      // Ignore AbortError — handleStopGeneration handles cleanup for user-initiated stops
      if (error instanceof Error && error.name === 'AbortError') return;
      console.error('Failed to send message:', error);
      const errorMessage = error instanceof Error ? error.message : 'Failed to send message';
      toast.error(errorMessage, {
        duration: 8000,
      });
      if (activeStreamingConversationIdRef.current === targetConversationId) {
        if (targetConversationId) setConversationStreamingState(targetConversationId, false);
      }
      if (targetConversationId) {
        delete inProgressByConversationRef.current[targetConversationId];
      }
      delete inProgressByConversationRef.current[PENDING_CONVERSATION_KEY];
      activeQueuedMessageIdRef.current = null;

      const nextIdx = queuedMessagesRef.current.findIndex((m) => m.conversationId === targetConversationId);
      const next = nextIdx >= 0 ? queuedMessagesRef.current.splice(nextIdx, 1)[0] : undefined;
      if (next) {
        toast.info(`Sending queued message (${queuedMessagesRef.current.length} remaining)...`);
        void sendPreparedMessage(next, false, next.queuedMessageId);
      }
    }
  }, [projectId, currentConversation?.id, selectedClusterId, defaultCatalog, defaultSchema, selectedWarehouseId, workspaceFolder, mlflowExperimentName, appendTraceHistoryForConversation, setConversationStreamingState, updateConversationActivityItems]);

  // Start an execution in another conversation while keeping the current chat live.
  const sendBackgroundMessage = useCallback(async (
    prepared: QueuedMessage,
    addUserMessage: boolean = true
  ) => {
    if (!projectId) return;
    let { conversationId } = prepared;
    const { userMessage, displayContent, imagesToSend } = prepared;
    let executionIdForRun: string | null = null;
    let confirmedText = '';
    let deltaText = '';

    const buildDisplayText = () =>
      !confirmedText
        ? deltaText
        : !deltaText
          ? confirmedText
          : confirmedText + (confirmedText.endsWith('\n') || deltaText.startsWith('\n') ? '' : '\n\n') + deltaText;

    if (addUserMessage && currentConversationIdRef.current === conversationId) {
      setMessages((prev) => [
        ...prev,
        {
          id: `temp-bg-${Date.now()}`,
          conversation_id: conversationId || '',
          role: 'user',
          content: displayContent,
          timestamp: new Date().toISOString(),
          is_error: false,
        },
      ]);
    }

    await invokeAgent({
      projectId,
      conversationId,
      message: userMessage,
      images: imagesToSend.length > 0 ? imagesToSend : null,
      clusterId: selectedClusterId,
      defaultCatalog,
      defaultSchema,
      warehouseId: selectedWarehouseId,
      workspaceFolder,
      mlflowExperimentName: mlflowExperimentName || null,
      onExecutionId: (executionId) => {
        executionIdForRun = executionId;
        if (conversationId) {
          setConversationStreamingState(conversationId, true, executionId);
        }
      },
      onEvent: (event) => {
        const type = event.type as string;

        if (type === 'conversation.created') {
          conversationId = event.conversation_id as string;
          setConversationStreamingState(conversationId, true, executionIdForRun);
          setConversations((prev) =>
            prev.some((conv) => conv.id === conversationId)
              ? prev
              : [{
                  id: conversationId,
                  project_id: projectId,
                  title: 'New Chat',
                  created_at: new Date().toISOString(),
                }, ...prev]
          );
          return;
        }

        if (!conversationId) return;

        if (type === 'text_delta') {
          deltaText += (event.text as string) || '';
          const existing = inProgressByConversationRef.current[conversationId] ?? { streamingText: '' };
          inProgressByConversationRef.current[conversationId] = {
            ...existing,
            streamingText: buildDisplayText(),
          };
          if (currentConversationIdRef.current === conversationId) {
            setStreamingText(buildDisplayText());
          }
          return;
        }

        if (type === 'text') {
          const text = (event.text as string) || '';
          if (!text) return;
          if (confirmedText && !confirmedText.endsWith('\n') && !text.startsWith('\n')) {
            confirmedText += '\n\n';
          }
          confirmedText += text;
          deltaText = '';
          const existing = inProgressByConversationRef.current[conversationId] ?? { streamingText: '' };
          inProgressByConversationRef.current[conversationId] = {
            ...existing,
            streamingText: buildDisplayText(),
          };
          if (currentConversationIdRef.current === conversationId) {
            setStreamingText(buildDisplayText());
          }
          return;
        }

        if (type === 'thinking' || type === 'thinking_delta') {
          const thinking = (event.thinking as string) || '';
          if (!thinking) return;
          updateConversationActivityItems(
            conversationId,
            (items) => applyThinkingEventToItems(items, type as 'thinking' | 'thinking_delta', thinking)
          );
          return;
        }

        if (type === 'tool_use') {
          const toolItem: ActivityItem = {
            id: event.tool_id as string,
            type: 'tool_use',
            content: '',
            toolName: event.tool_name as string,
            toolInput: event.tool_input as Record<string, unknown>,
            timestamp: Date.now(),
          };
          updateConversationActivityItems(conversationId, (items) => upsertActivityItem(items, toolItem));
          return;
        }

        if (type === 'tool_result') {
          const resultItem = {
            id: `result-${event.tool_use_id}`,
            type: 'tool_result' as const,
            content: typeof event.content === 'string' ? event.content : JSON.stringify(event.content),
            isError: Boolean(event.is_error),
            timestamp: Date.now(),
          };
          updateConversationActivityItems(conversationId, (items) => upsertActivityItem(items, resultItem));
        }
      },
      onError: (error) => {
        if (conversationId) {
          setConversationStreamingState(conversationId, false);
          delete inProgressByConversationRef.current[conversationId];
        }
        if (currentConversationIdRef.current === conversationId) {
          setStreamingText('');
        }
        toast.error(error.message, { duration: 8000 });
      },
      onDone: async () => {
        if (!conversationId) return;
        setConversationStreamingState(conversationId, false);
        delete inProgressByConversationRef.current[conversationId];
        if (currentConversationIdRef.current === conversationId) {
          setActivityItems((current) => {
            appendTraceHistoryForConversation(conversationId!, current);
            return current;
          });
          setStreamingText('');
          const conv = await fetchConversation(projectId, conversationId);
          setCurrentConversation(conv);
          setMessages(conv.messages || []);
        }
        fetchConversations(projectId).then(setConversations).catch(() => undefined);
      },
    });
  }, [projectId, selectedClusterId, defaultCatalog, defaultSchema, selectedWarehouseId, workspaceFolder, mlflowExperimentName, appendTraceHistoryForConversation, setConversationStreamingState, updateConversationActivityItems]);

  // Send message — allows new messages while streaming by queueing them.
  const handleSendMessage = useCallback(async () => {
    const hasContent = input.trim() || attachedImages.length > 0 || attachedFiles.length > 0;
    if (!projectId || !hasContent) return;

    const userText = input.trim();
    setInput('');

    // Capture and clear attachments
    const imagesToSend = attachedImages.map((img): ImageAttachment => ({
      type: 'base64',
      media_type: img.mediaType,
      data: img.data,
    }));
    const filesToSend = [...attachedFiles];
    setAttachedImages([]);
    setAttachedFiles([]);

    // Upload attached files into project-local uploads folder and send paths only.
    const uploadedFilePaths: string[] = [];
    for (const attached of filesToSend) {
      try {
        const uploaded = await uploadProjectFile(projectId, attached.file);
        uploadedFilePaths.push(uploaded.path);
      } catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        toast.error(`Failed to upload "${attached.file.name}": ${msg}`);
      }
    }

    // Build the actual message sent to the agent (text + uploaded local file paths)
    let agentMessage = userText;
    if (uploadedFilePaths.length > 0) {
      agentMessage += `\n\n--- Attached local files (project paths) ---\n${uploadedFilePaths.map((p) => `- ${p}`).join('\n')}\nUse these file paths and read files by path when needed. Do not ask for file contents unless required.\n---`;
    }

    // Build the display message shown in chat
    const attachmentParts: string[] = [];
    if (imagesToSend.length > 0) attachmentParts.push(`📷 ${imagesToSend.length} image${imagesToSend.length > 1 ? 's' : ''}`);
    if (uploadedFilePaths.length > 0) attachmentParts.push(`📎 ${uploadedFilePaths.join(', ')}`);
    const displayContent = [userText, attachmentParts.join(' · ')].filter(Boolean).join('\n');
    const userMessage = agentMessage.trim() || userText;
    if (!userMessage && imagesToSend.length === 0) {
      toast.error('No content to send (file upload failed)');
      return;
    }

    const shouldCreateNewConversationNow =
      shouldAutoCreateOnNextSendRef.current && !!currentConversation?.id;
    if (shouldCreateNewConversationNow) {
      // Clear the auto-selected conversation view; this prompt starts a new chat.
      setCurrentConversation(null);
      setMessages([]);
      setActivityItems([]);
      setTraceHistoryItems([]);
      setStreamingText('');
      shouldAutoCreateOnNextSendRef.current = false;
    }

    const prepared: QueuedMessage = {
      conversationId: shouldCreateNewConversationNow ? null : (currentConversation?.id ?? null),
      userMessage,
      displayContent,
      imagesToSend,
    };

    // If the same conversation is already streaming, queue in that conversation only.
    if (isStreaming) {
      const activeId = activeStreamingConversationIdRef.current;
      const sameConversation =
        activeId === prepared.conversationId ||
        (prepared.conversationId === null && activeId !== null);
      if (sameConversation) {
        // Bind the queued message to the active conversation so onDone
        // picks it up with the correct ID.
        if (prepared.conversationId === null && activeId !== null) {
          prepared.conversationId = activeId;
        }
        const queuedUserMessage: Message = {
          id: `temp-queued-${Date.now()}`,
          conversation_id: activeId || '',
          role: 'user',
          content: displayContent,
          timestamp: new Date().toISOString(),
          is_error: false,
        };
        prepared.queuedMessageId = queuedUserMessage.id;
        queuedMessagesRef.current.push(prepared);
        setMessages((prev) => [...prev, queuedUserMessage]);
        const progressKey = prepared.conversationId ?? PENDING_CONVERSATION_KEY;
        const existing = inProgressByConversationRef.current[progressKey] ?? { streamingText: '' };
        inProgressByConversationRef.current[progressKey] = {
          ...existing,
          queuedMessages: [...(existing.queuedMessages || []), queuedUserMessage],
        };
        toast.info(`Queued in this chat (${queuedMessagesRef.current.length} waiting)`);
        return;
      }

      // Different chat: run independently instead of cross-chat queueing.
      try {
        await sendBackgroundMessage(prepared, true);
      } catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        toast.error(msg, { duration: 8000 });
      }
      return;
    }

    await sendPreparedMessage(prepared, true);
  }, [projectId, input, attachedImages, attachedFiles, isStreaming, currentConversation?.id, sendPreparedMessage, sendBackgroundMessage]);

  // Stop generation - abort client stream AND tell backend to cancel
  const handleStopGeneration = useCallback(async () => {
    abortControllerRef.current?.abort();

    // Tell the backend to cancel the agent execution
    if (activeExecutionId) {
      try {
        await stopExecution(activeExecutionId);
      } catch (error) {
        console.error('Failed to stop execution on backend:', error);
      }
    }

    // Finalize UI: keep user message and save whatever partial response we have
    setStreamingText((currentText) => {
      if (currentText) {
        setMessages((prev) =>
          insertAssistantBeforeQueued(
            prev,
            {
              id: `msg-stopped-${Date.now()}`,
              conversation_id: '',
              role: 'assistant' as const,
              content: currentText,
              timestamp: new Date().toISOString(),
              is_error: false,
            },
            activeStreamingConversationIdRef.current
          )
        );
      }
      return '';
    });
    const stoppedConversationId = activeStreamingConversationIdRef.current;
    if (stoppedConversationId) {
      const before = queuedMessagesRef.current.length;
      queuedMessagesRef.current = queuedMessagesRef.current.filter(
        (m) => m.conversationId !== stoppedConversationId
      );
      const removed = before - queuedMessagesRef.current.length;
      if (removed > 0) {
        toast.info(`Cleared ${removed} queued message${removed > 1 ? 's' : ''} for this chat`);
      }
      delete inProgressByConversationRef.current[stoppedConversationId];
      setMessages((prev) =>
        prev.filter(
          (m) =>
            !(m.id.startsWith('temp-queued-') && m.conversation_id === stoppedConversationId)
        )
      );
    }
    delete inProgressByConversationRef.current[PENDING_CONVERSATION_KEY];
    if (stoppedConversationId) {
      setConversationStreamingState(stoppedConversationId, false);
    } else {
      setIsStreaming(false);
      activeStreamingConversationIdRef.current = null;
      setActiveExecutionId(null);
    }
    activeQueuedMessageIdRef.current = null;
    setActivityItems((current) => {
      if (stoppedConversationId) {
        appendTraceHistoryForConversation(stoppedConversationId, current);
      }
      return current;
    });
  }, [activeExecutionId, appendTraceHistoryForConversation, insertAssistantBeforeQueued, setConversationStreamingState]);

  const handleRemoveQueuedMessage = useCallback((queuedMessageId: string) => {
    queuedMessagesRef.current = queuedMessagesRef.current.filter(
      (queued) => queued.queuedMessageId !== queuedMessageId
    );
    setMessages((prev) => prev.filter((message) => message.id !== queuedMessageId));

    for (const key of Object.keys(inProgressByConversationRef.current)) {
      const state = inProgressByConversationRef.current[key];
      if (!state?.queuedMessages) continue;
      const nextQueued = state.queuedMessages.filter((message) => message.id !== queuedMessageId);
      inProgressByConversationRef.current[key] = {
        ...state,
        queuedMessages: nextQueued.length > 0 ? nextQueued : undefined,
      };
    }
  }, []);

  const handleMoveQueuedMessageUp = useCallback((queuedMessageId: string) => {
    const conversationId = currentConversation?.id ?? null;
    if (!conversationId) return;

    const queueIndexes = queuedMessagesRef.current
      .map((queued, index) => ({ queued, index }))
      .filter(({ queued }) => queued.conversationId === conversationId);

    const position = queueIndexes.findIndex(({ queued }) => queued.queuedMessageId === queuedMessageId);
    if (position <= 0) return;

    const currentIndex = queueIndexes[position].index;
    const previousIndex = queueIndexes[position - 1].index;
    const reordered = [...queuedMessagesRef.current];
    [reordered[previousIndex], reordered[currentIndex]] = [reordered[currentIndex], reordered[previousIndex]];
    queuedMessagesRef.current = reordered;

    const queuedIdsInOrder = reordered
      .filter((queued) => queued.conversationId === conversationId)
      .map((queued) => queued.queuedMessageId)
      .filter((id): id is string => Boolean(id));

    setMessages((prev) => {
      const queuedMap = new Map(
        prev
          .filter((message) => message.id.startsWith('temp-queued-') && message.conversation_id === conversationId)
          .map((message) => [message.id, message] as const)
      );
      const reorderedQueuedMessages = queuedIdsInOrder
        .map((id) => queuedMap.get(id))
        .filter((message): message is Message => Boolean(message));
      const remainingMessages = prev.filter(
        (message) => !(message.id.startsWith('temp-queued-') && message.conversation_id === conversationId)
      );
      return [...remainingMessages, ...reorderedQueuedMessages];
    });

    const progressState = inProgressByConversationRef.current[conversationId];
    if (progressState?.queuedMessages) {
      const progressQueuedMap = new Map(progressState.queuedMessages.map((message) => [message.id, message] as const));
      const reorderedProgressQueued = queuedIdsInOrder
        .map((id) => progressQueuedMap.get(id))
        .filter((message): message is Message => Boolean(message));
      inProgressByConversationRef.current[conversationId] = {
        ...progressState,
        queuedMessages: reorderedProgressQueued.length > 0 ? reorderedProgressQueued : undefined,
      };
    }
  }, [currentConversation?.id]);

  // Handle keyboard submit
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // Handle paste — intercept image pastes from clipboard
  const handlePaste = useCallback((e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    const imageFiles: File[] = [];
    for (const item of items) {
      if (item.type.startsWith('image/')) {
        const file = item.getAsFile();
        if (file) imageFiles.push(file);
      }
    }
    if (imageFiles.length > 0) {
      e.preventDefault();
      handleAddImages(imageFiles);
    }
  }, []);

  // Process and add image files
  const handleAddImages = useCallback(async (files: File[]) => {
    const valid = files.filter((f) => {
      if (!SUPPORTED_IMAGE_TYPES.includes(f.type)) {
        toast.error(`Unsupported image type: ${f.type}`);
        return false;
      }
      if (f.size > MAX_IMAGE_SIZE) {
        toast.error(`Image too large (max 20MB): ${f.name}`);
        return false;
      }
      return true;
    });
    if (valid.length === 0) return;

    const newImages = await Promise.all(
      valid.map(async (file) => {
        const preview = URL.createObjectURL(file);
        const { data, mediaType } = await readImageAsBase64(file);
        return { id: crypto.randomUUID(), file, preview, data, mediaType };
      })
    );
    setAttachedImages((prev) => [...prev, ...newImages].slice(0, 5)); // max 5 images
  }, []);

  // Handle image file input change
  const handleImageChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (files && files.length > 0) handleAddImages(Array.from(files));
      e.target.value = '';
    },
    [handleAddImages]
  );

  // Process text files — mirrors handleAddImages pattern (start FileReader synchronously)
  const handleAddFiles = useCallback(async (files: File[]) => {
    const queued = files.map((file) => ({ id: crypto.randomUUID(), file }));
    if (queued.length > 0) setAttachedFiles((prev) => [...prev, ...queued]);
  }, []);

  // Handle text file input change — mirrors handleImageChange exactly
  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (files && files.length > 0) handleAddFiles(Array.from(files));
      e.target.value = '';
    },
    [handleAddFiles]
  );

  // Open skills explorer
  const handleViewSkills = () => {
    setSkillsExplorerOpen(true);
  };

  const configChips = useMemo(() => {
    const chips: { label: string; color: string }[] = [];
    if (defaultCatalog && defaultSchema) {
      chips.push({ label: `${defaultCatalog}.${defaultSchema}`, color: 'text-[var(--color-accent-primary)]' });
    }
    const cluster = clusters.find(c => c.cluster_id === selectedClusterId);
    if (cluster) {
      const isServerless = cluster.cluster_id === '__serverless__';
      chips.push({ label: isServerless ? 'Serverless Compute' : (cluster.cluster_name || 'Cluster'), color: cluster.state === 'RUNNING' ? 'text-[var(--color-success)]' : 'text-[var(--color-text-muted)]' });
    }
    const warehouse = warehouses.find(w => w.warehouse_id === selectedWarehouseId);
    if (warehouse) {
      chips.push({ label: warehouse.warehouse_name || 'Warehouse', color: warehouse.state === 'RUNNING' ? 'text-[var(--color-success)]' : 'text-[var(--color-text-muted)]' });
    }
    return chips;
  }, [defaultCatalog, defaultSchema, clusters, selectedClusterId, warehouses, selectedWarehouseId]);

  if (isLoading) {
    return (
      <MainLayout projectName={project?.name}>
        <div className="flex h-full items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-[var(--color-text-muted)]" />
        </div>
      </MainLayout>
    );
  }

  const queuedMessageIdPrefix = 'temp-queued-';
  const currentConversationId = currentConversation?.id ?? null;
  const isCurrentConversationStreaming =
    isStreaming && (
      activeStreamingConversationIdRef.current === currentConversationId
      || currentConversationId === null
    );
  const activeQueuedMessageId = activeQueuedMessageIdRef.current;
  const isQueuedRunActive =
    !!activeQueuedMessageId && (
      isCurrentConversationStreaming
      || (!isStreaming && !!streamingText)
    );
  const showStoppedSnapshot =
    !isCurrentConversationStreaming && !!streamingText && !isQueuedRunActive;
  const nonQueuedMessages = isCurrentConversationStreaming
    ? messages.filter((message) => !message.id.startsWith(queuedMessageIdPrefix))
    : messages;
  const queuedMessages = isCurrentConversationStreaming
    ? messages.filter((message) => message.id.startsWith(queuedMessageIdPrefix))
    : [];

  const sidebar = (
    <Sidebar
      conversations={conversations}
      currentConversationId={currentConversation?.id}
      streamingConversationIds={streamingConversationIds}
      onConversationSelect={handleSelectConversation}
      onNewConversation={handleNewConversation}
      onDeleteConversation={handleDeleteConversation}
      onViewSkills={handleViewSkills}
      isLoading={false}
    />
  );

  return (
    <MainLayout projectName={project?.name} sidebar={sidebar}>
      <div className="flex flex-1 flex-col h-full">
        {/* Chat Header */}
        <div className="flex h-14 items-center justify-between border-b border-[var(--color-border)]/60 px-6 bg-[var(--color-bg-secondary)]/20">
          <div className="flex items-center gap-3 min-w-0">
            <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-gradient-to-br from-[var(--color-accent-primary)]/10 to-[var(--color-accent-secondary)]/10 flex items-center justify-center">
              <Sparkles className="h-4 w-4 text-[var(--color-accent-primary)]" />
            </div>
            <h2 className="font-semibold text-[15px] text-[var(--color-text-heading)] truncate">
              {currentConversation?.title || 'New Chat'}
            </h2>
          </div>
          <div className="flex items-center gap-2.5">
            {/* Config summary chips */}
            <div className="hidden md:flex items-center gap-1.5">
              {configChips.map((chip, i) => (
                <span
                  key={i}
                  className={cn('text-[11px] font-medium px-2.5 py-1 rounded-lg bg-[var(--color-bg-secondary)] border border-[var(--color-border)]/40 truncate max-w-[160px]', chip.color)}
                >
                  {chip.label}
                </span>
              ))}
            </div>
            {/* Thinking toggle */}
            <button
              onClick={() => setVerbose((v) => !v)}
              className={cn(
                'flex items-center justify-center h-7 w-7 rounded-lg transition-all',
                verbose
                  ? 'bg-purple-500/10 text-purple-400 ring-2 ring-purple-500/20'
                  : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-bg-secondary)]'
              )}
              title={verbose ? 'Thinking ON — showing full agent trace' : 'Thinking OFF — click to show full agent trace'}
            >
              <Brain className="h-3.5 w-3.5" />
            </button>
            {/* Settings button */}
            <div className="relative" ref={configPanelRef}>
              <button
                onClick={() => setConfigPanelOpen(!configPanelOpen)}
                className={cn(
                  'flex items-center justify-center h-9 w-9 rounded-lg transition-all',
                  configPanelOpen
                    ? 'bg-[var(--color-accent-primary)]/10 text-[var(--color-accent-primary)] ring-2 ring-[var(--color-accent-primary)]/20'
                    : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-bg-secondary)]'
                )}
                title="Configuration"
              >
                <Settings2 className="h-4.5 w-4.5" />
              </button>
              <ConfigPanel
                isOpen={configPanelOpen}
                onClose={() => setConfigPanelOpen(false)}
                defaultCatalog={defaultCatalog}
                setDefaultCatalog={setDefaultCatalog}
                defaultSchema={defaultSchema}
                setDefaultSchema={setDefaultSchema}
                clusters={clusters}
                selectedClusterId={selectedClusterId}
                setSelectedClusterId={setSelectedClusterId}
                warehouses={warehouses}
                selectedWarehouseId={selectedWarehouseId}
                setSelectedWarehouseId={setSelectedWarehouseId}
                workspaceFolder={workspaceFolder}
                setWorkspaceFolder={setWorkspaceFolder}
                mlflowExperimentName={mlflowExperimentName}
                setMlflowExperimentName={setMlflowExperimentName}
                workspaceUrl={workspaceUrl}
              />
            </div>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-6">
          {messages.length === 0 && !streamingText ? (
            <div className="flex h-full items-center justify-center px-6">
              <div className="text-center max-w-xl w-full">
                <div className="relative inline-flex items-center justify-center w-20 h-20 mb-6">
                  <div className="absolute inset-0 rounded-3xl bg-gradient-to-br from-[var(--color-accent-primary)]/15 to-[var(--color-accent-secondary)]/10 blur-md" />
                  <div className="relative w-16 h-16 rounded-2xl bg-gradient-to-br from-[var(--color-accent-primary)]/10 to-[var(--color-accent-secondary)]/5 border border-[var(--color-accent-primary)]/10 flex items-center justify-center">
                    <Sparkles className="h-8 w-8 text-[var(--color-accent-primary)]" />
                  </div>
                </div>
                <h3 className="text-2xl font-bold text-[var(--color-text-heading)]">
                  What can I help you build?
                </h3>
                <p className="mt-3 text-sm text-[var(--color-text-muted)] max-w-md mx-auto leading-relaxed">
                  Build data pipelines, generate synthetic data, create dashboards, and more on Databricks.
                </p>

                <div className="mt-10 grid grid-cols-2 gap-3 text-left">
                  {[
                    { title: 'Generate synthetic data', desc: 'Realistic test datasets with customers, orders, and tickets', prompt: 'Generate synthetic customer data with orders and support tickets' },
                    { title: 'Build a data pipeline', desc: 'ETL workflows with medallion architecture', prompt: 'Create a data pipeline to transform raw data into bronze, silver, and gold layers' },
                    { title: 'Create a dashboard', desc: 'Interactive AI/BI visualizations', prompt: 'Create a dashboard to visualize customer metrics and trends' },
                    { title: 'Explore my data', desc: 'Tables, volumes, and resources in your project', prompt: 'What tables and data do I have in my project?' },
                  ].map((item) => (
                    <button
                      key={item.title}
                      onClick={() => setInput(item.prompt)}
                      className="group p-4 rounded-xl border border-[var(--color-border)]/50 bg-[var(--color-background)] hover:border-[var(--color-accent-primary)]/30 hover:shadow-lg hover:shadow-[var(--color-accent-primary)]/5 hover:-translate-y-0.5 text-left transition-all duration-200"
                    >
                      <span className="text-sm font-semibold text-[var(--color-text-heading)] group-hover:text-[var(--color-accent-primary)] transition-colors">{item.title}</span>
                      <p className="text-xs text-[var(--color-text-muted)] mt-1.5 leading-relaxed">{item.desc}</p>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="mx-auto max-w-5xl space-y-4">
              {(() => {
                const finishedTraces = verbose ? traceHistoryItems : [];
                let assistantTraceIdx = 0;
                const rows = nonQueuedMessages.map((message) => {
                  const traceForMessage =
                    message.role === 'assistant' ? finishedTraces[assistantTraceIdx++] : null;
                  const stats = message.role === 'assistant'
                    ? (message.duration_ms != null || message.input_tokens != null
                      ? message
                      : responseStatsRef.current[message.id] ?? null)
                    : null;
                  return (
                  <div key={`msg-row-${message.id}`}>
                    {traceForMessage && (
                      <div className="mb-4 flex justify-start">
                        <VerboseActivityLog items={traceForMessage} isStreaming={false} />
                      </div>
                    )}
                    <div
                      className={cn(
                        'flex',
                        message.role === 'user' ? 'justify-end' : 'justify-start'
                      )}
                    >
                      <div
                        className={cn(
                          'max-w-[85%] rounded-lg px-3 py-2 shadow-sm',
                          message.role === 'user'
                            ? 'bg-[var(--color-accent-primary)] text-white'
                            : 'bg-[var(--color-bg-secondary)] border border-[var(--color-border)]/50',
                          message.is_error && 'bg-[var(--color-error)]/10 border-[var(--color-error)]/30'
                        )}
                      >
                        {message.role === 'assistant' ? (
                          <div className="prose prose-xs max-w-none text-[var(--color-text-primary)] text-[13px] leading-relaxed">
                            <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                              {normalizeImagePathsToMarkdown(message.content)}
                            </ReactMarkdown>
                          </div>
                        ) : (
                          <p className="whitespace-pre-wrap text-[13px]">{message.content}</p>
                        )}
                      </div>
                    </div>
                    {message.role === 'user' && message.timestamp && (
                      <div className="flex justify-end mt-1">
                        <span className="text-[10px] text-[var(--color-text-muted)]">
                          {formatTimestamp(message.timestamp)}
                        </span>
                      </div>
                    )}
                    {message.role === 'assistant' && stats && (
                      <div className="flex justify-start mt-1 gap-2 flex-wrap">
                        {stats.duration_ms != null && (
                          <span className="text-[10px] text-[var(--color-text-muted)]">
                            {formatDuration(stats.duration_ms)}
                          </span>
                        )}
                        {(stats.input_tokens != null || stats.output_tokens != null) && (
                          <span className="text-[10px] text-[var(--color-text-muted)]">
                            {formatTokenCount(stats.input_tokens)} in / {formatTokenCount(stats.output_tokens)} out
                          </span>
                        )}
                        {stats.cache_read_tokens != null && stats.cache_read_tokens > 0 && (
                          <span className="text-[10px] text-[var(--color-text-muted)]">
                            {formatTokenCount(stats.cache_read_tokens)} cached
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                )});
                if (finishedTraces.length > 0 && nonQueuedMessages.filter((m) => m.role === 'assistant').length === 0) {
                  rows.push(
                    <div key="finished-trace-without-assistant" className="mb-4 flex justify-start">
                      <VerboseActivityLog items={finishedTraces[finishedTraces.length - 1]} isStreaming={false} />
                    </div>
                  );
                }
                return rows;
              })()}

              {/* Activity section - verbose shows full trace, non-verbose shows current tool only */}
              {(isCurrentConversationStreaming || showStoppedSnapshot) && !isQueuedRunActive && activityItems.length > 0 && (
                verbose
                  ? <div className="flex justify-start"><VerboseActivityLog items={activityItems} isStreaming={true} /></div>
                  : <ActivitySection items={activityItems} isStreaming={isCurrentConversationStreaming} />
              )}

              {/* Streaming response - show accumulated text as it arrives */}
              {(isCurrentConversationStreaming || showStoppedSnapshot) && !isQueuedRunActive && streamingText && (
                <div className="flex justify-start">
                  <div className="max-w-[85%] rounded-lg px-3 py-2 shadow-sm bg-[var(--color-bg-secondary)] border border-[var(--color-border)]/50">
                    <div className="prose prose-xs max-w-none text-[var(--color-text-primary)] text-[13px] leading-relaxed">
                      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                        {normalizeImagePathsToMarkdown(improveReadabilityForStreaming(streamingText))}
                      </ReactMarkdown>
                    </div>
                  </div>
                </div>
              )}

              {/* Fun loader with progress - shown while streaming before text arrives */}
              {isCurrentConversationStreaming && !isQueuedRunActive && !streamingText && (
                <div className="flex justify-start">
                  {isReconnecting ? (
                    <div className="flex items-center gap-2 text-sm text-[var(--color-text-muted)] py-2">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span>Reconnecting to agent...</span>
                    </div>
                  ) : (
                    <FunLoader todos={todos} className="py-2" />
                  )}
                </div>
              )}

              {/* Active queued item streaming output */}
              {isQueuedRunActive && (
                <div className="mt-2 space-y-2">
                  {activityItems.length > 0 && (
                    verbose
                      ? <div className="flex justify-start"><VerboseActivityLog items={activityItems} isStreaming={true} /></div>
                      : <ActivitySection items={activityItems} isStreaming={isCurrentConversationStreaming} />
                  )}
                  {streamingText ? (
                    <div className="flex justify-start">
                      <div className="max-w-[85%] rounded-lg px-3 py-2 shadow-sm bg-[var(--color-bg-secondary)] border border-[var(--color-border)]/50">
                        <div className="prose prose-xs max-w-none text-[var(--color-text-primary)] text-[13px] leading-relaxed">
                          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                            {normalizeImagePathsToMarkdown(improveReadabilityForStreaming(streamingText))}
                          </ReactMarkdown>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="flex justify-start">
                      {isReconnecting ? (
                        <div className="flex items-center gap-2 text-sm text-[var(--color-text-muted)] py-2">
                          <Loader2 className="h-4 w-4 animate-spin" />
                          <span>Reconnecting to agent...</span>
                        </div>
                      ) : (
                        <FunLoader todos={todos} className="py-2" />
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Queued messages panel */}
              {queuedMessages.length > 0 && (
                <div className="flex justify-start">
                  <div className="w-full max-w-[85%] rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/40 shadow-sm overflow-hidden">
                    <div className="px-3 py-2 border-b border-[var(--color-border)] text-sm font-medium text-[var(--color-text-heading)]">
                      {queuedMessages.length} Queued
                    </div>
                    <div className="divide-y divide-[var(--color-border)]">
                      {queuedMessages.map((message, index) => (
                        <div key={`queued-row-${message.id}`} className="group flex items-center gap-3 px-3 py-2.5">
                          <span className="h-4 w-4 rounded-full border border-[var(--color-text-muted)]/60 flex-shrink-0" />
                          <span className="flex-1 min-w-0 truncate text-[13px] text-[var(--color-text-primary)]">
                            {message.content.replace(/\s+/g, ' ').trim()}
                          </span>
                          <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                            <button
                              onClick={() => {
                                setInput(message.content);
                                handleRemoveQueuedMessage(message.id);
                                inputRef.current?.focus();
                              }}
                              className="p-1 rounded text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-bg-secondary)]"
                              title="Edit queued message"
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </button>
                            <button
                              onClick={() => handleMoveQueuedMessageUp(message.id)}
                              disabled={index === 0}
                              className="p-1 rounded text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-bg-secondary)] disabled:opacity-40 disabled:cursor-not-allowed"
                              title="Move up"
                            >
                              <ArrowUp className="h-3.5 w-3.5" />
                            </button>
                            <button
                              onClick={() => handleRemoveQueuedMessage(message.id)}
                              className="p-1 rounded text-[var(--color-text-muted)] hover:text-[var(--color-error)] hover:bg-[var(--color-bg-secondary)]"
                              title="Remove from queue"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="border-t border-[var(--color-border)] p-4 bg-[var(--color-bg-secondary)]/30">
          <div className="mx-auto max-w-5xl flex gap-3 items-end">
            <div className={cn(
              'flex-1',
              'rounded-xl border bg-[var(--color-background)] transition-all',
              isStreaming
                ? 'border-[var(--color-border)] opacity-80'
                : 'border-[var(--color-border)] focus-within:ring-2 focus-within:ring-[var(--color-accent-primary)]/50 focus-within:border-[var(--color-accent-primary)]'
            )}>
              {/* Attachment previews */}
              {(attachedImages.length > 0 || attachedFiles.length > 0) && (
                <div className="flex flex-wrap gap-2 px-4 pt-3">
                  {attachedImages.map((img) => (
                    <div
                      key={img.id}
                      className="relative group w-16 h-16 rounded-lg overflow-hidden border border-[var(--color-border)] bg-[var(--color-bg-secondary)] flex-shrink-0"
                    >
                      <img src={img.preview} alt="Attached" className="w-full h-full object-cover" />
                      <button
                        onClick={() => {
                          URL.revokeObjectURL(img.preview);
                          setAttachedImages((prev) => prev.filter((i) => i.id !== img.id));
                        }}
                        className="absolute top-0.5 right-0.5 h-4 w-4 rounded-full bg-black/60 text-white opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center"
                      >
                        <X className="h-2.5 w-2.5" />
                      </button>
                    </div>
                  ))}
                  {attachedFiles.map((file) => (
                    <div
                      key={file.id}
                      className="flex items-center gap-1.5 h-8 px-3 rounded-full border border-[var(--color-border)] bg-[var(--color-bg-secondary)] text-xs text-[var(--color-text-primary)] flex-shrink-0"
                    >
                      <FileText className="h-3 w-3 text-[var(--color-accent-primary)]" />
                      <span className="max-w-[120px] truncate">{file.file.name}</span>
                      <button
                        onClick={() => setAttachedFiles((prev) => prev.filter((f) => f.id !== file.id))}
                        className="ml-0.5 text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* Textarea */}
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                onPaste={handlePaste}
                placeholder="Ask Claude to help with code..."
                rows={1}
                className="w-full resize-none bg-transparent px-4 pt-3 pb-2 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:outline-none"
              />

              {/* Bottom toolbar — attach buttons only */}
              <div className="flex items-center gap-1 px-3 pb-2.5 pt-1">
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="flex items-center gap-1.5 h-7 px-2 rounded-md text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-bg-secondary)] border border-transparent hover:border-[var(--color-border)] transition-all text-xs"
                  title="Attach file"
                >
                  <Paperclip className="h-3.5 w-3.5" />
                  <span>File</span>
                </button>
                <button
                  onClick={() => imageInputRef.current?.click()}
                  className="flex items-center gap-1.5 h-7 px-2 rounded-md text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-bg-secondary)] border border-transparent hover:border-[var(--color-border)] transition-all text-xs"
                  title="Attach image"
                >
                  <ImageIcon className="h-3.5 w-3.5" />
                  <span>Image</span>
                </button>
              </div>
            </div>

            {/* Send / Stop button — Send takes priority when input has content (interrupt-and-resend).
                Stop is shown only when streaming with no pending input. */}
            {isStreaming && !input.trim() && attachedImages.length === 0 && attachedFiles.length === 0 ? (
              <Button
                onClick={handleStopGeneration}
                className="h-12 w-12 rounded-xl bg-[var(--color-destructive)] hover:bg-[var(--color-destructive)]/90 flex-shrink-0"
                title="Stop generation"
              >
                <Square className="h-5 w-5" />
              </Button>
            ) : (
              <Button
                onClick={handleSendMessage}
                disabled={!input.trim() && attachedImages.length === 0 && attachedFiles.length === 0}
                className="h-12 w-12 rounded-xl flex-shrink-0"
              >
                <Send className="h-5 w-5" />
              </Button>
            )}

            {/* Hidden file inputs */}
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              accept="text/*,.md,.py,.js,.ts,.jsx,.tsx,.json,.yaml,.yml,.csv,.sql,.sh,.env,.toml,.ini,.cfg,.xml,.html,.htm,.css,.scss,.less,.r,.R,.rmd,.scala,.java,.c,.cpp,.h,.hpp,.go,.rs,.rb,.php,.swift,.kt,.lua,.pl,.pm,.ps1,.bat,.cmd,.makefile,.dockerfile,.tf,.hcl,.conf,.properties,.log,.diff,.patch,.ipynb,.tsv,.graphql,.proto,.gradle,.sbt,.lock,.gitignore,.dockerignore,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-powerpoint,application/vnd.openxmlformats-officedocument.presentationml.presentation"
              onChange={handleFileChange}
            />
            <input
              ref={imageInputRef}
              type="file"
              multiple
              className="hidden"
              accept="image/jpeg,image/png,image/gif,image/webp"
              onChange={handleImageChange}
            />
          </div>
          <p className="mt-2 text-xs text-[var(--color-text-muted)]">
            Press Enter to send, Shift+Enter for new line
          </p>
        </div>
      </div>

      {/* Skills Explorer */}
      {skillsExplorerOpen && projectId && (
        <SkillsExplorer
          projectId={projectId}
          systemPromptParams={{
            clusterId: selectedClusterId,
            warehouseId: selectedWarehouseId,
            defaultCatalog,
            defaultSchema,
            workspaceFolder,
            projectId,
          }}
          customSystemPrompt={project?.custom_system_prompt ?? null}
          onSystemPromptChange={(prompt) => {
            setProject((prev) => prev ? { ...prev, custom_system_prompt: prompt } : prev);
          }}
          onClose={() => setSkillsExplorerOpen(false)}
        />
      )}
    </MainLayout>
  );
}
