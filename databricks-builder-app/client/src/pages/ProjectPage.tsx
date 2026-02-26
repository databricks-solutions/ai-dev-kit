import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useUser } from '@/contexts/UserContext';
import {
  ArrowUp,
  Check,
  ChevronDown,
  ClipboardCopy,
  ExternalLink,
  Loader2,
  Settings2,
  Square,
  Sparkles,
  Wrench,
  X,
} from 'lucide-react';
import { toast } from 'sonner';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { MainLayout } from '@/components/layout/MainLayout';
import { Sidebar } from '@/components/layout/Sidebar';
import { SkillsExplorer } from '@/components/SkillsExplorer';
import { FunLoader } from '@/components/FunLoader';
import {
  createConversation,
  deleteConversation,
  fetchClusters,
  fetchConversation,
  fetchConversations,
  fetchExecutions,
  fetchProject,
  fetchWarehouses,
  invokeAgent,
  reconnectToExecution,
  stopExecution,
} from '@/lib/api';
import type { Cluster, Conversation, Message, Project, Warehouse, TodoItem } from '@/lib/types';
import { cn } from '@/lib/utils';

// Combined activity item for display
interface ActivityItem {
  id: string;
  type: 'thinking' | 'tool_use' | 'tool_result';
  content: string;
  toolName?: string;
  toolInput?: Record<string, unknown>;
  isError?: boolean;
  timestamp: number;
}

// Databricks logo mark SVG
function DatabricksLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
      <path d="M18 2L3 10.5V12.5L18 21L33 12.5V10.5L18 2Z" fill="currentColor" />
      <path d="M18 24.5L3 16V18L18 27L33 18V16L18 24.5Z" fill="currentColor" />
      <path d="M18 30.5L3 22V24L18 33L33 24V22L18 30.5Z" fill="currentColor" opacity="0.7" />
    </svg>
  );
}

