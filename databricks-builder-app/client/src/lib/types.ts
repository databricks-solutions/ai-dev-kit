/**
 * Types matching the backend API and DB models.
 */

/** Current user info from GET /api/me */
export interface UserInfo {
  user: string;
  workspace_url: string | null;
  lakebase_configured: boolean;
  lakebase_project_id: string | null;
  lakebase_error: string | null;
}

/** Project from API (projects list/detail) */
export interface Project {
  id: string;
  name: string;
  user_email: string;
  created_at: string | null;
  conversation_count: number;
}

/** Conversation summary (list) or full (detail with messages) */
export interface Conversation {
  id: string;
  project_id: string;
  title: string;
  created_at: string | null;
  session_id?: string | null;
  cluster_id?: string | null;
  default_catalog?: string | null;
  default_schema?: string | null;
  warehouse_id?: string | null;
  workspace_folder?: string | null;
  messages?: Message[];
  message_count?: number;
}

/** Single message in a conversation */
export interface Message {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string | null;
  is_error: boolean;
}

/** Databricks cluster from GET /api/clusters */
export interface Cluster {
  cluster_id: string;
  cluster_name: string | null;
  state: string;
  creator_user_name?: string | null;
}

/** Databricks SQL warehouse from GET /api/warehouses */
export interface Warehouse {
  warehouse_id: string;
  warehouse_name: string | null;
  state: string;
  cluster_size?: string | null;
  creator_name?: string | null;
}

/** Todo item from agent TodoWrite tool */
export interface TodoItem {
  id?: string;
  content: string;
  status: 'pending' | 'in_progress' | 'completed';
}

/** Skill with enabled status from GET .../skills/available */
export interface AvailableSkill {
  name: string;
  description: string;
  enabled: boolean;
}

/** Active or recent execution from GET .../executions */
export interface Execution {
  id: string;
  conversation_id: string;
  project_id: string;
  status: string;
  events: unknown[];
  error?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}
