import { useCallback, useEffect, useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Code,
  Eye,
  File,
  FileText,
  Folder,
  FolderOpen,
  Loader2,
  RefreshCw,
  Sparkles,
  X,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import {
  fetchAvailableSkills,
  fetchSkillFile,
  fetchSkillsTree,
  fetchSystemPrompt,
  reloadProjectSkills,
  updateEnabledSkills,
  type FetchSystemPromptParams,
  type SkillTreeNode,
} from '@/lib/api';
import type { AvailableSkill } from '@/lib/types';

interface TreeNodeProps {
  node: SkillTreeNode;
  level: number;
  selectedPath: string | null;
  expandedPaths: Set<string>;
  onSelect: (path: string) => void;
  onToggle: (path: string) => void;
}

function TreeNode({
  node,
  level,
  selectedPath,
  expandedPaths,
  onSelect,
  onToggle,
}: TreeNodeProps) {
  const isExpanded = expandedPaths.has(node.path);
  const isSelected = selectedPath === node.path;
  const isDirectory = node.type === 'directory';
  const isMarkdown = node.name.endsWith('.md');

  const handleClick = () => {
    if (isDirectory) {
      onToggle(node.path);
    } else {
      onSelect(node.path);
    }
  };

  return (
    <div>
      <button
        onClick={handleClick}
        className={cn(
          'flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-left text-xs transition-colors',
          isSelected
            ? 'bg-[var(--color-accent-primary)]/10 text-[var(--color-accent-primary)]'
            : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] hover:text-[var(--color-text-primary)]'
        )}
        style={{ paddingLeft: `${level * 12 + 8}px` }}
      >
        {isDirectory ? (
          <>
            {isExpanded ? (
              <ChevronDown className="h-3 w-3 flex-shrink-0 text-[var(--color-text-muted)]" />
            ) : (
              <ChevronRight className="h-3 w-3 flex-shrink-0 text-[var(--color-text-muted)]" />
            )}
            {isExpanded ? (
              <FolderOpen className="h-3.5 w-3.5 flex-shrink-0 text-[var(--color-warning)]" />
            ) : (
              <Folder className="h-3.5 w-3.5 flex-shrink-0 text-[var(--color-warning)]" />
            )}
          </>
        ) : (
          <>
            <span className="w-3" />
            {isMarkdown ? (
              <FileText className="h-3.5 w-3.5 flex-shrink-0 text-[var(--color-accent-secondary)]" />
            ) : (
              <File className="h-3.5 w-3.5 flex-shrink-0 text-[var(--color-text-muted)]" />
            )}
          </>
        )}
        <span className="truncate">{node.name}</span>
      </button>

      {isDirectory && isExpanded && node.children && (
        <div>
          {node.children.map((child) => (
            <TreeNode
              key={child.path}
              node={child}
              level={level + 1}
              selectedPath={selectedPath}
              expandedPaths={expandedPaths}
              onSelect={onSelect}
              onToggle={onToggle}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// Toggle switch component
function Toggle({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={(e) => {
        e.stopPropagation();
        onChange(!checked);
      }}
      className={cn(
        'relative inline-flex h-4 w-7 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-[var(--color-accent-primary)]/50 focus:ring-offset-1',
        checked ? 'bg-[var(--color-accent-primary)]' : 'bg-[var(--color-text-muted)]/50',
        disabled && 'opacity-50 cursor-not-allowed'
      )}
    >
      <span
        className={cn(
          'pointer-events-none inline-block h-3 w-3 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out',
          checked ? 'translate-x-3' : 'translate-x-0'
        )}
      />
    </button>
  );
}

interface SkillsExplorerProps {
  projectId: string;
  systemPromptParams: FetchSystemPromptParams;
  onClose: () => void;
}

export function SkillsExplorer({
  projectId,
  systemPromptParams,
  onClose,
}: SkillsExplorerProps) {
  const [tree, setTree] = useState<SkillTreeNode[]>([]);
  const [isLoadingTree, setIsLoadingTree] = useState(true);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [selectedType, setSelectedType] = useState<'system_prompt' | 'skill'>('system_prompt');
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set());
  const [content, setContent] = useState<string>('');
  const [isLoadingContent, setIsLoadingContent] = useState(false);
  const [showRawCode, setShowRawCode] = useState(false);
  const [isReloading, setIsReloading] = useState(false);

  // Skill management state
  const [availableSkills, setAvailableSkills] = useState<AvailableSkill[]>([]);
  const [isUpdatingSkills, setIsUpdatingSkills] = useState(false);

  // Load skills tree and available skills
  useEffect(() => {
    const loadData = async () => {
      try {
        setIsLoadingTree(true);
        const [treeData, skillsData] = await Promise.all([
          fetchSkillsTree(projectId),
          fetchAvailableSkills(projectId),
        ]);
        setTree(treeData);
        setAvailableSkills(skillsData.skills);

        // Auto-expand first level directories
        const initialExpanded = new Set<string>();
        treeData.forEach((node) => {
          if (node.type === 'directory') {
            initialExpanded.add(node.path);
          }
        });
        setExpandedPaths(initialExpanded);
      } catch (error) {
        console.error('Failed to load skills data:', error);
      } finally {
        setIsLoadingTree(false);
      }
    };

    loadData();
  }, [projectId]);

  // Load system prompt by default
  useEffect(() => {
    const loadSystemPrompt = async () => {
      try {
        setIsLoadingContent(true);
        const prompt = await fetchSystemPrompt(systemPromptParams);
        setContent(prompt);
        setSelectedType('system_prompt');
      } catch (error) {
        console.error('Failed to load system prompt:', error);
        setContent('Error loading system prompt');
      } finally {
        setIsLoadingContent(false);
      }
    };

    loadSystemPrompt();
  }, [systemPromptParams]);

  const handleSelectSystemPrompt = useCallback(async () => {
    setSelectedPath(null);
    setSelectedType('system_prompt');
    setIsLoadingContent(true);
    try {
      const prompt = await fetchSystemPrompt(systemPromptParams);
      setContent(prompt);
    } catch (error) {
      console.error('Failed to load system prompt:', error);
      setContent('Error loading system prompt');
    } finally {
      setIsLoadingContent(false);
    }
  }, [systemPromptParams]);

  const handleSelectSkill = useCallback(
    async (path: string) => {
      setSelectedPath(path);
      setSelectedType('skill');
      setIsLoadingContent(true);
      try {
        const file = await fetchSkillFile(projectId, path);
        setContent(file.content);
      } catch (error) {
        console.error('Failed to load skill file:', error);
        setContent('Error loading file');
      } finally {
        setIsLoadingContent(false);
      }
    },
    [projectId]
  );

  const handleToggle = useCallback((path: string) => {
    setExpandedPaths((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  }, []);

  const handleReloadSkills = useCallback(async () => {
    setIsReloading(true);
    try {
      await reloadProjectSkills(projectId);
      // Reload the tree and available skills after refresh
      const [treeData, skillsData] = await Promise.all([
        fetchSkillsTree(projectId),
        fetchAvailableSkills(projectId),
      ]);
      setTree(treeData);
      setAvailableSkills(skillsData.skills);
      // Auto-expand first level directories
      const initialExpanded = new Set<string>();
      treeData.forEach((node) => {
        if (node.type === 'directory') {
          initialExpanded.add(node.path);
        }
      });
      setExpandedPaths(initialExpanded);
      // Reset selection to system prompt
      setSelectedPath(null);
      setSelectedType('system_prompt');
      toast.success('Skills reloaded');
    } catch (error) {
      console.error('Failed to reload skills:', error);
      toast.error('Failed to reload skills');
    } finally {
      setIsReloading(false);
    }
  }, [projectId]);

  // Toggle a single skill
  const handleToggleSkill = useCallback(
    async (skillName: string, enabled: boolean) => {
      setIsUpdatingSkills(true);
      try {
        // Calculate new enabled list
        const allEnabled = availableSkills.every((s) => s.enabled) && availableSkills.some((s) => s.name !== skillName);
        let newEnabledList: string[] | null;

        if (enabled) {
          // Enabling a skill
          const currentEnabled = availableSkills.filter((s) => s.enabled).map((s) => s.name);
          const newEnabled = [...currentEnabled, skillName];
          // If all skills would be enabled, set to null (all)
          if (newEnabled.length >= availableSkills.length) {
            newEnabledList = null;
          } else {
            newEnabledList = newEnabled;
          }
        } else {
          // Disabling a skill
          const currentEnabled = availableSkills.filter((s) => s.enabled).map((s) => s.name);
          newEnabledList = currentEnabled.filter((n) => n !== skillName);
          if (newEnabledList.length === 0) {
            toast.error('At least one skill must be enabled');
            setIsUpdatingSkills(false);
            return;
          }
        }

        await updateEnabledSkills(projectId, newEnabledList);

        // Update local state
        setAvailableSkills((prev) =>
          prev.map((s) => (s.name === skillName ? { ...s, enabled } : s))
        );

        // Refresh the tree to reflect filesystem changes
        const treeData = await fetchSkillsTree(projectId);
        setTree(treeData);

        // Refresh system prompt if currently viewing it (so disabled skills disappear)
        if (selectedType === 'system_prompt') {
          const prompt = await fetchSystemPrompt(systemPromptParams);
          setContent(prompt);
        }
      } catch (error) {
        console.error('Failed to toggle skill:', error);
        toast.error('Failed to update skill');
      } finally {
        setIsUpdatingSkills(false);
      }
    },
    [projectId, availableSkills, selectedType, systemPromptParams]
  );

  // Enable or disable all skills
  const handleToggleAll = useCallback(
    async (enableAll: boolean) => {
      setIsUpdatingSkills(true);
      try {
        if (enableAll) {
          await updateEnabledSkills(projectId, null);
          setAvailableSkills((prev) => prev.map((s) => ({ ...s, enabled: true })));
        } else {
          // Disable all except first skill (must have at least one)
          const firstSkill = availableSkills[0]?.name;
          if (!firstSkill) return;
          await updateEnabledSkills(projectId, [firstSkill]);
          setAvailableSkills((prev) =>
            prev.map((s) => ({ ...s, enabled: s.name === firstSkill }))
          );
        }

        // Refresh tree
        const treeData = await fetchSkillsTree(projectId);
        setTree(treeData);

        // Refresh system prompt if currently viewing it
        if (selectedType === 'system_prompt') {
          const prompt = await fetchSystemPrompt(systemPromptParams);
          setContent(prompt);
        }

        toast.success(enableAll ? 'All skills enabled' : 'Skills minimized');
      } catch (error) {
        console.error('Failed to toggle all skills:', error);
        toast.error('Failed to update skills');
      } finally {
        setIsUpdatingSkills(false);
      }
    },
    [projectId, availableSkills, selectedType, systemPromptParams]
  );

  const enabledCount = availableSkills.filter((s) => s.enabled).length;
  const totalCount = availableSkills.length;
  const isMarkdownFile = selectedType === 'system_prompt' || selectedPath?.endsWith('.md');

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Content */}
      <div className="relative z-10 flex w-full h-full m-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-background)] shadow-2xl overflow-hidden">
        {/* Left sidebar - Navigation */}
        <div className="w-72 flex-shrink-0 border-r border-[var(--color-border)] bg-[var(--color-bg-secondary)]/30 flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border)]">
            <h2 className="text-sm font-semibold text-[var(--color-text-heading)]">
              Skills & Docs
            </h2>
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-[var(--color-accent-primary)]/10 text-[var(--color-accent-primary)]">
              {enabledCount}/{totalCount}
            </span>
          </div>

          {/* Navigation content */}
          <div className="flex-1 overflow-y-auto p-2">
            {/* System Prompt */}
            <button
              onClick={handleSelectSystemPrompt}
              className={cn(
                'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors mb-2',
                selectedType === 'system_prompt'
                  ? 'bg-[var(--color-accent-primary)]/10 text-[var(--color-accent-primary)]'
                  : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] hover:text-[var(--color-text-primary)]'
              )}
            >
              <Sparkles className="h-3.5 w-3.5 flex-shrink-0" />
              <span className="font-medium">System Prompt</span>
            </button>

            {/* Divider */}
            <div className="my-2 border-t border-[var(--color-border)]" />

            {/* Action Buttons Row */}
            <div className="flex gap-1.5 mb-3">
              {/* Reload Skills Button */}
              <button
                onClick={handleReloadSkills}
                disabled={isReloading}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-[10px] font-medium bg-[var(--color-accent-primary)] text-white hover:bg-[var(--color-accent-secondary)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
              >
                <RefreshCw className={cn('h-3 w-3 flex-shrink-0', isReloading && 'animate-spin')} />
                <span>{isReloading ? 'Reloading...' : 'Reload'}</span>
              </button>

              {/* Enable All / Disable All */}
              <button
                onClick={() => handleToggleAll(true)}
                disabled={isUpdatingSkills || enabledCount === totalCount}
                className="flex items-center justify-center gap-1 rounded-lg px-2 py-1.5 text-[10px] font-medium border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                All on
              </button>
              <button
                onClick={() => handleToggleAll(false)}
                disabled={isUpdatingSkills || enabledCount <= 1}
                className="flex items-center justify-center gap-1 rounded-lg px-2 py-1.5 text-[10px] font-medium border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Min
              </button>
            </div>

            {/* Skills label */}
            <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
              Skills
            </div>

            {/* Skills list with toggles */}
            {isLoadingTree ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-4 w-4 animate-spin text-[var(--color-text-muted)]" />
              </div>
            ) : availableSkills.length === 0 ? (
              <div className="px-2 py-4 text-xs text-[var(--color-text-muted)]">
                No skills available
              </div>
            ) : (
              <div className="space-y-0.5">
                {availableSkills.map((skill) => (
                  <div
                    key={skill.name}
                    className={cn(
                      'flex items-center gap-2 rounded-md px-2 py-1.5 text-xs transition-colors group',
                      !skill.enabled && 'opacity-50'
                    )}
                  >
                    <Toggle
                      checked={skill.enabled}
                      onChange={(checked) => handleToggleSkill(skill.name, checked)}
                      disabled={isUpdatingSkills}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-[var(--color-text-primary)] truncate text-[11px]">
                        {skill.name}
                      </div>
                      <div className="text-[var(--color-text-muted)] truncate text-[10px] leading-tight">
                        {skill.description}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* File tree (collapsed by default behind a divider) */}
            {tree.length > 0 && (
              <>
                <div className="my-3 border-t border-[var(--color-border)]" />
                <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                  Skill Files
                </div>
                <div className="space-y-0.5">
                  {tree.map((node) => (
                    <TreeNode
                      key={node.path}
                      node={node}
                      level={0}
                      selectedPath={selectedPath}
                      expandedPaths={expandedPaths}
                      onSelect={handleSelectSkill}
                      onToggle={handleToggle}
                    />
                  ))}
                </div>
              </>
            )}
          </div>
        </div>

        {/* Right panel - Content */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--color-border)]">
            <div className="flex items-center gap-2 min-w-0">
              {selectedType === 'system_prompt' ? (
                <>
                  <Sparkles className="h-4 w-4 flex-shrink-0 text-[var(--color-accent-primary)]" />
                  <div className="min-w-0">
                    <h3 className="text-sm font-semibold text-[var(--color-text-heading)] truncate">
                      System Prompt
                    </h3>
                    <p className="text-xs text-[var(--color-text-muted)]">
                      Instructions injected to Claude Code
                    </p>
                  </div>
                </>
              ) : (
                <>
                  <FileText className="h-4 w-4 flex-shrink-0 text-[var(--color-accent-secondary)]" />
                  <div className="min-w-0">
                    <h3 className="text-sm font-semibold text-[var(--color-text-heading)] truncate">
                      {selectedPath?.split('/').pop() || 'Select a file'}
                    </h3>
                    <p className="text-xs text-[var(--color-text-muted)] truncate">
                      {selectedPath || 'Choose a skill file from the sidebar'}
                    </p>
                  </div>
                </>
              )}
            </div>

            <div className="flex items-center gap-2">
              {/* Toggle raw/rendered for markdown */}
              {isMarkdownFile && (
                <button
                  onClick={() => setShowRawCode(!showRawCode)}
                  className={cn(
                    'flex items-center gap-1 px-2 py-1 rounded-md text-xs transition-colors',
                    showRawCode
                      ? 'bg-[var(--color-accent-primary)]/10 text-[var(--color-accent-primary)]'
                      : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-bg-secondary)]'
                  )}
                >
                  {showRawCode ? (
                    <>
                      <Eye className="h-3 w-3" />
                      Rendered
                    </>
                  ) : (
                    <>
                      <Code className="h-3 w-3" />
                      Raw
                    </>
                  )}
                </button>
              )}

              {/* Close button */}
              <button
                onClick={onClose}
                className="p-1 rounded-md text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-bg-secondary)] transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Content area */}
          <div className="flex-1 overflow-y-auto p-5">
            {isLoadingContent ? (
              <div className="flex items-center justify-center py-20">
                <div className="flex flex-col items-center gap-3">
                  <Loader2 className="h-6 w-6 animate-spin text-[var(--color-accent-primary)]" />
                  <p className="text-xs text-[var(--color-text-muted)]">Loading...</p>
                </div>
              </div>
            ) : showRawCode || !isMarkdownFile ? (
              <pre className="text-xs font-mono text-[var(--color-text-primary)] whitespace-pre-wrap break-words bg-[var(--color-bg-secondary)]/50 p-4 rounded-lg border border-[var(--color-border)]">
                {content}
              </pre>
            ) : (
              <div className="prose prose-xs max-w-none text-[var(--color-text-primary)] text-xs leading-relaxed">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