// Expandable tools list for a message
function ToolsUsedBadge({ tools }: { tools: string[] }) {
  const [expanded, setExpanded] = useState(false);

  if (tools.length === 0) return null;

  // Deduplicate and clean tool names
  const uniqueTools = [...new Set(tools.map(t => t.replace('mcp__databricks__', '').replace(/_/g, ' ')))];

  return (
    <div className="mt-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="inline-flex items-center gap-1.5 text-[11px] text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
      >
        <Wrench className="h-3 w-3" />
        <span>{uniqueTools.length} tool{uniqueTools.length !== 1 ? 's' : ''} used</span>
        <ChevronDown className={cn('h-3 w-3 transition-transform', expanded && 'rotate-180')} />
      </button>
      {expanded && (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {uniqueTools.map((tool, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-[var(--color-bg-secondary)] border border-[var(--color-border)]/40 text-[11px] text-[var(--color-text-muted)] capitalize"
            >
              <Wrench className="h-2.5 w-2.5" />
              {tool}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// Copy button for code blocks
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }}
      className="absolute top-2 right-2 p-1.5 rounded-md bg-[var(--color-bg-secondary)]/80 border border-[var(--color-border)]/50 text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-bg-secondary)] opacity-0 group-hover/code:opacity-100 transition-all"
      title={copied ? 'Copied!' : 'Copy code'}
    >
      {copied ? <Check className="h-3.5 w-3.5 text-[var(--color-success)]" /> : <ClipboardCopy className="h-3.5 w-3.5" />}
    </button>
  );
}

// Activity indicator - shows current tool with animated dots
function ActivitySection({
  items,
}: {
  items: ActivityItem[];
  isStreaming: boolean;
}) {
  if (items.length === 0) return null;

  const currentTool = [...items].reverse().find((item) => item.type === 'tool_use');
  if (!currentTool) return null;

  const toolName = currentTool.toolName?.replace('mcp__databricks__', '').replace(/_/g, ' ') || 'working';

  return (
    <div className="flex items-start gap-3 max-w-3xl">
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-[var(--color-accent-primary)] to-[var(--color-accent-secondary)] flex items-center justify-center shadow-sm mt-0.5">
        <DatabricksLogo className="h-4 w-4 text-white" />
      </div>
      <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-[var(--color-bg-secondary)]/60 border border-[var(--color-border)]/30">
        <Wrench className="h-3.5 w-3.5 text-[var(--color-accent-primary)] animate-pulse" />
        <span className="text-xs text-[var(--color-text-muted)] capitalize">
          {toolName}
        </span>
        <span className="flex gap-0.5">
          <span className="w-1 h-1 rounded-full bg-[var(--color-text-muted)] animate-bounce" style={{ animationDelay: '0ms' }} />
          <span className="w-1 h-1 rounded-full bg-[var(--color-text-muted)] animate-bounce" style={{ animationDelay: '150ms' }} />
          <span className="w-1 h-1 rounded-full bg-[var(--color-text-muted)] animate-bounce" style={{ animationDelay: '300ms' }} />
        </span>
      </div>
    </div>
  );
}

// Custom dropdown for cluster/warehouse selection with status indicators
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

// Configuration panel component
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
        {/* Catalog & Schema - stacked for more room */}
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

        {/* Cluster - custom dropdown */}
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

        {/* Warehouse - custom dropdown */}
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

        {/* Workspace Folder */}
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

        {/* MLflow Experiment */}
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

// Sanitize string for schema name: only a-z, 0-9, _ allowed
function sanitizeForSchema(str: string): string {
  return str.replace(/[^a-zA-Z0-9]/g, '_').toLowerCase();
}

// Convert email + project name to schema name: quentin.ambard@databricks.com + "My Project" -> quentin_ambard_my_project
function toSchemaName(email: string | null, projectName: string | null): string {
  if (!email) return '';
  const localPart = email.split('@')[0];
  const emailPart = sanitizeForSchema(localPart);
  if (!projectName) return emailPart;
  const projectPart = sanitizeForSchema(projectName);
  return `${emailPart}_${projectPart}`;
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
  const [defaultCatalog, setDefaultCatalog] = useState<string>('ai_dev_kit');
  const [defaultSchema, setDefaultSchema] = useState<string>('');
  const [workspaceFolder, setWorkspaceFolder] = useState<string>('');
  const [mlflowExperimentName, setMlflowExperimentName] = useState<string>('');
  const [skillsExplorerOpen, setSkillsExplorerOpen] = useState(false);
  const [activeExecutionId, setActiveExecutionId] = useState<string | null>(null);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [messageTools, setMessageTools] = useState<Record<string, string[]>>({});

  // Calculate default schema from user email + project name once available
  const userDefaultSchema = useMemo(() => toSchemaName(user, project?.name ?? null), [user, project?.name]);

  // Refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const reconnectAttemptedRef = useRef<string | null>(null); // Track which conversation we've checked
  const streamingToolsRef = useRef<string[]>([]); // Accumulate tools during current streaming response
  const streamingConversationIdRef = useRef<string | null>(null); // Which conversation owns the current stream

  // Load project and conversations
  useEffect(() => {
    if (!projectId) return;

    const loadData = async () => {
      try {
        setIsLoading(true);
        const [projectData, conversationsData, clustersData, warehousesData] = await Promise.all([
          fetchProject(projectId),
          fetchConversations(projectId),
          fetchClusters().catch(() => []), // Don't fail if clusters can't be loaded
          fetchWarehouses().catch(() => []), // Don't fail if warehouses can't be loaded
        ]);
        setProject(projectData);
        setConversations(conversationsData);
        setClusters(clustersData);
        setWarehouses(warehousesData);

        // Load first conversation if available
        if (conversationsData.length > 0) {
          const conv = await fetchConversation(projectId, conversationsData[0].id);
          setCurrentConversation(conv);
          setMessages(conv.messages || []);
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
          // Restore catalog/schema from conversation
          if (conv.default_catalog) {
            setDefaultCatalog(conv.default_catalog);
          }
          if (conv.default_schema) {
            setDefaultSchema(conv.default_schema);
          }
          // Restore workspace folder from conversation
          if (conv.workspace_folder) {
            setWorkspaceFolder(conv.workspace_folder);
          }
        } else {
          // No conversation yet, but still select first cluster/warehouse
          if (clustersData.length > 0) {
            setSelectedClusterId(clustersData[0].cluster_id);
          }
          if (warehousesData.length > 0) {
            setSelectedWarehouseId(warehousesData[0].warehouse_id);
          }
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
  }, [projectId, navigate]);

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
          setActiveExecutionId(active.id);

          // Create abort controller for reconnection
          abortControllerRef.current = new AbortController();

          let fullText = '';

          await reconnectToExecution({
            executionId: active.id,
            storedEvents: active.events,
            signal: abortControllerRef.current.signal,
            onEvent: (event) => {
              const type = event.type as string;

              if (type === 'text_delta') {
                const text = event.text as string;
                fullText += text;
                setStreamingText(fullText);
              } else if (type === 'text') {
                const text = event.text as string;
                if (text) {
                  if (fullText && !fullText.endsWith('\n') && !text.startsWith('\n')) {
                    fullText += '\n\n';
                  }
                  fullText += text;
                  setStreamingText(fullText);
                }
              } else if (type === 'tool_use') {
                setActivityItems((prev) => [
                  ...prev,
                  {
                    id: event.tool_id as string,
                    type: 'tool_use',
                    content: '',
                    toolName: event.tool_name as string,
                    toolInput: event.tool_input as Record<string, unknown>,
                    timestamp: Date.now(),
                  },
                ]);
              } else if (type === 'tool_result') {
                setActivityItems((prev) => [
                  ...prev,
                  {
                    id: `result-${event.tool_use_id}`,
                    type: 'tool_result',
                    content: typeof event.content === 'string' ? event.content : JSON.stringify(event.content),
                    isError: event.is_error as boolean,
                    timestamp: Date.now(),
                  },
                ]);
              } else if (type === 'todos') {
                const todoItems = event.todos as TodoItem[];
                if (todoItems) {
                  setTodos(todoItems);
                }
              } else if (type === 'error') {
                toast.error(event.error as string, { duration: 8000 });
              }
            },
            onError: (error) => {
              console.error('Reconnect error:', error);
              toast.error('Failed to reconnect to execution');
            },
            onDone: async () => {
              // Reload conversation to get the final messages from DB
              const conv = await fetchConversation(projectId, currentConversation.id);
              setCurrentConversation(conv);
              setMessages(conv.messages || []);
              setStreamingText('');
              setIsStreaming(false);
              setIsReconnecting(false);
              setActiveExecutionId(null);
              setActivityItems([]);
              setTodos([]);
            },
          });
        }
      } catch (error) {
        console.error('Failed to check for active executions:', error);
        // Don't show error toast - this is a background check
      }
    };

    checkAndReconnect();
  }, [projectId, currentConversation?.id, isLoading]);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingText, activityItems]);

  // Set default schema from user email once when first available
  const schemaDefaultApplied = useRef(false);
  useEffect(() => {
    if (userDefaultSchema && !schemaDefaultApplied.current && !defaultSchema) {
      setDefaultSchema(userDefaultSchema);
      schemaDefaultApplied.current = true;
    }
  }, [userDefaultSchema]);

  // Set default workspace folder from user email and project name once when first available
  const folderDefaultApplied = useRef(false);
  useEffect(() => {
    if (user && project?.name && !folderDefaultApplied.current && !workspaceFolder) {
      const projectFolder = sanitizeForSchema(project.name);
      setWorkspaceFolder(`/Workspace/Users/${user}/ai_dev_kit/${projectFolder}`);
      folderDefaultApplied.current = true;
    }
  }, [user, project?.name]);

  // Select a conversation
  const handleSelectConversation = async (conversationId: string) => {
    if (!projectId || currentConversation?.id === conversationId) return;

    // Reset reconnect tracking for the new conversation
    reconnectAttemptedRef.current = null;

    try {
      const conv = await fetchConversation(projectId, conversationId);
      setCurrentConversation(conv);
      setMessages(conv.messages || []);
      setActivityItems([]);
      // Restore cluster selection from conversation, or default to first cluster
      setSelectedClusterId(conv.cluster_id || (clusters.length > 0 ? clusters[0].cluster_id : undefined));
      // Restore warehouse selection from conversation, or default to first warehouse
      setSelectedWarehouseId(conv.warehouse_id || (warehouses.length > 0 ? warehouses[0].warehouse_id : undefined));
      // Restore catalog/schema from conversation, or use defaults
      setDefaultCatalog(conv.default_catalog || 'ai_dev_kit');
      setDefaultSchema(conv.default_schema || userDefaultSchema);
      // Restore workspace folder from conversation, or use default
      const projectFolder = project?.name ? sanitizeForSchema(project.name) : projectId;
      setWorkspaceFolder(conv.workspace_folder || (user ? `/Workspace/Users/${user}/ai_dev_kit/${projectFolder}` : ''));
    } catch (error) {
      console.error('Failed to load conversation:', error);
      toast.error('Failed to load conversation');
    }
  };

  // Create new conversation
  const handleNewConversation = async () => {
    if (!projectId) return;

    try {
      const conv = await createConversation(projectId);
      setConversations((prev) => [conv, ...prev]);
      setCurrentConversation(conv);
      setMessages([]);
      setActivityItems([]);
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

      if (currentConversation?.id === conversationId) {
        const remaining = conversations.filter((c) => c.id !== conversationId);
        if (remaining.length > 0) {
          const conv = await fetchConversation(projectId, remaining[0].id);
          setCurrentConversation(conv);
          setMessages(conv.messages || []);
        } else {
          setCurrentConversation(null);
          setMessages([]);
        }
        setActivityItems([]);
      }
      toast.success('Conversation deleted');
    } catch (error) {
      console.error('Failed to delete conversation:', error);
      toast.error('Failed to delete conversation');
    }
  };

  // Send message
  const handleSendMessage = useCallback(async () => {
    if (!projectId || !input.trim() || isStreaming) return;

    const userMessage = input.trim();
    setInput('');
    setIsStreaming(true);
    setStreamingText('');
    setActivityItems([]);
    setTodos([]);
    streamingToolsRef.current = [];
    streamingConversationIdRef.current = currentConversation?.id || null;

    // Add user message to UI immediately
    const tempUserMessage: Message = {
      id: `temp-${Date.now()}`,
      conversation_id: currentConversation?.id || '',
      role: 'user',
      content: userMessage,
      timestamp: new Date().toISOString(),
      is_error: false,
    };
    setMessages((prev) => [...prev, tempUserMessage]);

    // Create abort controller
    abortControllerRef.current = new AbortController();

    try {
      let conversationId = currentConversation?.id;
      let fullText = '';

      await invokeAgent({
        projectId,
        conversationId,
        message: userMessage,
        clusterId: selectedClusterId,
        defaultCatalog,
        defaultSchema,
        warehouseId: selectedWarehouseId,
        workspaceFolder,
        mlflowExperimentName: mlflowExperimentName || null,
        signal: abortControllerRef.current.signal,
        onExecutionId: (executionId) => setActiveExecutionId(executionId),
        onEvent: (event) => {
          const type = event.type as string;

          if (type === 'conversation.created') {
            conversationId = event.conversation_id as string;
            streamingConversationIdRef.current = conversationId;
            // Set currentConversation immediately so isStreamingHere stays true
            setCurrentConversation((prev) => prev ?? {
              id: conversationId,
              project_id: projectId,
              title: 'New Chat',
              created_at: new Date().toISOString(),
              conversation_count: 0,
            } as unknown as Conversation);
            fetchConversations(projectId).then(setConversations);
          } else if (type === 'text_delta') {
            // Token-by-token streaming - accumulate and display for live updates
            const text = event.text as string;
            fullText += text;
            console.log('[STREAM] text_delta received, fullText length:', fullText.length);
            setStreamingText(fullText);
          } else if (type === 'text') {
            // Complete text block from AssistantMessage - the authoritative final content
            // This event contains the COMPLETE text for this response segment
            // We always use it to ensure final responses after tool execution are captured
            const text = event.text as string;
            console.log('[STREAM] text event received, text length:', text?.length, 'current fullText length:', fullText.length);
            if (text) {
              // Append to fullText (there may be multiple text blocks in a conversation)
              // Add separator if needed
              if (fullText && !fullText.endsWith('\n') && !text.startsWith('\n')) {
                fullText += '\n\n';
              }
              fullText += text;
              console.log('[STREAM] fullText updated, new length:', fullText.length);
              setStreamingText(fullText);
            }
          } else if (type === 'thinking' || type === 'thinking_delta') {
            // Handle both complete thinking blocks and streaming thinking deltas
            const thinking = (event.thinking as string) || '';
            if (thinking) {
              setActivityItems((prev) => {
                // For deltas, append to the last thinking item if it exists
                if (type === 'thinking_delta' && prev.length > 0 && prev[prev.length - 1].type === 'thinking') {
                  const updated = [...prev];
                  updated[updated.length - 1] = {
                    ...updated[updated.length - 1],
                    content: updated[updated.length - 1].content + thinking,
                  };
                  return updated;
                }
                // For complete blocks or first delta, add new item
                return [
                  ...prev,
                  {
                    id: `thinking-${Date.now()}`,
                    type: 'thinking',
                    content: thinking,
                    timestamp: Date.now(),
                  },
                ];
              });
            }
          } else if (type === 'tool_use') {
            const toolName = event.tool_name as string;
            streamingToolsRef.current = [...streamingToolsRef.current, toolName];
            setActivityItems((prev) => [
              ...prev,
              {
                id: event.tool_id as string,
                type: 'tool_use',
                content: '',
                toolName,
                toolInput: event.tool_input as Record<string, unknown>,
                timestamp: Date.now(),
              },
            ]);
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

            setActivityItems((prev) => [
              ...prev,
              {
                id: `result-${event.tool_use_id}`,
                type: 'tool_result',
                content: typeof content === 'string' ? content : JSON.stringify(content),
                isError: event.is_error as boolean,
                timestamp: Date.now(),
              },
            ]);
          } else if (type === 'error') {
            let errorMsg = event.error as string;

            // Improve generic error messages
            if (errorMsg === 'Stream closed' || errorMsg.includes('Stream closed')) {
              errorMsg = 'Execution interrupted: The operation took too long or the connection was lost. Operations exceeding 50 seconds may be interrupted. Check backend logs for details.';
            }

            toast.error(errorMsg, {
              duration: 8000,
            });
          } else if (type === 'cancelled') {
            // Agent was cancelled by user - show a toast notification
            toast.info('Generation stopped');
          } else if (type === 'todos') {
            // Update todo list from agent
            const todoItems = event.todos as TodoItem[];
            if (todoItems) {
              setTodos(todoItems);
            }
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
          if (fullText) {
            const msgId = `msg-${Date.now()}`;
            const assistantMessage: Message = {
              id: msgId,
              conversation_id: conversationId || '',
              role: 'assistant',
              content: fullText,
              timestamp: new Date().toISOString(),
              is_error: false,
            };
            setMessages((prev) => [...prev, assistantMessage]);
            // Store tools used for this message
            if (streamingToolsRef.current.length > 0) {
              setMessageTools((prev) => ({ ...prev, [msgId]: streamingToolsRef.current }));
            }
          }
          setStreamingText('');
          setIsStreaming(false);
          setActiveExecutionId(null);
          setActivityItems([]);
          setTodos([]);
          streamingConversationIdRef.current = null;

          // Fetch full conversation to get updated title and messages
          if (conversationId) {
            const conv = await fetchConversation(projectId, conversationId);
            setCurrentConversation(conv);
            fetchConversations(projectId).then(setConversations);
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
      setIsStreaming(false);
    }
  }, [projectId, input, isStreaming, currentConversation?.id, selectedClusterId, defaultCatalog, defaultSchema, selectedWarehouseId, workspaceFolder, mlflowExperimentName]);

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
        const msgId = `msg-stopped-${Date.now()}`;
        setMessages((prev) => [
          ...prev,
          {
            id: msgId,
            conversation_id: '',
            role: 'assistant' as const,
            content: currentText,
            timestamp: new Date().toISOString(),
            is_error: false,
          },
        ]);
        if (streamingToolsRef.current.length > 0) {
          setMessageTools((prev) => ({ ...prev, [msgId]: streamingToolsRef.current }));
        }
      }
      return '';
    });
    setIsStreaming(false);
    setActiveExecutionId(null);
    setActivityItems([]);
    setTodos([]);
    streamingConversationIdRef.current = null;
  }, [activeExecutionId]);

  // Handle keyboard submit
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // Open skills explorer
  const handleViewSkills = () => {
    setSkillsExplorerOpen(true);
  };

  // Config panel state
  const [configPanelOpen, setConfigPanelOpen] = useState(false);
  const configPanelRef = useRef<HTMLDivElement>(null);

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

  // Auto-resize textarea
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
  };

  // Markdown components shared between messages and streaming
  const markdownComponents = useMemo(() => ({
    a: ({ href, children }: { href?: string; children?: React.ReactNode }) => (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-[var(--color-accent-primary)] underline decoration-[var(--color-accent-primary)]/30 hover:decoration-[var(--color-accent-primary)] hover:text-[var(--color-accent-secondary)] transition-colors"
      >
        {children}
      </a>
    ),
    pre: ({ children }: { children?: React.ReactNode }) => {
      // Extract text content from children for copy button
      const getTextContent = (node: React.ReactNode): string => {
        if (typeof node === 'string') return node;
        if (!node) return '';
        if (Array.isArray(node)) return node.map(getTextContent).join('');
        if (typeof node === 'object' && 'props' in (node as React.ReactElement)) {
          return getTextContent((node as React.ReactElement).props.children);
        }
        return '';
      };
      const text = getTextContent(children);
      return (
        <div className="relative group/code my-3">
          <pre className="!bg-[var(--color-bg-tertiary)] !rounded-lg !border !border-[var(--color-border)]/50 !p-4 overflow-x-auto">
            {children}
          </pre>
          <CopyButton text={text} />
        </div>
      );
    },
    code: ({ children, className }: { children?: React.ReactNode; className?: string }) => {
      // Inline code (no language class)
      if (!className) {
        return (
          <code className="px-1.5 py-0.5 rounded-md bg-[var(--color-bg-tertiary)] border border-[var(--color-border)]/30 text-[0.875em] font-mono">
            {children}
          </code>
        );
      }
      // Block code inside pre
      return <code className={cn(className, 'font-mono text-[12px]')}>{children}</code>;
    },
    table: ({ children }: { children?: React.ReactNode }) => (
      <div className="my-3 overflow-x-auto rounded-lg border border-[var(--color-border)]/50">
        <table className="w-full text-sm">{children}</table>
      </div>
    ),
    th: ({ children }: { children?: React.ReactNode }) => (
      <th className="px-3 py-2 text-left text-xs font-semibold text-[var(--color-text-heading)] bg-[var(--color-bg-secondary)] border-b border-[var(--color-border)]/50">
        {children}
      </th>
    ),
    td: ({ children }: { children?: React.ReactNode }) => (
      <td className="px-3 py-2 text-sm border-b border-[var(--color-border)]/30">
        {children}
      </td>
    ),
  }), []);

  // Config summary for header chips
  const configChips = useMemo(() => {
    const chips: { label: string; color: string }[] = [];
    if (defaultCatalog && defaultSchema) {
      chips.push({ label: `${defaultCatalog}.${defaultSchema}`, color: 'text-[var(--color-accent-primary)]' });
    }
    const cluster = clusters.find(c => c.cluster_id === selectedClusterId);
    if (cluster) {
      chips.push({ label: cluster.cluster_name || 'Cluster', color: cluster.state === 'RUNNING' ? 'text-[var(--color-success)]' : 'text-[var(--color-text-muted)]' });
    }
    const warehouse = warehouses.find(w => w.warehouse_id === selectedWarehouseId);
    if (warehouse) {
      chips.push({ label: warehouse.warehouse_name || 'Warehouse', color: warehouse.state === 'RUNNING' ? 'text-[var(--color-success)]' : 'text-[var(--color-text-muted)]' });
    }
    return chips;
  }, [defaultCatalog, defaultSchema, clusters, selectedClusterId, warehouses, selectedWarehouseId]);

  // Only show streaming UI if viewing the conversation that owns the stream
  const isStreamingHere = isStreaming && (
    streamingConversationIdRef.current === null || // New conversation (not yet created)
    streamingConversationIdRef.current === currentConversation?.id
  );

  if (isLoading) {
    return (
      <MainLayout projectName={project?.name}>
        <div className="flex h-full items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-[var(--color-text-muted)]" />
        </div>
      </MainLayout>
    );
  }

  const sidebar = (
    <Sidebar
      conversations={conversations}
      currentConversationId={currentConversation?.id}
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
        <div className="flex-1 overflow-y-auto">
          {messages.length === 0 && !(isStreamingHere && streamingText) ? (
            /* Empty State */
            <div className="flex h-full items-center justify-center px-6">
              <div className="text-center max-w-xl w-full">
                {/* Decorative gradient orb */}
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

                {/* Example prompts - 2x2 grid */}
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
            /* Message Thread */
            <div className="mx-auto max-w-3xl px-6 py-8 space-y-1">
              {messages.map((message) => (
                <div key={message.id}>
                  {message.role === 'assistant' ? (
                    /* Assistant message - left aligned with Databricks avatar */
                    <div className="flex items-start gap-3 group/msg mb-4">
                      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-[var(--color-accent-primary)] to-[var(--color-accent-secondary)] flex items-center justify-center shadow-sm shadow-[var(--color-accent-primary)]/20 mt-0.5">
                        <DatabricksLogo className="h-4 w-4 text-white" />
                      </div>
                      <div className={cn('flex-1 min-w-0', message.is_error && 'text-[var(--color-error)]')}>
                        <div className="mb-1 flex items-center gap-2">
                          <span className="text-xs font-semibold text-[var(--color-text-heading)]">Assistant</span>
                          {message.timestamp && (
                            <span className="text-[10px] text-[var(--color-text-muted)]/60 opacity-0 group-hover/msg:opacity-100 transition-opacity">
                              {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                            </span>
                          )}
                        </div>
                        <div className="prose prose-xs max-w-none text-[var(--color-text-primary)] text-[14px] leading-[1.7]">
                          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                            {message.content}
                          </ReactMarkdown>
                        </div>
                        <ToolsUsedBadge tools={messageTools[message.id] || []} />
                      </div>
                    </div>
                  ) : (
                    /* User message - right aligned like iMessage */
                    <div className="flex justify-end mb-4 group/msg">
                      <div className="max-w-[80%]">
                        <div className="mb-1 flex items-center justify-end gap-2">
                          {message.timestamp && (
                            <span className="text-[10px] text-[var(--color-text-muted)]/60 opacity-0 group-hover/msg:opacity-100 transition-opacity">
                              {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                            </span>
                          )}
                        </div>
                        <div className="rounded-2xl rounded-br-md bg-[var(--color-accent-primary)] text-white px-4 py-2.5 shadow-sm">
                          <p className="whitespace-pre-wrap text-[14px] leading-[1.6]">{message.content}</p>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ))}

              {/* Streaming response */}
              {isStreamingHere && streamingText && (
                <div className="flex items-start gap-3 mb-4">
                  <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-[var(--color-accent-primary)] to-[var(--color-accent-secondary)] flex items-center justify-center shadow-sm shadow-[var(--color-accent-primary)]/20 mt-0.5">
                    <DatabricksLogo className="h-4 w-4 text-white" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="mb-1">
                      <span className="text-xs font-semibold text-[var(--color-text-heading)]">
                        Assistant
                      </span>
                    </div>
                    <div className="prose prose-xs max-w-none text-[var(--color-text-primary)] text-[14px] leading-[1.7]">
                      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                        {streamingText}
                      </ReactMarkdown>
                    </div>
                  </div>
                </div>
              )}

              {/* Activity section */}
              {isStreamingHere && activityItems.length > 0 && (
                <ActivitySection items={activityItems} isStreaming={isStreamingHere} />
              )}

              {/* Loader */}
              {isStreamingHere && !streamingText && (
                <div className="flex items-start gap-3 mb-4">
                  <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-[var(--color-accent-primary)] to-[var(--color-accent-secondary)] flex items-center justify-center shadow-sm shadow-[var(--color-accent-primary)]/20 mt-0.5">
                    <DatabricksLogo className="h-4 w-4 text-white" />
                  </div>
                  <div className="flex-1">
                    <div className="mb-1">
                      <span className="text-xs font-semibold text-[var(--color-text-heading)]">
                        Assistant
                      </span>
                    </div>
                    {isReconnecting ? (
                      <div className="flex items-center gap-2 text-sm text-[var(--color-text-muted)] py-2">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        <span>Reconnecting to agent...</span>
                      </div>
                    ) : (
                      <FunLoader todos={todos} className="py-1" />
                    )}
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="px-6 pb-5 pt-3">
          <div className="mx-auto max-w-3xl">
            <div className="relative rounded-2xl border border-[var(--color-border)] bg-[var(--color-background)] shadow-sm shadow-black/[0.03] focus-within:border-[var(--color-accent-primary)]/40 focus-within:shadow-lg focus-within:shadow-[var(--color-accent-primary)]/[0.06] transition-all duration-300">
              <textarea
                ref={inputRef}
                value={input}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                placeholder="Message the assistant..."
                rows={1}
                className="w-full resize-none bg-transparent px-5 pt-4 pb-14 text-[14px] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)]/50 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
                style={{ maxHeight: 200 }}
                disabled={isStreamingHere}
              />
              <div className="absolute bottom-3 left-5 right-3 flex items-center justify-between">
                <span className="text-[11px] text-[var(--color-text-muted)]/40 select-none">
                  <kbd className="px-1.5 py-0.5 rounded border border-[var(--color-border)]/40 bg-[var(--color-bg-secondary)]/50 text-[10px] font-mono">Enter</kbd> to send
                </span>
                {isStreamingHere ? (
                  <button
                    onClick={handleStopGeneration}
                    className="flex items-center justify-center h-9 w-9 rounded-xl bg-[var(--color-destructive)] hover:bg-[var(--color-destructive)]/90 text-white transition-all shadow-sm hover:shadow-md"
                    title="Stop generation"
                  >
                    <Square className="h-3.5 w-3.5" />
                  </button>
                ) : (
                  <button
                    onClick={handleSendMessage}
                    disabled={!input.trim()}
                    className={cn(
                      'flex items-center justify-center h-9 w-9 rounded-xl transition-all',
                      input.trim()
                        ? 'bg-[var(--color-accent-primary)] hover:bg-[var(--color-accent-primary)]/90 text-white shadow-sm shadow-[var(--color-accent-primary)]/30 hover:shadow-md hover:shadow-[var(--color-accent-primary)]/40'
                        : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-muted)]/40 cursor-not-allowed'
                    )}
                    title="Send message"
                  >
                    <ArrowUp className="h-4.5 w-4.5" />
                  </button>
                )}
              </div>
            </div>
          </div>
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
          onClose={() => setSkillsExplorerOpen(false)}
        />
      )}
    </MainLayout>
  );
}
