import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

// Fun loading messages like Claude Code uses
const FUN_MESSAGES = [
  'Thinking...',
  'Pondering...',
  'Contemplating...',
  'Ruminating...',
  'Cogitating...',
  'Deliberating...',
  'Musing...',
  'Reflecting...',
  'Analyzing...',
  'Processing...',
  'Computing...',
  'Synthesizing...',
  'Formulating...',
  'Architecting...',
  'Strategizing...',
  'Investigating...',
  'Researching...',
  'Exploring...',
  'Brainstorming...',
  'Ideating...',
];

interface TodoItem {
  content: string;
  status: 'pending' | 'in_progress' | 'completed';
}

interface FunLoaderProps {
  todos?: TodoItem[];
  className?: string;
}

export function FunLoader({ todos = [], className }: FunLoaderProps) {
  const [messageIndex, setMessageIndex] = useState(() =>
    Math.floor(Math.random() * FUN_MESSAGES.length)
  );

  // Rotate messages every 2.5 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      setMessageIndex((prev) => (prev + 1) % FUN_MESSAGES.length);
    }, 2500);
    return () => clearInterval(interval);
  }, []);

  // Calculate progress
  const completedCount = todos.filter((t) => t.status === 'completed').length;
  const totalCount = todos.length;
  const progress = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;
  const currentTodo = todos.find((t) => t.status === 'in_progress');

  return (
    <div className={cn('flex flex-col items-center gap-3', className)}>
      {/* Main loader with rotating message */}
      <div className="flex items-center gap-3 rounded-xl bg-[var(--color-bg-secondary)] border border-[var(--color-border)]/50 px-4 py-3 shadow-sm">
        <Loader2 className="h-5 w-5 animate-spin text-[var(--color-accent-primary)]" />
        <span className="text-sm text-[var(--color-text-primary)] font-medium min-w-[120px]">
          {FUN_MESSAGES[messageIndex]}
        </span>
      </div>

      {/* Progress section - only show if there are todos */}
      {totalCount > 0 && (
        <div className="w-full max-w-md space-y-2">
          {/* Progress bar */}
          <div className="relative h-2 w-full overflow-hidden rounded-full bg-[var(--color-bg-secondary)] border border-[var(--color-border)]/30">
            <div
              className="absolute inset-y-0 left-0 bg-[var(--color-accent-primary)] transition-all duration-500 ease-out rounded-full"
              style={{ width: `${progress}%` }}
            />
          </div>

          {/* Progress text */}
          <div className="flex items-center justify-between text-xs text-[var(--color-text-muted)]">
            <span>
              {completedCount} of {totalCount} tasks
            </span>
            <span>{Math.round(progress)}%</span>
          </div>

          {/* Current task indicator */}
          {currentTodo && (
            <div className="flex items-center gap-2 text-xs text-[var(--color-text-muted)] bg-[var(--color-bg-secondary)]/50 rounded-md px-2 py-1.5 border border-[var(--color-border)]/30">
              <div className="h-1.5 w-1.5 rounded-full bg-[var(--color-accent-primary)] animate-pulse" />
              <span className="truncate">{currentTodo.content}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
