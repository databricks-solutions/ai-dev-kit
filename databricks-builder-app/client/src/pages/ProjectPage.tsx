import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useUser } from '@/contexts/UserContext';
import {
  ChevronDown,
  ExternalLink,
  Loader2,
  MessageSquare,
  Send,
  Square,
  Wrench,
} from 'lucide-react';
import { toast } from 'sonner';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
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
  fetchProject,
  fetchWarehouses,
  invokeAgent,
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

// Minimal activity indicator - shows only current tool being executed
function ActivitySection({
  items,
}: {
  items: ActivityItem[];
  isStreaming: boolean;
}) {
  if (items.length === 0) return null;

  // Get the most recent tool_use item (current activity)
  const currentTool = [...items].reverse().find((item) => item.type === 'tool_use');

  if (!currentTool) return null;

  return (
    <div className="mb-2 flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
      <Wrench className="h-3 w-3 text-blue-500 animate-pulse" />
      <span className="truncate">
        Using {currentTool.toolName?.replace('mcp__databricks__', '')}...
      </span>
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
  const [clusterDropdownOpen, setClusterDropdownOpen] = useState(false);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [selectedWarehouseId, setSelectedWarehouseId] = useState<string | undefined>();
  const [warehouseDropdownOpen, setWarehouseDropdownOpen] = useState(false);
  const [defaultCatalog, setDefaultCatalog] = useState<string>('ai_dev_kit');
  const [defaultSchema, setDefaultSchema] = useState<string>('');
  const [workspaceFolder, setWorkspaceFolder] = useState<string>('');
  const [skillsExplorerOpen, setSkillsExplorerOpen] = useState(false);

  // Calculate default schema from user email + project name once available
  const userDefaultSchema = useMemo(() => toSchemaName(user, project?.name ?? null), [user, project?.name]);

  // Refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const clusterDropdownRef = useRef<HTMLDivElement>(null);
  const warehouseDropdownRef = useRef<HTMLDivElement>(null);

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

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingText, activityItems]);

  // Close dropdowns on outside click
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (clusterDropdownRef.current && !clusterDropdownRef.current.contains(event.target as Node)) {
        setClusterDropdownOpen(false);
      }
      if (warehouseDropdownRef.current && !warehouseDropdownRef.current.contains(event.target as Node)) {
        setWarehouseDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Set default schema from user email if not already set
  useEffect(() => {
    if (userDefaultSchema && !defaultSchema) {
      setDefaultSchema(userDefaultSchema);
    }
  }, [userDefaultSchema, defaultSchema]);

  // Set default workspace folder from user email and project name if not already set
  useEffect(() => {
    if (user && project?.name && !workspaceFolder) {
      const projectFolder = sanitizeForSchema(project.name);
      setWorkspaceFolder(`/Workspace/Users/${user}/ai_dev_kit/${projectFolder}`);
    }
  }, [user, project?.name, workspaceFolder]);

  // Select a conversation
  const handleSelectConversation = async (conversationId: string) => {
    if (!projectId || currentConversation?.id === conversationId) return;

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
      let receivedDeltas = false; // Track if we received streaming deltas

      await invokeAgent({
        projectId,
        conversationId,
        message: userMessage,
        clusterId: selectedClusterId,
        defaultCatalog,
        defaultSchema,
        warehouseId: selectedWarehouseId,
        workspaceFolder,
        signal: abortControllerRef.current.signal,
        onEvent: (event) => {
          const type = event.type as string;

          if (type === 'conversation.created') {
            conversationId = event.conversation_id as string;
            fetchConversations(projectId).then(setConversations);
          } else if (type === 'text_delta') {
            // Token-by-token streaming - accumulate and display
            const text = event.text as string;
            fullText += text;
            receivedDeltas = true;
            console.log('[STREAM] text_delta received, fullText length:', fullText.length);
            setStreamingText(fullText);
          } else if (type === 'text') {
            // Complete text block - only use if we haven't received deltas
            // When streaming is enabled, text_delta events contain the same content
            // so we skip 'text' events to avoid duplication
            console.log('[STREAM] text event received, receivedDeltas:', receivedDeltas, 'text length:', (event.text as string)?.length);
            if (!receivedDeltas) {
              const text = event.text as string;
              if (text) {
                // Add newline separator between text blocks for readability
                if (fullText && !fullText.endsWith('\n')) {
                  fullText += '\n\n';
                }
                fullText += text;
                console.log('[STREAM] text accumulated, fullText length:', fullText.length);
                setStreamingText(fullText);
              }
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
            const assistantMessage: Message = {
              id: `msg-${Date.now()}`,
              conversation_id: conversationId || '',
              role: 'assistant',
              content: fullText,
              timestamp: new Date().toISOString(),
              is_error: false,
            };
            setMessages((prev) => [...prev, assistantMessage]);
          }
          setStreamingText('');
          setIsStreaming(false);
          // Clear activity items after response is finalized - only show final answer
          setActivityItems([]);
          setTodos([]);

          if (conversationId && !currentConversation?.id) {
            const conv = await fetchConversation(projectId, conversationId);
            setCurrentConversation(conv);
          }
        },
      });
    } catch (error) {
      console.error('Failed to send message:', error);
      // Show the actual error message instead of generic text
      const errorMessage = error instanceof Error ? error.message : 'Failed to send message';
      toast.error(errorMessage, {
        duration: 8000, // Show error for 8 seconds
      });
      setIsStreaming(false);
    }
  }, [projectId, input, isStreaming, currentConversation?.id, selectedClusterId, defaultCatalog, defaultSchema, selectedWarehouseId, workspaceFolder]);

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
        {/* Chat Header - always show configuration controls */}
        <div className="flex h-14 items-center justify-between border-b border-[var(--color-border)] px-6 bg-[var(--color-bg-secondary)]/50">
          <h2 className="font-medium text-[var(--color-text-heading)] truncate max-w-[150px]">
            {currentConversation?.title || 'New Chat'}
          </h2>
          <div className="flex items-center gap-2">
              {/* Catalog.Schema Input */}
              <div className="flex items-center h-8 rounded-md border border-[var(--color-border)] bg-[var(--color-background)] focus-within:ring-2 focus-within:ring-[var(--color-accent-primary)]/50">
                <div className="flex items-center justify-center w-8 h-full border-r border-[var(--color-border)] bg-[var(--color-bg-secondary)]/50 rounded-l-md">
                  <svg className="w-4 h-4 text-[var(--color-text-muted)]" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path fill="currentColor" fillRule="evenodd" d="M8.646.368a.75.75 0 0 0-1.292 0l-3.25 5.5A.75.75 0 0 0 4.75 7h6.5a.75.75 0 0 0 .646-1.132zM8 2.224 9.936 5.5H6.064zM8.5 9.25a.75.75 0 0 1 .75-.75h5a.75.75 0 0 1 .75.75v5a.75.75 0 0 1-.75.75h-5a.75.75 0 0 1-.75-.75zM10 10v3.5h3.5V10zM1 11.75a3.25 3.25 0 1 1 6.5 0 3.25 3.25 0 0 1-6.5 0M4.25 10a1.75 1.75 0 1 0 0 3.5 1.75 1.75 0 0 0 0-3.5" clipRule="evenodd" />
                  </svg>
                </div>
                <input
                  type="text"
                  value={defaultCatalog}
                  onChange={(e) => setDefaultCatalog(e.target.value)}
                  placeholder="catalog"
                  className="h-full w-20 px-2 bg-transparent text-xs text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:outline-none"
                />
                <span className="text-[var(--color-text-muted)] text-xs">.</span>
                <input
                  type="text"
                  value={defaultSchema}
                  onChange={(e) => setDefaultSchema(e.target.value)}
                  placeholder="schema"
                  className="h-full w-32 px-2 bg-transparent text-xs text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:outline-none"
                />
              </div>
              {/* Open Catalog Button */}
              {workspaceUrl && defaultCatalog && defaultSchema && (
                <a
                  href={`${workspaceUrl}/explore/data/${defaultCatalog}/${defaultSchema}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-center h-8 w-8 rounded-md border border-[var(--color-border)] bg-[var(--color-background)] text-[var(--color-text-muted)] hover:bg-[var(--color-bg-secondary)] hover:text-[var(--color-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent-primary)]/50 transition-colors"
                  title="Open in Catalog Explorer"
                >
                  <ExternalLink className="h-4 w-4" />
                </a>
              )}
              {/* Cluster Dropdown */}
              {clusters.length > 0 && (
              <div className="relative" ref={clusterDropdownRef}>
                <button
                  onClick={() => setClusterDropdownOpen(!clusterDropdownOpen)}
                  className="flex items-center h-8 rounded-md border border-[var(--color-border)] bg-[var(--color-background)] text-xs text-[var(--color-text-primary)] hover:bg-[var(--color-bg-secondary)]/30 focus:outline-none focus:ring-2 focus:ring-[var(--color-accent-primary)]/50 transition-colors"
                  title="Cluster for code execution"
                >
                  <div className="flex items-center justify-center w-8 h-full border-r border-[var(--color-border)] bg-[var(--color-bg-secondary)]/50 rounded-l-md">
                    <svg className="w-4 h-4 text-[var(--color-text-muted)]" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <path fill="currentColor" fillRule="evenodd" d="M3.394 5.586a4.752 4.752 0 0 1 9.351.946 3.75 3.75 0 0 1-.668 7.464L12 14H4a.8.8 0 0 1-.179-.021 4.25 4.25 0 0 1-.427-8.393m.72 6.914h7.762a.8.8 0 0 1 .186-.008q.092.008.188.008a2.25 2.25 0 0 0 0-4.5H12a.75.75 0 0 1-.75-.75v-.5a3.25 3.25 0 0 0-6.475-.402.75.75 0 0 1-.698.657 2.75 2.75 0 0 0-.024 5.488z" clipRule="evenodd" />
                    </svg>
                  </div>
                  <div className="flex items-center gap-2 px-2">
                    {(() => {
                      const selected = clusters.find(c => c.cluster_id === selectedClusterId);
                      return selected ? (
                        <>
                          <span className={cn(
                            'w-2 h-2 rounded-full',
                            selected.state === 'RUNNING' ? 'bg-green-500' : 'bg-gray-400'
                          )} />
                          <span className="max-w-[100px] truncate">{selected.cluster_name}</span>
                        </>
                      ) : (
                        <span className="text-[var(--color-text-muted)]">Cluster...</span>
                      );
                    })()}
                    <ChevronDown className={cn('w-3 h-3 transition-transform', clusterDropdownOpen && 'rotate-180')} />
                  </div>
                </button>
                {clusterDropdownOpen && (
                  <div className="absolute right-0 top-full mt-1 w-72 max-h-64 overflow-y-auto rounded-md border border-[var(--color-border)] bg-[var(--color-background)] shadow-lg z-50">
                    {clusters.map((cluster) => (
                      <button
                        key={cluster.cluster_id}
                        onClick={() => {
                          setSelectedClusterId(cluster.cluster_id);
                          setClusterDropdownOpen(false);
                        }}
                        className={cn(
                          'w-full flex items-center gap-2 px-3 py-2 text-xs text-left hover:bg-[var(--color-bg-secondary)] transition-colors',
                          selectedClusterId === cluster.cluster_id && 'bg-[var(--color-bg-secondary)]'
                        )}
                      >
                        <span className={cn(
                          'w-2 h-2 rounded-full flex-shrink-0',
                          cluster.state === 'RUNNING' ? 'bg-green-500' : 'bg-gray-400'
                        )} />
                        <span className="truncate text-[var(--color-text-primary)]">{cluster.cluster_name}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
              )}
              {/* Warehouse Dropdown */}
              {warehouses.length > 0 && (
              <div className="relative" ref={warehouseDropdownRef}>
                <button
                  onClick={() => setWarehouseDropdownOpen(!warehouseDropdownOpen)}
                  className="flex items-center h-8 rounded-md border border-[var(--color-border)] bg-[var(--color-background)] text-xs text-[var(--color-text-primary)] hover:bg-[var(--color-bg-secondary)]/30 focus:outline-none focus:ring-2 focus:ring-[var(--color-accent-primary)]/50 transition-colors"
                  title="SQL Warehouse for queries"
                >
                  <div className="flex items-center justify-center w-8 h-full border-r border-[var(--color-border)] bg-[var(--color-bg-secondary)]/50 rounded-l-md">
                    <svg className="w-4 h-4 text-[var(--color-text-muted)]" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <path d="M13 13.75C13 14.5784 11.6569 15.25 10 15.25C8.34315 15.25 7 14.5784 7 13.75" stroke="currentColor" strokeWidth="1.5" />
                      <path d="M3.39373 5.58639C3.91293 3.52534 5.77786 2 8 2C10.5504 2 12.6314 4.01005 12.7451 6.5324C14.1591 6.7189 15.3247 7.69323 15.7866 9H14.1211C13.7175 8.39701 13.0301 8 12.25 8H12C11.5858 8 11.25 7.66421 11.25 7.25V6.75C11.25 4.95507 9.79493 3.5 8 3.5C6.34131 3.5 4.97186 4.74324 4.7745 6.34833C4.73041 6.70685 4.43704 6.98301 4.07651 7.00536C2.63892 7.09448 1.5 8.28952 1.5 9.75C1.5 11.1845 2.59873 12.3629 4 12.4888V14C3.93845 14 3.87864 13.9926 3.8214 13.9786C1.67511 13.7633 0 11.9526 0 9.75C0 7.69604 1.45669 5.98279 3.39373 5.58639Z" fill="currentColor" />
                      <path d="M7 11.5V13.7769" stroke="currentColor" strokeWidth="1.5" />
                      <path d="M13 11.5V13.7769" stroke="currentColor" strokeWidth="1.5" />
                      <ellipse cx="10" cy="11.5" rx="3" ry="1.5" stroke="currentColor" strokeWidth="1.5" />
                    </svg>
                  </div>
                  <div className="flex items-center gap-2 px-2">
                    {(() => {
                      const selected = warehouses.find(w => w.warehouse_id === selectedWarehouseId);
                      return selected ? (
                        <>
                          <span className={cn(
                            'w-2 h-2 rounded-full',
                            selected.state === 'RUNNING' ? 'bg-green-500' : 'bg-gray-400'
                          )} />
                          <span className="max-w-[100px] truncate">{selected.warehouse_name}</span>
                        </>
                      ) : (
                        <span className="text-[var(--color-text-muted)]">Warehouse...</span>
                      );
                    })()}
                    <ChevronDown className={cn('w-3 h-3 transition-transform', warehouseDropdownOpen && 'rotate-180')} />
                  </div>
                </button>
                {warehouseDropdownOpen && (
                  <div className="absolute right-0 top-full mt-1 w-72 max-h-64 overflow-y-auto rounded-md border border-[var(--color-border)] bg-[var(--color-background)] shadow-lg z-50">
                    {warehouses.map((warehouse) => (
                      <button
                        key={warehouse.warehouse_id}
                        onClick={() => {
                          setSelectedWarehouseId(warehouse.warehouse_id);
                          setWarehouseDropdownOpen(false);
                        }}
                        className={cn(
                          'w-full flex items-center gap-2 px-3 py-2 text-xs text-left hover:bg-[var(--color-bg-secondary)] transition-colors',
                          selectedWarehouseId === warehouse.warehouse_id && 'bg-[var(--color-bg-secondary)]'
                        )}
                      >
                        <span className={cn(
                          'w-2 h-2 rounded-full flex-shrink-0',
                          warehouse.state === 'RUNNING' ? 'bg-green-500' : 'bg-gray-400'
                        )} />
                        <span className="truncate text-[var(--color-text-primary)]">{warehouse.warehouse_name}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
              )}
              {/* Workspace Folder Input */}
              <div className="flex items-center h-8 rounded-md border border-[var(--color-border)] bg-[var(--color-background)] focus-within:ring-2 focus-within:ring-[var(--color-accent-primary)]/50">
                <div className="flex items-center justify-center w-8 h-full border-r border-[var(--color-border)] bg-[var(--color-bg-secondary)]/50 rounded-l-md">
                  <svg className="w-4 h-4 text-[var(--color-text-muted)]" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path fill="currentColor" fillRule="evenodd" d="M3 1.75A.75.75 0 0 1 3.75 1h10.5a.75.75 0 0 1 .75.75v12.5a.75.75 0 0 1-.75.75H3.75a.75.75 0 0 1-.75-.75V12.5H1V11h2V8.75H1v-1.5h2V5H1V3.5h2zm1.5.75v11H6v-11zm3 0v11h6v-11z" clipRule="evenodd" />
                  </svg>
                </div>
                <input
                  type="text"
                  value={workspaceFolder}
                  onChange={(e) => setWorkspaceFolder(e.target.value)}
                  placeholder="/Workspace/Users/..."
                  className="h-full w-[500px] px-2 bg-transparent text-xs text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:outline-none"
                  title="Workspace working folder for uploading files and pipelines"
                />
              </div>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-6">
          {messages.length === 0 && !streamingText ? (
            <div className="flex h-full items-center justify-center">
              <div className="text-center max-w-2xl">
                <MessageSquare className="mx-auto h-12 w-12 text-[var(--color-text-muted)]/40" />
                <h3 className="mt-4 text-lg font-medium text-[var(--color-text-heading)]">
                  What can I help you build?
                </h3>
                <p className="mt-2 text-sm text-[var(--color-text-muted)]">
                  I can help you build data pipelines, generate synthetic data, create dashboards, and more on Databricks.
                </p>

                {/* Example prompts */}
                <div className="mt-6 grid gap-2 text-left">
                  <button
                    onClick={() => setInput('Generate synthetic customer data with orders and support tickets')}
                    className="p-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/30 hover:bg-[var(--color-bg-secondary)] text-left transition-colors"
                  >
                    <span className="text-sm font-medium text-[var(--color-text-primary)]">Generate synthetic data</span>
                    <p className="text-xs text-[var(--color-text-muted)] mt-0.5">Create realistic test datasets with customers, orders, and tickets</p>
                  </button>
                  <button
                    onClick={() => setInput('Create a data pipeline to transform raw data into bronze, silver, and gold layers')}
                    className="p-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/30 hover:bg-[var(--color-bg-secondary)] text-left transition-colors"
                  >
                    <span className="text-sm font-medium text-[var(--color-text-primary)]">Build a data pipeline</span>
                    <p className="text-xs text-[var(--color-text-muted)] mt-0.5">Create ETL workflows with bronze/silver/gold medallion architecture</p>
                  </button>
                  <button
                    onClick={() => setInput('Create a dashboard to visualize customer metrics and trends')}
                    className="p-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/30 hover:bg-[var(--color-bg-secondary)] text-left transition-colors"
                  >
                    <span className="text-sm font-medium text-[var(--color-text-primary)]">Create a dashboard</span>
                    <p className="text-xs text-[var(--color-text-muted)] mt-0.5">Build interactive visualizations with AI/BI dashboards</p>
                  </button>
                  <button
                    onClick={() => setInput('What tables and data do I have in my project?')}
                    className="p-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/30 hover:bg-[var(--color-bg-secondary)] text-left transition-colors"
                  >
                    <span className="text-sm font-medium text-[var(--color-text-primary)]">Explore my data</span>
                    <p className="text-xs text-[var(--color-text-muted)] mt-0.5">See what tables, volumes, and resources exist in your project</p>
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="mx-auto max-w-5xl space-y-4">
              {messages.map((message) => (
                <div
                  key={message.id}
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
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          components={{
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
                          }}
                        >
                          {message.content}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      <p className="whitespace-pre-wrap text-[13px]">{message.content}</p>
                    )}
                  </div>
                </div>
              ))}

              {/* Streaming response - show accumulated text as it arrives */}
              {isStreaming && streamingText && (
                <div className="flex justify-start">
                  <div className="max-w-[85%] rounded-lg px-3 py-2 shadow-sm bg-[var(--color-bg-secondary)] border border-[var(--color-border)]/50">
                    <div className="prose prose-xs max-w-none text-[var(--color-text-primary)] text-[13px] leading-relaxed">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
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
                        }}
                      >
                        {streamingText}
                      </ReactMarkdown>
                    </div>
                  </div>
                </div>
              )}

              {/* Activity section (thinking, tools) - shown below streaming text */}
              {activityItems.length > 0 && (
                <ActivitySection items={activityItems} isStreaming={isStreaming} />
              )}

              {/* Fun loader with progress - shown while streaming before text arrives */}
              {isStreaming && !streamingText && (
                <div className="flex justify-start">
                  <FunLoader todos={todos} className="py-2" />
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="border-t border-[var(--color-border)] p-4 bg-[var(--color-bg-secondary)]/30">
          <div className="mx-auto max-w-5xl">
            <div className="flex gap-3">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask Claude to help with code..."
                rows={1}
                className="flex-1 resize-none rounded-xl border border-[var(--color-border)] bg-[var(--color-background)] px-4 py-3 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent-primary)]/50 focus:border-[var(--color-accent-primary)] disabled:cursor-not-allowed disabled:opacity-50 transition-all"
                disabled={isStreaming}
              />
              {isStreaming ? (
                <Button
                  onClick={() => abortControllerRef.current?.abort()}
                  className="h-12 w-12 rounded-xl bg-red-600 hover:bg-red-700"
                  title="Stop generation"
                >
                  <Square className="h-5 w-5" />
                </Button>
              ) : (
                <Button
                  onClick={handleSendMessage}
                  disabled={!input.trim()}
                  className="h-12 w-12 rounded-xl"
                >
                  <Send className="h-5 w-5" />
                </Button>
              )}
            </div>
            <p className="mt-2 text-xs text-[var(--color-text-muted)]">
              Press Enter to send, Shift+Enter for new line
            </p>
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
          }}
          onClose={() => setSkillsExplorerOpen(false)}
        />
      )}
    </MainLayout>
  );
}
