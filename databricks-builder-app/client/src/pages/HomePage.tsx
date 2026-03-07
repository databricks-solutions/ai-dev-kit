import { useState, useMemo, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Trash2, Loader2, MessageSquare, Plus, ArrowRight, Clock, BarChart3, Folder, Pencil, Check, X } from 'lucide-react';
import { toast } from 'sonner';
import { MainLayout } from '@/components/layout/MainLayout';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { useProjects } from '@/contexts/ProjectsContext';
import { useUser } from '@/contexts/UserContext';
import { formatRelativeTime } from '@/lib/utils';

type SortMode = 'recent' | 'conversations';

/* ─── Deterministic color from string ─── */
const CARD_PALETTES = [
  { from: '#FF3621', to: '#FF6B4A' },  // red
  { from: '#E8590C', to: '#FF922B' },  // orange
  { from: '#D6336C', to: '#F06595' },  // pink
  { from: '#7048E8', to: '#9775FA' },  // violet
  { from: '#1C7ED6', to: '#4DABF7' },  // blue
  { from: '#0CA678', to: '#38D9A9' },  // teal
  { from: '#E03131', to: '#FF6B6B' },  // crimson
  { from: '#6741D9', to: '#B197FC' },  // purple
];

function hashString(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash + str.charCodeAt(i)) | 0;
  }
  return Math.abs(hash);
}

function getCardPalette(id: string) {
  return CARD_PALETTES[hashString(id) % CARD_PALETTES.length];
}

/* ─── Animated mesh gradient canvas ─── */
function MeshGradient() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationId: number;
    let t = 0;

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.scale(dpr, dpr);
    };
    resize();
    window.addEventListener('resize', resize);

    const blobs = [
      { x: 0.2,  y: 0.25, r: 260, color: [255, 54, 33],  sx: 0.7,  sy: 0.5,  px: 0,    py: 2   },
      { x: 0.75, y: 0.35, r: 240, color: [255, 95, 70],   sx: 0.4,  sy: 0.6,  px: 1.2,  py: 0.8 },
      { x: 0.5,  y: 0.65, r: 220, color: [255, 140, 50],  sx: 0.55, sy: 0.35, px: 3.5,  py: 1.5 },
      { x: 0.1,  y: 0.6,  r: 200, color: [200, 40, 20],   sx: 0.3,  sy: 0.7,  px: 5,    py: 4   },
      { x: 0.85, y: 0.2,  r: 210, color: [255, 170, 80],  sx: 0.6,  sy: 0.45, px: 2.5,  py: 3.2 },
      { x: 0.55, y: 0.3,  r: 180, color: [255, 60, 40],   sx: 0.5,  sy: 0.55, px: 4.1,  py: 5.3 },
    ];

    const draw = () => {
      const rect = canvas.getBoundingClientRect();
      const w = rect.width;
      const h = rect.height;

      ctx.clearRect(0, 0, w, h);

      for (const blob of blobs) {
        const bx = blob.x * w + Math.sin(t * blob.sx + blob.px) * (w * 0.15)
                               + Math.sin(t * blob.sx * 0.6 + blob.px * 1.7) * (w * 0.06);
        const by = blob.y * h + Math.cos(t * blob.sy + blob.py) * (h * 0.18)
                               + Math.cos(t * blob.sy * 0.7 + blob.py * 1.3) * (h * 0.05);
        const br = blob.r + Math.sin(t * 0.8 + blob.r * 0.01) * 40;

        const gradient = ctx.createRadialGradient(bx, by, 0, bx, by, br);
        const [r, g, b] = blob.color;
        gradient.addColorStop(0, `rgba(${r}, ${g}, ${b}, 0.45)`);
        gradient.addColorStop(0.4, `rgba(${r}, ${g}, ${b}, 0.18)`);
        gradient.addColorStop(1, `rgba(${r}, ${g}, ${b}, 0)`);

        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, w, h);
      }

      t += 0.012;
      animationId = requestAnimationFrame(draw);
    };

    draw();
    return () => {
      cancelAnimationFrame(animationId);
      window.removeEventListener('resize', resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 w-full h-full"
      style={{ filter: 'blur(60px) saturate(1.4)' }}
    />
  );
}

/* ─── Floating grid of subtle dots ─── */
function DotGrid() {
  return (
    <div
      className="absolute inset-0 opacity-[0.04]"
      style={{
        backgroundImage: 'radial-gradient(circle, var(--color-text-heading) 1px, transparent 1px)',
        backgroundSize: '28px 28px',
      }}
    />
  );
}

