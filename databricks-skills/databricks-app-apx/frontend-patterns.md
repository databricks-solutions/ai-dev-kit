# Frontend Patterns (React + TypeScript)

Detailed React frontend patterns for APX applications.

---

## Project Setup

### Vite + React + TypeScript

```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
```

### vite.config.ts

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
  },
});
```

The proxy configuration routes `/api/*` requests to the FastAPI backend during local development. In production, both frontend and backend are served from the same origin.

### tsconfig.json

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ESNext",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "moduleResolution": "bundler",
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["src"]
}
```

---

## shadcn/ui Integration

shadcn/ui provides accessible, composable components built on Radix UI and Tailwind CSS.

### Initialize shadcn

```bash
npx shadcn@latest init
```

### Add components

```bash
npx shadcn@latest add button card table badge input select dialog skeleton
```

### Component usage

```tsx
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
```

---

## API Client Pattern

### Typed API client

```typescript
// src/lib/api.ts
const API_BASE = "/api";

export interface Project {
  id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectInput {
  name: string;
  description: string;
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

export const api = {
  projects: {
    list: (): Promise<Project[]> =>
      fetch(`${API_BASE}/projects`).then(handleResponse<Project[]>),

    get: (id: string): Promise<Project> =>
      fetch(`${API_BASE}/projects/${id}`).then(handleResponse<Project>),

    create: (data: ProjectInput): Promise<Project> =>
      fetch(`${API_BASE}/projects`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      }).then(handleResponse<Project>),

    update: (id: string, data: ProjectInput): Promise<Project> =>
      fetch(`${API_BASE}/projects/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      }).then(handleResponse<Project>),

    delete: (id: string): Promise<void> =>
      fetch(`${API_BASE}/projects/${id}`, { method: "DELETE" }).then(() => {}),
  },
};
```

### Using the API client

```tsx
import { api, Project } from "@/lib/api";

function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.projects
      .list()
      .then(setProjects)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Skeleton className="h-32 w-full" />;
  if (error) return <div className="text-red-500">Error: {error}</div>;

  return (
    <div>
      {projects.map((p) => (
        <ProjectCard key={p.id} project={p} />
      ))}
    </div>
  );
}
```

---

## Routing with React Router

### Setup

```bash
npm install react-router-dom
```

### Route configuration

```tsx
// src/App.tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { ProjectsPage } from "@/pages/ProjectsPage";
import { ProjectDetailPage } from "@/pages/ProjectDetailPage";
import { NewProjectPage } from "@/pages/NewProjectPage";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<ProjectsPage />} />
          <Route path="/projects/:id" element={<ProjectDetailPage />} />
          <Route path="/projects/new" element={<NewProjectPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
```

### Layout component

```tsx
// src/components/Layout.tsx
import { Outlet, Link } from "react-router-dom";

export function Layout() {
  return (
    <div className="min-h-screen bg-background">
      <nav className="border-b px-6 py-3">
        <Link to="/" className="text-lg font-semibold">
          My App
        </Link>
      </nav>
      <main className="container mx-auto px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
```

---

## Form Handling

### Simple form with controlled state

```tsx
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ProjectInput } from "@/lib/api";

export function CreateProjectForm({ onCreated }: { onCreated: () => void }) {
  const [form, setForm] = useState<ProjectInput>({ name: "", description: "" });
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await api.projects.create(form);
      setForm({ name: "", description: "" });
      onCreated();
    } catch (err) {
      console.error("Failed to create project:", err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <Label htmlFor="name">Name</Label>
        <Input
          id="name"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          required
        />
      </div>
      <div>
        <Label htmlFor="description">Description</Label>
        <Input
          id="description"
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
        />
      </div>
      <Button type="submit" disabled={submitting}>
        {submitting ? "Creating..." : "Create Project"}
      </Button>
    </form>
  );
}
```

### React Hook Form (for complex forms)

```bash
npm install react-hook-form @hookform/resolvers zod
```

```tsx
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

const projectSchema = z.object({
  name: z.string().min(1, "Name is required").max(200),
  description: z.string().optional(),
});

type ProjectForm = z.infer<typeof projectSchema>;

export function CreateProjectFormAdvanced() {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ProjectForm>({
    resolver: zodResolver(projectSchema),
  });

  const onSubmit = async (data: ProjectForm) => {
    await api.projects.create(data);
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div>
        <Label htmlFor="name">Name</Label>
        <Input {...register("name")} />
        {errors.name && <p className="text-red-500 text-sm">{errors.name.message}</p>}
      </div>
      <Button type="submit" disabled={isSubmitting}>
        Create
      </Button>
    </form>
  );
}
```

---

## Data Display Patterns

### Table with shadcn/ui

```tsx
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Project } from "@/lib/api";

export function ProjectsTable({ projects }: { projects: Project[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Description</TableHead>
          <TableHead>Created</TableHead>
          <TableHead>Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {projects.map((p) => (
          <TableRow key={p.id}>
            <TableCell className="font-medium">{p.name}</TableCell>
            <TableCell>{p.description}</TableCell>
            <TableCell>{new Date(p.created_at).toLocaleDateString()}</TableCell>
            <TableCell>
              <Button variant="outline" size="sm" asChild>
                <Link to={`/projects/${p.id}`}>View</Link>
              </Button>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
```

### Loading skeleton

```tsx
import { Skeleton } from "@/components/ui/skeleton";

export function ProjectsTableSkeleton() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </div>
  );
}
```

---

## Environment Variables

Vite exposes environment variables prefixed with `VITE_`:

```
# .env.development
VITE_API_BASE=http://localhost:8000/api
```

```typescript
// Usage in code
const API_BASE = import.meta.env.VITE_API_BASE || "/api";
```

In production (deployed to Databricks), use the default `/api` path since both frontend and backend share the same origin.
