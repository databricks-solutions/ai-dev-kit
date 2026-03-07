import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  createProject as apiCreateProject,
  deleteProject as apiDeleteProject,
  renameProject as apiRenameProject,
  fetchProjects,
} from "@/lib/api";
import type { Project } from "@/lib/types";

interface ProjectsContextType {
  projects: Project[];
  loading: boolean;
  error: Error | null;
  refresh: () => Promise<void>;
  createProject: (name: string) => Promise<Project>;
  deleteProject: (projectId: string) => Promise<void>;
  renameProject: (projectId: string, name: string) => Promise<void>;
}

const ProjectsContext = createContext<ProjectsContextType | null>(null);

export function ProjectsProvider({ children }: { children: ReactNode }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await fetchProjects();
      setProjects(data);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setLoading(false);
    }
  }, []);

  const createProject = useCallback(async (name: string): Promise<Project> => {
    const project = await apiCreateProject(name);
    setProjects((prev) => [project, ...prev]);
    return project;
  }, []);

  const deleteProject = useCallback(async (projectId: string): Promise<void> => {
    await apiDeleteProject(projectId);
    setProjects((prev) => prev.filter((p) => p.id !== projectId));
  }, []);

  const renameProject = useCallback(async (projectId: string, name: string): Promise<void> => {
    await apiRenameProject(projectId, name);
    setProjects((prev) =>
      prev.map((p) => (p.id === projectId ? { ...p, name } : p))
    );
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const value: ProjectsContextType = {
    projects,
    loading,
    error,
    refresh,
    createProject,
    deleteProject,
    renameProject,
  };

  return (
    <ProjectsContext.Provider value={value}>
      {children}
    </ProjectsContext.Provider>
  );
}

export function useProjects() {
  const context = useContext(ProjectsContext);
  if (!context) {
    throw new Error("useProjects must be used within a ProjectsProvider");
  }
  return context;
}