export default function HomePage() {
  const navigate = useNavigate();
  const { loading: userLoading } = useUser();
  const { projects, loading: projectsLoading, createProject, deleteProject, renameProject } = useProjects();
  const [newProjectName, setNewProjectName] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [sortMode, setSortMode] = useState<SortMode>('recent');
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const renameInputRef = useRef<HTMLInputElement>(null);

  const sortedProjects = useMemo(() => {
    const sorted = [...projects];
    if (sortMode === 'recent') {
      sorted.sort((a, b) => {
        if (!a.created_at) return 1;
        if (!b.created_at) return -1;
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      });
    } else {
      sorted.sort((a, b) => b.conversation_count - a.conversation_count);
    }
    return sorted;
  }, [projects, sortMode]);

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName.trim()) return;

    setIsCreating(true);
    try {
      const project = await createProject(newProjectName.trim());
      setNewProjectName('');
      toast.success('Project created');
      navigate(`/projects/${project.id}`);
    } catch (error) {
      toast.error('Failed to create project');
      console.error(error);
    } finally {
      setIsCreating(false);
    }
  };

  const handleDeleteProject = async (e: React.MouseEvent, projectId: string) => {
    e.stopPropagation();
    if (!confirm('Delete this project and all its conversations?')) return;

    try {
      await deleteProject(projectId);
      toast.success('Project deleted');
    } catch (error) {
      toast.error('Failed to delete project');
      console.error(error);
    }
  };

  const startRename = (e: React.MouseEvent, project: { id: string; name: string }) => {
    e.stopPropagation();
    setRenamingId(project.id);
    setRenameValue(project.name);
    setTimeout(() => renameInputRef.current?.select(), 0);
  };

  const confirmRename = async (e?: React.FormEvent) => {
    e?.preventDefault();
    e?.stopPropagation();
    if (!renamingId || !renameValue.trim()) return;

    try {
      await renameProject(renamingId, renameValue.trim());
      toast.success('Project renamed');
    } catch (error) {
      toast.error('Failed to rename project');
      console.error(error);
    }
    setRenamingId(null);
  };

  const cancelRename = (e?: React.MouseEvent) => {
    e?.stopPropagation();
    setRenamingId(null);
  };

  if (userLoading || projectsLoading) {
    return (
      <MainLayout>
        <div className="flex h-full items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-[var(--color-text-muted)]" />
        </div>
      </MainLayout>
    );
  }

  return (
    <MainLayout>
      <div className="flex-1 overflow-y-auto">
        {/* ─── Hero section ─── */}
        <section className="relative overflow-hidden">
          <div className="absolute inset-0 bg-[var(--color-background)]" />
          <MeshGradient />
          <DotGrid />

          <div className="relative z-10 mx-auto max-w-5xl px-6 pt-20 pb-16 text-center">
            <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-[var(--color-bg-secondary)] border border-[var(--color-border)] shadow-lg">
              <svg className="w-9 h-9" viewBox="33 0 28 31" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path
                  d="M59.7279 12.5153L47.2039 19.6185L33.8814 12.0502L33.251 12.3884V17.885L47.2039 25.8339L59.7279 18.7306V21.648L47.2039 28.7513L33.8814 21.1829L33.251 21.5212V22.4514L47.2039 30.4002L61.1989 22.4514V16.9548L60.5685 16.6165L47.2039 24.1849L34.7219 17.0816V14.2065L47.2039 21.2675L61.1989 13.3186V7.9066L60.4844 7.52607L47.2039 15.0521L35.3943 8.32941L47.2039 1.64897L56.9541 7.14554L57.8367 6.68044V6.00394L47.2039 0L33.251 7.9066V8.75223L47.2039 16.7011L59.7279 9.59785V12.5153Z"
                  fill="#FF3621"
                />
              </svg>
            </div>

            <h1 className="text-5xl font-bold tracking-tight text-[var(--color-text-heading)] sm:text-6xl">
              AI Dev Kit
            </h1>
            <p className="mx-auto mt-4 max-w-2xl text-lg text-[var(--color-text-muted)] leading-relaxed">
              Build, deploy, and manage Databricks resources with an AI-powered coding agent.
              Create a project to get started.
            </p>

            <form
              onSubmit={handleCreateProject}
              className="mx-auto mt-8 flex max-w-lg gap-3"
            >
              <Input
                value={newProjectName}
                onChange={(e) => setNewProjectName(e.target.value)}
                placeholder="New project name..."
                className="flex-1 h-12 text-base bg-[var(--color-bg-secondary)]/80 backdrop-blur border-[var(--color-border)] shadow-sm"
              />
              <Button
                type="submit"
                disabled={!newProjectName.trim() || isCreating}
                className="h-12 px-6 text-base gap-2"
              >
                {isCreating ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <>
                    <Plus className="h-4 w-4" />
                    Create
                  </>
                )}
              </Button>
            </form>
          </div>

          <div className="absolute bottom-0 left-0 right-0 h-24 bg-gradient-to-t from-[var(--color-background)] to-transparent" />
        </section>

        {/* ─── Projects section ─── */}
        <section className="relative z-10 mx-auto max-w-5xl px-6 pb-16">
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-lg font-semibold text-[var(--color-text-heading)]">
              Your Projects
              <span className="ml-2 text-sm font-normal text-[var(--color-text-muted)]">
                ({projects.length})
              </span>
            </h2>

            {projects.length > 1 && (
              <div className="flex items-center rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-0.5">
                <button
                  onClick={() => setSortMode('recent')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                    sortMode === 'recent'
                      ? 'bg-[var(--color-background)] text-[var(--color-text-heading)] shadow-sm'
                      : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-heading)]'
                  }`}
                >
                  <Clock className="h-3 w-3" />
                  Recent
                </button>
                <button
                  onClick={() => setSortMode('conversations')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                    sortMode === 'conversations'
                      ? 'bg-[var(--color-background)] text-[var(--color-text-heading)] shadow-sm'
                      : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-heading)]'
                  }`}
                >
                  <BarChart3 className="h-3 w-3" />
                  Most Active
                </button>
              </div>
            )}
          </div>

          {projects.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-bg-secondary)]/50 py-16 text-center">
              <Folder className="mx-auto h-10 w-10 text-[var(--color-text-muted)] opacity-40" />
              <p className="mt-3 text-sm text-[var(--color-text-muted)]">
                No projects yet. Create one above to get started.
              </p>
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {sortedProjects.map((project) => {
                const palette = getCardPalette(project.id);
                const monogram = project.name.charAt(0).toUpperCase();
                const isRenaming = renamingId === project.id;

                return (
                  <div
                    key={project.id}
                    onClick={() => !isRenaming && navigate(`/projects/${project.id}`)}
                    className="group relative flex flex-col rounded-2xl border border-[var(--color-border)]/60 bg-[var(--color-bg-secondary)] cursor-pointer transition-all duration-200 hover:border-[var(--color-border)] hover:shadow-xl hover:shadow-black/[0.04] hover:-translate-y-0.5 overflow-hidden"
                  >
                    {/* Gradient accent bar */}
                    <div
                      className="h-1 opacity-70 group-hover:opacity-100 transition-opacity"
                      style={{ background: `linear-gradient(to right, ${palette.from}, ${palette.to})` }}
                    />

                    <div className="p-5 flex flex-col flex-1">
                      {/* Top row: monogram + actions */}
                      <div className="flex items-start justify-between mb-4">
                        <div
                          className="flex h-11 w-11 items-center justify-center rounded-xl text-white font-bold text-lg"
                          style={{ background: `linear-gradient(135deg, ${palette.from}, ${palette.to})` }}
                        >
                          {monogram}
                        </div>
                        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button
                            onClick={(e) => startRename(e, project)}
                            className="p-1.5 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text-heading)] hover:bg-[var(--color-bg-tertiary)]"
                            title="Rename"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                          <button
                            onClick={(e) => handleDeleteProject(e, project.id)}
                            className="p-1.5 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-error)] hover:bg-[var(--color-error)]/10"
                            title="Delete"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </div>

                      {/* Project name — editable or static */}
                      {isRenaming ? (
                        <form
                          onSubmit={confirmRename}
                          onClick={(e) => e.stopPropagation()}
                          className="flex items-center gap-1.5"
                        >
                          <input
                            ref={renameInputRef}
                            value={renameValue}
                            onChange={(e) => setRenameValue(e.target.value)}
                            onKeyDown={(e) => e.key === 'Escape' && cancelRename()}
                            onBlur={() => confirmRename()}
                            className="flex-1 min-w-0 text-lg font-semibold text-[var(--color-text-heading)] bg-transparent border-b-2 border-[var(--color-accent-primary)] outline-none py-0.5"
                            autoFocus
                          />
                          <button
                            type="submit"
                            className="p-1 rounded text-[var(--color-success)] hover:bg-[var(--color-success)]/10"
                          >
                            <Check className="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            onClick={cancelRename}
                            className="p-1 rounded text-[var(--color-text-muted)] hover:bg-[var(--color-bg-tertiary)]"
                          >
                            <X className="h-4 w-4" />
                          </button>
                        </form>
                      ) : (
                        <h3 className="text-lg font-semibold text-[var(--color-text-heading)] truncate leading-tight">
                          {project.name}
                        </h3>
                      )}

                      {/* Spacer */}
                      <div className="flex-1 min-h-4" />

                      {/* Bottom stats */}
                      <div className="flex items-center justify-between pt-4 border-t border-[var(--color-border)]/40">
                        <div className="flex items-center gap-1.5 text-xs text-[var(--color-text-muted)]">
                          <MessageSquare className="h-3.5 w-3.5" />
                          <span>
                            {project.conversation_count} conversation{project.conversation_count !== 1 ? 's' : ''}
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-[var(--color-text-muted)]">
                            {project.created_at ? formatRelativeTime(project.created_at) : ''}
                          </span>
                          <ArrowRight className="h-3.5 w-3.5 text-[var(--color-accent-primary)] opacity-0 group-hover:opacity-100 transition-opacity" />
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </div>
    </MainLayout>
  );
}
