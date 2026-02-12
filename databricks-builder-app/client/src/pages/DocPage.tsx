import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Home,
  Database,
  Server,
  BookOpen,
  Layers,
  Code,
  Cpu,
  ArrowRight,
  ChevronRight,
  Terminal,
  Sparkles
} from 'lucide-react';

type DocSection = 'overview' | 'tools-skills' | 'app';

interface NavItem {
  id: DocSection;
  label: string;
  icon: React.ReactNode;
}

const navItems: NavItem[] = [
  { id: 'overview', label: 'Overview', icon: <Home className="h-4 w-4" /> },
  { id: 'tools-skills', label: 'Tools & Skills', icon: <Database className="h-4 w-4" /> },
  { id: 'app', label: 'MCP App', icon: <Sparkles className="h-4 w-4" /> },
];

function OverviewSection() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-[var(--color-text-heading)]">
          Databricks AI Dev Kit
        </h1>
        <p className="mt-2 text-lg text-[var(--color-text-muted)]">
          Build Databricks projects with AI coding assistants using MCP (Model Context Protocol)
        </p>
      </div>

      <div className="rounded-xl border border-[var(--color-accent-primary)]/20 bg-[var(--color-accent-primary)]/5 p-6">
        <h2 className="text-xl font-semibold text-[var(--color-text-heading)] mb-4">
          What is the AI Dev Kit?
        </h2>
        <p className="text-[var(--color-text-secondary)]">
          The AI Dev Kit provides everything you need to build on Databricks using AI assistants like Claude Code, Cursor, and more:
        </p>
        <ul className="mt-4 space-y-2">
          <li className="flex items-start gap-3">
            <BookOpen className="h-5 w-5 text-[var(--color-accent-primary)] mt-0.5 flex-shrink-0" />
            <span><code className="font-mono text-sm bg-[var(--color-background)] px-1.5 py-0.5 rounded">databricks-skills/</code> - Teach AI assistants best practices, patterns, and which tools to use</span>
          </li>
          <li className="flex items-start gap-3">
            <Database className="h-5 w-5 text-[var(--color-accent-primary)] mt-0.5 flex-shrink-0" />
            <span><code className="font-mono text-sm bg-[var(--color-background)] px-1.5 py-0.5 rounded">databricks-tools-core/</code> - Python functions for sql/, unity_catalog/, compute/, spark_declarative_pipelines/, agent_bricks/</span>
          </li>
          <li className="flex items-start gap-3">
            <Server className="h-5 w-5 text-[var(--color-accent-primary)] mt-0.5 flex-shrink-0" />
            <span><code className="font-mono text-sm bg-[var(--color-background)] px-1.5 py-0.5 rounded">databricks-mcp-server/</code> - Wraps tools and exposes them via MCP protocol</span>
          </li>
          <li className="flex items-start gap-3">
            <Sparkles className="h-5 w-5 text-[var(--color-accent-primary)] mt-0.5 flex-shrink-0" />
            <span><code className="font-mono text-sm bg-[var(--color-background)] px-1.5 py-0.5 rounded">databricks-builder-app/</code> - Claude Code in a web UI to deploy Databricks resources</span>
          </li>
        </ul>
      </div>

      {/* Visual Architecture */}
      <div>
        <h2 className="text-xl font-semibold text-[var(--color-text-heading)] mb-4">
          How It Works
        </h2>
        <div className="space-y-4">
          {/* Outer wrapper: ai-dev-kit */}
          <div className="rounded-xl border-2 border-[var(--color-border)] p-4">
            <div className="flex items-center gap-2 mb-4">
              <Layers className="h-5 w-5 text-[var(--color-text-heading)]" />
              <h3 className="font-semibold text-[var(--color-text-heading)] font-mono">ai-dev-kit/</h3>
            </div>

            {/* Skills (left) and MCP Server with Tools (right) */}
            <div className="grid gap-4 md:grid-cols-2">
              {/* Skills Layer - Left */}
              <div className="rounded-xl border-2 border-[var(--color-accent-primary)] bg-[var(--color-accent-primary)]/5 p-4 h-fit">
                <div className="flex items-center gap-2 mb-3">
                  <BookOpen className="h-5 w-5 text-[var(--color-accent-primary)]" />
                  <h3 className="font-semibold text-[var(--color-text-heading)] font-mono">databricks-skills/</h3>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-[var(--color-accent-primary)]/20 text-[var(--color-accent-primary)]">Knowledge</span>
                </div>
                <p className="text-sm text-[var(--color-text-muted)] mb-3">
                  Skills explain <em>how</em> to do things and reference the tools from databricks-tools-core.
                </p>
                <div className="flex flex-wrap gap-2">
                  {['asset-bundles/', 'databricks-app-apx/', 'databricks-app-python/', 'databricks-python-sdk/', 'mlflow-evaluation/', 'spark-declarative-pipelines/', 'synthetic-data-generation/'].map((skill) => (
                    <span key={skill} className="text-xs px-2 py-1 rounded bg-[var(--color-accent-primary)]/10 text-[var(--color-text-secondary)] font-mono">
                      {skill}
                    </span>
                  ))}
                </div>
              </div>

              {/* MCP Server wraps Tools Core - Right */}
              <div className="rounded-xl border-2 border-dashed border-green-500/40 p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Server className="h-5 w-5 text-green-400" />
                  <h3 className="font-semibold text-[var(--color-text-heading)] font-mono">databricks-mcp-server/</h3>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-green-500/20 text-green-400">MCP Protocol</span>
                </div>
                <p className="text-sm text-[var(--color-text-muted)] mb-3">
                  Wraps databricks-tools-core, exposing functions via MCP protocol.
                </p>

                {/* Tools Core Layer (nested inside MCP Server) */}
                <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Database className="h-5 w-5 text-[var(--color-accent-primary)]" />
                    <h3 className="font-semibold text-[var(--color-text-heading)] font-mono">databricks-tools-core/</h3>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-[var(--color-accent-primary)]/20 text-[var(--color-accent-primary)]">Python</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {['sql/', 'unity_catalog/', 'compute/', 'spark_declarative_pipelines/', 'agent_bricks/', 'file/'].map((module) => (
                      <span key={module} className="text-xs px-2 py-1 rounded bg-[var(--color-accent-primary)]/10 text-[var(--color-text-secondary)] font-mono">
                        {module}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Arrow */}
          <div className="flex justify-center">
            <ArrowRight className="h-6 w-6 text-[var(--color-text-muted)] rotate-90" />
          </div>

          {/* Consumers */}
          <div className="grid gap-4 md:grid-cols-2">
            {/* AI Tools (Claude Code, Cursor, etc.) */}
            <div className="rounded-xl border border-purple-500/30 bg-purple-500/5 p-4">
              <div className="flex items-center gap-2 mb-3">
                <Terminal className="h-5 w-5 text-purple-400" />
                <h3 className="font-semibold text-[var(--color-text-heading)]">AI Coding Tools</h3>
              </div>
              <p className="text-sm text-[var(--color-text-muted)] mb-3">
                Supercharge your coding AI tools with Databricks capabilities
              </p>
              <div className="flex flex-wrap gap-2">
                {['Cursor', 'Claude Code', 'Windsurf', 'Custom Agents'].map((tool) => (
                  <span key={tool} className="text-xs px-2 py-1 rounded bg-purple-500/10 text-purple-300">
                    {tool}
                  </span>
                ))}
              </div>
            </div>

            {/* MCP App */}
            <div className="rounded-xl border border-orange-500/30 bg-orange-500/5 p-4">
              <div className="flex items-center gap-2 mb-3">
                <Sparkles className="h-5 w-5 text-orange-400" />
                <h3 className="font-semibold text-[var(--color-text-heading)] font-mono">databricks-builder-app/</h3>
              </div>
              <p className="text-sm text-[var(--color-text-muted)] mb-3">
                Claude Code in a UI - an agent to work on and deploy Databricks resources
              </p>
              <div className="flex flex-wrap gap-2">
                {['Web UI', 'Project Management', 'Deploy Resources', 'Conversation History'].map((feature) => (
                  <span key={feature} className="text-xs px-2 py-1 rounded bg-orange-500/10 text-orange-300">
                    {feature}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Example Workflow */}
      <div>
        <h2 className="text-xl font-semibold text-[var(--color-text-heading)] mb-4">
          Example: Generate Synthetic Data
        </h2>
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-6">
          <div className="space-y-4">
            {/* User Request */}
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-[var(--color-accent-primary)]/20 flex items-center justify-center">
                <span className="text-sm font-medium text-[var(--color-accent-primary)]">1</span>
              </div>
              <div>
                <p className="font-medium text-[var(--color-text-heading)]">User Request</p>
                <p className="text-sm text-[var(--color-text-muted)] mt-1">
                  "Generate synthetic customer support data with realistic patterns"
                </p>
              </div>
            </div>

            {/* Read Skill */}
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-[var(--color-accent-primary)]/20 flex items-center justify-center">
                <span className="text-sm font-medium text-[var(--color-accent-primary)]">2</span>
              </div>
              <div>
                <p className="font-medium text-[var(--color-text-heading)]">Read Skill</p>
                <p className="text-sm text-[var(--color-text-muted)] mt-1">
                  Claude reads <code className="px-1 py-0.5 rounded bg-[var(--color-background)] text-xs">synthetic-data-generation/</code> skill to learn best practices
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {['Non-linear distributions', 'Referential integrity', 'Time patterns', 'Row coherence'].map((item) => (
                    <span key={item} className="text-xs px-2 py-1 rounded bg-[var(--color-accent-primary)]/10 text-[var(--color-text-secondary)]">
                      {item}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* Understand Storage */}
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-[var(--color-accent-primary)]/20 flex items-center justify-center">
                <span className="text-sm font-medium text-[var(--color-accent-primary)]">3</span>
              </div>
              <div>
                <p className="font-medium text-[var(--color-text-heading)]">Understand how to write and store raw data on Databricks UC</p>
                <p className="text-sm text-[var(--color-text-muted)] mt-1">
                  Learn from skill: save raw files to Volume, create catalog/schema/volume in script, ask user for schema name, install libraries on cluster
                </p>
              </div>
            </div>

            {/* Write Code */}
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-green-500/20 flex items-center justify-center">
                <span className="text-sm font-medium text-green-400">4</span>
              </div>
              <div>
                <p className="font-medium text-[var(--color-text-heading)]">Write Python Locally</p>
                <p className="text-sm text-[var(--color-text-muted)] mt-1">
                  Create <code className="px-1 py-0.5 rounded bg-[var(--color-background)] text-xs">scripts/generate_data.py</code> with Faker, pandas, realistic distributions
                </p>
              </div>
            </div>

            {/* Execute Remote */}
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-green-500/20 flex items-center justify-center">
                <span className="text-sm font-medium text-green-400">5</span>
              </div>
              <div>
                <p className="font-medium text-[var(--color-text-heading)]">Execute on Databricks</p>
                <p className="text-sm text-[var(--color-text-muted)] mt-1">
                  Call <code className="px-1 py-0.5 rounded bg-[var(--color-background)] text-xs">run_python_file_on_databricks()</code> - auto-selects best cluster, creates execution context, installs required libraries
                </p>
              </div>
            </div>

            {/* Handle Errors */}
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-orange-500/20 flex items-center justify-center">
                <span className="text-sm font-medium text-orange-400">6</span>
              </div>
              <div>
                <p className="font-medium text-[var(--color-text-heading)]">Fix & Retry</p>
                <p className="text-sm text-[var(--color-text-muted)] mt-1">
                  If error, edit local file, re-execute with same <code className="px-1 py-0.5 rounded bg-[var(--color-background)] text-xs">cluster_id</code> + <code className="px-1 py-0.5 rounded bg-[var(--color-background)] text-xs">context_id</code> (faster, keeps state)
                </p>
              </div>
            </div>

            {/* Validate */}
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-purple-500/20 flex items-center justify-center">
                <span className="text-sm font-medium text-purple-400">7</span>
              </div>
              <div>
                <p className="font-medium text-[var(--color-text-heading)]">Validate Results</p>
                <p className="text-sm text-[var(--color-text-muted)] mt-1">
                  Call <code className="px-1 py-0.5 rounded bg-[var(--color-background)] text-xs">get_volume_folder_details()</code> to verify written files - schema, row counts, column stats
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Why It Works */}
      <div>
        <h2 className="text-xl font-semibold text-[var(--color-text-heading)] mb-4">
          Why It Works
        </h2>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
            <div className="flex items-center gap-2 mb-2">
              <BookOpen className="h-5 w-5 text-[var(--color-accent-primary)]" />
              <h3 className="font-semibold text-[var(--color-text-heading)]">Skills teach latest features</h3>
            </div>
            <p className="text-sm text-[var(--color-text-muted)]">
              AI learns Databricks best practices through curated skills - no outdated patterns or deprecated APIs.
            </p>
          </div>

          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
            <div className="flex items-center gap-2 mb-2">
              <Code className="h-5 w-5 text-green-400" />
              <h3 className="font-semibold text-[var(--color-text-heading)]">Battle-tested abstractions</h3>
            </div>
            <p className="text-sm text-[var(--color-text-muted)]">
              High-level tools like "run this file" hide 2000+ lines of tested code with caching, retries, and optimizations.
            </p>
          </div>

          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
            <div className="flex items-center gap-2 mb-2">
              <Cpu className="h-5 w-5 text-purple-400" />
              <h3 className="font-semibold text-[var(--color-text-heading)]">Faster execution</h3>
            </div>
            <p className="text-sm text-[var(--color-text-muted)]">
              Bundled operations reduce LLM reasoning steps - no assembling dozens of API calls, just a few high-level tools.
            </p>
          </div>

          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
            <div className="flex items-center gap-2 mb-2">
              <Database className="h-5 w-5 text-orange-400" />
              <h3 className="font-semibold text-[var(--color-text-heading)]">No hallucination</h3>
            </div>
            <p className="text-sm text-[var(--color-text-muted)]">
              Tools return real data and errors - the AI knows exactly what succeeded or failed, no guessing.
            </p>
          </div>

          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
            <div className="flex items-center gap-2 mb-2">
              <ArrowRight className="h-5 w-5 text-[var(--color-accent-primary)]" />
              <h3 className="font-semibold text-[var(--color-text-heading)]">Built-in feedback loops</h3>
            </div>
            <p className="text-sm text-[var(--color-text-muted)]">
              Skills teach how to handle errors. Tools return structured results. The AI can iterate and self-correct.
            </p>
          </div>

          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
            <div className="flex items-center gap-2 mb-2">
              <Layers className="h-5 w-5 text-green-400" />
              <h3 className="font-semibold text-[var(--color-text-heading)]">Fully decoupled</h3>
            </div>
            <p className="text-sm text-[var(--color-text-muted)]">
              Use tools natively (LangChain, Claude SDK, OpenAI) or via MCP. With or without skills. For any agent framework.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

type CoverageStatus = 'done' | 'in-progress' | 'not-started' | 'tbd';

interface CoverageItem {
  product: string;
  skills: CoverageStatus;
  mcpFunctions: CoverageStatus;
  tested: CoverageStatus;
  functionalInApp?: CoverageStatus;
  owner?: string;
  testLink?: string;
  date?: string;
  comments?: string;
}

interface CoverageSection {
  title: string;
  items: CoverageItem[];
}

const coverageSections: CoverageSection[] = [
  {
    title: 'Ingestion / ETL',
    items: [
      { product: 'Lakeflow Spark Declarative Pipelines', skills: 'done', mcpFunctions: 'done', tested: 'done', functionalInApp: 'in-progress', owner: 'Cal Reynolds', date: 'Jan 13', comments: 'Tested with State Street example. Successful locally in deploying pipelines of python, sql and modifiable varieties (SCP, Iceberg, Clustering). \n\nNeeds claude-agent-sdk bug to be fixed to work with app' },
      { product: 'Lakeflow Jobs', skills: 'not-started', mcpFunctions: 'not-started', tested: 'not-started', owner: '' },
      { product: 'Synthetic Data Generation', skills: 'done', mcpFunctions: 'done', tested: 'done', owner: '' },
      { product: 'PDF / Unstructured Data Generation', skills: 'done', mcpFunctions: 'done', tested: 'done', owner: 'Quentin', comments: 'Generate realistic PDFs (invoices, contracts, reports) and unstructured data files. Uses LLM for content generation.' },
    ],
  },
  {
    title: 'ML / AI',
    items: [
      { product: 'Agent Bricks - Knowledge Assistant', skills: 'done', mcpFunctions: 'done', tested: 'done', owner: '', comments: 'Knowledge Assistant tile management' },
      { product: 'Agent Bricks - Multi Agent Supervisor', skills: 'done', mcpFunctions: 'done', tested: 'done', owner: '', comments: 'Multi Agent Supervisor tile management' },
      { product: 'Agent Bricks - Genie', skills: 'done', mcpFunctions: 'done', tested: 'done', owner: '', comments: 'Genie tile management' },
      { product: 'Model Serving', skills: 'not-started', mcpFunctions: 'not-started', tested: 'not-started', owner: '' },
      { product: 'Classic ML and MLFlow', skills: 'not-started', mcpFunctions: 'not-started', tested: 'not-started', owner: '' },
    ],
  },
  {
    title: 'AI/BI - SQL',
    items: [
      { product: 'DBSQL', skills: 'done', mcpFunctions: 'done', tested: 'done', owner: '' },
      { product: 'Unity Catalog', skills: 'done', mcpFunctions: 'done', tested: 'done', owner: '' },
      { product: 'AI/BI Dashboards', skills: 'not-started', mcpFunctions: 'not-started', tested: 'not-started', owner: '' },
    ],
  },
  {
    title: 'Other',
    items: [
      { product: 'Databricks Asset Bundles', skills: 'done', mcpFunctions: 'not-started', tested: 'not-started', owner: '' },
      { product: 'Notebook Creation', skills: 'not-started', mcpFunctions: 'not-started', tested: 'not-started', owner: '' },
      { product: 'Lakebase', skills: 'not-started', mcpFunctions: 'not-started', tested: 'not-started', owner: '' },
      { product: 'Apps', skills: 'tbd', mcpFunctions: 'tbd', tested: 'tbd', owner: 'Ivan' },
    ],
  },
];

function StatusBadge({ status }: { status: CoverageStatus }) {
  const config = {
    'done': { label: 'Initial Coverage', bg: 'bg-green-500/20', text: 'text-green-400', dot: 'bg-green-400' },
    'in-progress': { label: 'In Progress', bg: 'bg-yellow-500/20', text: 'text-yellow-400', dot: 'bg-yellow-400' },
    'not-started': { label: 'Not Started', bg: 'bg-[var(--color-text-muted)]/20', text: 'text-[var(--color-text-muted)]', dot: 'bg-[var(--color-text-muted)]' },
    'tbd': { label: 'TBD', bg: 'bg-purple-500/20', text: 'text-purple-400', dot: 'bg-purple-400' },
  };
  const { label, bg, text, dot } = config[status];

  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs ${bg} ${text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
      {label}
    </span>
  );
}

function ToolsSkillsSection() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-[var(--color-text-heading)]">
          Tools & Skills Coverage
        </h1>
        <p className="mt-2 text-lg text-[var(--color-text-muted)]">
          Current status of Databricks product coverage in the AI Dev Kit
        </p>
      </div>

      {/* Coverage Table */}
      <div className="rounded-xl border border-[var(--color-border)] overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="bg-[var(--color-bg-secondary)] border-b border-[var(--color-border)]">
              <th className="text-left px-6 py-4 text-sm font-semibold text-[var(--color-text-heading)]">Product</th>
              <th className="text-center px-6 py-4 text-sm font-semibold text-[var(--color-text-heading)]">Skills</th>
              <th className="text-center px-6 py-4 text-sm font-semibold text-[var(--color-text-heading)]">MCP Functions</th>
              <th className="text-center px-6 py-4 text-sm font-semibold text-[var(--color-text-heading)]">Tested on Local Terminal</th>
              <th className="text-center px-6 py-4 text-sm font-semibold text-[var(--color-text-heading)]">Functional in App</th>
              <th className="text-left px-6 py-4 text-sm font-semibold text-[var(--color-text-heading)]">Owner</th>
              <th className="text-left px-6 py-4 text-sm font-semibold text-[var(--color-text-heading)]">Date</th>
              <th className="text-left px-6 py-4 text-sm font-semibold text-[var(--color-text-heading)]">Comments</th>
            </tr>
          </thead>
          <tbody>
            {coverageSections.map((section) => (
              <React.Fragment key={section.title}>
                {/* Section Header */}
                <tr className="bg-[var(--color-accent-primary)]/10 border-b border-[var(--color-border)]">
                  <td colSpan={8} className="px-6 py-3 text-sm font-semibold text-[var(--color-accent-primary)]">
                    {section.title}
                  </td>
                </tr>
                {/* Section Items */}
                {section.items.map((item, idx) => (
                  <tr
                    key={item.product}
                    className={`border-b border-[var(--color-border)] last:border-b-0 ${idx % 2 === 0 ? 'bg-[var(--color-background)]' : 'bg-[var(--color-bg-secondary)]/50'}`}
                  >
                    <td className="px-6 py-4 text-sm text-[var(--color-text-primary)]">{item.product}</td>
                    <td className="px-6 py-4 text-center"><StatusBadge status={item.skills} /></td>
                    <td className="px-6 py-4 text-center"><StatusBadge status={item.mcpFunctions} /></td>
                    <td className="px-6 py-4 text-center"><StatusBadge status={item.tested} /></td>
                    <td className="px-6 py-4 text-center">{item.functionalInApp ? <StatusBadge status={item.functionalInApp} /> : '-'}</td>
                    <td className="px-6 py-4 text-sm text-[var(--color-text-muted)]">{item.owner || '-'}</td>
                    <td className="px-6 py-4 text-sm text-[var(--color-text-muted)]">{item.date || '-'}</td>
                    <td className="px-6 py-4 text-sm text-[var(--color-text-muted)] whitespace-pre-line max-w-md">{item.comments || '-'}</td>
                  </tr>
                ))}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-6 text-sm text-[var(--color-text-muted)]">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-green-400" />
          <span>Initial Coverage</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-yellow-400" />
          <span>In Progress</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-[var(--color-text-muted)]" />
          <span>Not Started</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-purple-400" />
          <span>TBD</span>
        </div>
      </div>
    </div>
  );
}

function AppSection() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-[var(--color-text-heading)]">
          databricks-builder-app
        </h1>
        <p className="mt-2 text-lg text-[var(--color-text-muted)]">
          Claude Code in a web UI - an agent to work on and deploy Databricks resources
        </p>
      </div>

      <div className="rounded-xl border border-[var(--color-accent-primary)]/20 bg-[var(--color-accent-primary)]/5 p-6">
        <p className="text-[var(--color-text-secondary)]">
          You're using it right now! This application provides a web interface for interacting with Claude
          and Databricks tools, with project-based organization and conversation history.
        </p>
      </div>

      {/* Architecture Diagram */}
      <div>
        <h2 className="text-xl font-semibold text-[var(--color-text-heading)] mb-4">
          Architecture
        </h2>
        <div className="rounded-xl border border-[var(--color-border)] p-6 space-y-4">
          {/* React Frontend - Top */}
          <div className="rounded-xl border border-[var(--color-accent-primary)]/30 bg-[var(--color-accent-primary)]/5 p-4">
            <div className="flex items-center gap-2 mb-2">
              <Code className="h-5 w-5 text-[var(--color-accent-primary)]" />
              <h3 className="font-semibold text-[var(--color-text-heading)]">React Frontend</h3>
            </div>
            <p className="text-sm text-[var(--color-text-muted)]">
              Chat UI, project management, resource configuration, file browser
            </p>
          </div>

          {/* Arrow */}
          <div className="flex justify-center">
            <ArrowRight className="h-6 w-6 text-[var(--color-text-muted)] rotate-90" />
          </div>

          {/* Backend + PostgreSQL side by side */}
          <div className="grid gap-4 md:grid-cols-3">
            {/* FastAPI Backend - 2 cols */}
            <div className="md:col-span-2 space-y-4">
              <div className="rounded-xl border border-green-500/30 bg-green-500/5 p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Server className="h-5 w-5 text-green-400" />
                  <h3 className="font-semibold text-[var(--color-text-heading)]">FastAPI Backend</h3>
                </div>
                <p className="text-sm text-[var(--color-text-muted)]">
                  Claude Agent SDK, MCP tools, file management
                </p>
              </div>

              {/* Arrow */}
              <div className="flex justify-center">
                <ArrowRight className="h-6 w-6 text-[var(--color-text-muted)] rotate-90" />
              </div>

              {/* Claude Code Session */}
              <div className="rounded-xl border border-purple-500/30 bg-purple-500/5 p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Terminal className="h-5 w-5 text-purple-400" />
                  <h3 className="font-semibold text-[var(--color-text-heading)]">Create Claude Code session through the SDK</h3>
                </div>
                <p className="text-sm text-[var(--color-text-muted)] mb-3">
                  Claude Code reads/writes files locally in the app folder <code className="px-1.5 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">project/&lt;project_id&gt;/</code>
                </p>
                <p className="text-sm text-[var(--color-text-muted)] mb-3">
                  When starting a new project, we load skills and provide tools in the Claude Code session:
                </p>
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="rounded-lg border border-[var(--color-accent-primary)]/30 bg-[var(--color-accent-primary)]/5 p-3">
                    <div className="flex items-center gap-2 mb-2">
                      <BookOpen className="h-4 w-4 text-[var(--color-accent-primary)]" />
                      <span className="font-semibold text-sm text-[var(--color-text-heading)]">Skills</span>
                    </div>
                    <p className="text-xs text-[var(--color-text-muted)]">
                      Best practices, patterns, how to use tools
                    </p>
                  </div>
                  <div className="rounded-lg border border-green-500/30 bg-green-500/5 p-3">
                    <div className="flex items-center gap-2 mb-2">
                      <Cpu className="h-4 w-4 text-green-400" />
                      <span className="font-semibold text-sm text-[var(--color-text-heading)]">Tools</span>
                    </div>
                    <p className="text-xs text-[var(--color-text-muted)]">
                      MCP functions to interact with Databricks
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* PostgreSQL - 1 col on the right */}
            <div className="rounded-xl border border-orange-500/30 bg-orange-500/5 p-4 h-fit">
              <div className="flex items-center gap-2 mb-3">
                <Database className="h-5 w-5 text-orange-400" />
                <h3 className="font-semibold text-[var(--color-text-heading)]">PostgreSQL</h3>
              </div>
              <ul className="space-y-2 text-sm text-[var(--color-text-muted)]">
                <li className="flex items-center gap-2">
                  <ChevronRight className="h-3 w-3 text-orange-400" />
                  Save conversations
                </li>
                <li className="flex items-center gap-2">
                  <ChevronRight className="h-3 w-3 text-orange-400" />
                  Claude Code session
                </li>
                <li className="flex items-center gap-2">
                  <ChevronRight className="h-3 w-3 text-orange-400" />
                  Backup project files
                </li>
                <li className="flex items-center gap-2">
                  <ChevronRight className="h-3 w-3 text-orange-400" />
                  Project details/resources
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      {/* How It Works - Key Concepts */}
      <div>
        <h2 className="text-xl font-semibold text-[var(--color-text-heading)] mb-4">
          How It Works
        </h2>
        <div className="space-y-6">
          {/* Project Creation */}
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-5">
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-[var(--color-accent-primary)]/20 flex items-center justify-center text-[var(--color-accent-primary)] font-semibold text-sm">1</div>
              <div>
                <h3 className="font-semibold text-[var(--color-text-heading)]">Project Creation</h3>
                <p className="text-sm text-[var(--color-text-muted)] mt-1">
                  Each project is user-scoped with a UUID. A directory <code className="px-1.5 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">project/&lt;project_id&gt;/</code> is created on disk.
                  Skills from <code className="px-1.5 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">databricks-skills/</code> are copied to <code className="px-1.5 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">.claude/skills/</code> in the project folder.
                </p>
              </div>
            </div>
          </div>

          {/* Claude Code Session */}
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-5">
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-purple-500/20 flex items-center justify-center text-purple-400 font-semibold text-sm">2</div>
              <div>
                <h3 className="font-semibold text-[var(--color-text-heading)]">Claude Code Session via SDK</h3>
                <p className="text-sm text-[var(--color-text-muted)] mt-1">
                  When you send a message, the backend creates a Claude Code session using the <strong>Claude Agent SDK</strong>.
                  The session runs with <code className="px-1.5 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">cwd</code> set to the project directory (file access is scoped).
                </p>
                <p className="text-sm text-[var(--color-text-muted)] mt-2">
                  The session is configured with:
                </p>
                <ul className="mt-2 space-y-1 text-sm text-[var(--color-text-muted)]">
                  <li className="flex items-center gap-2">
                    <ChevronRight className="h-3 w-3 text-purple-400" />
                    <strong>Built-in tools:</strong> Read, Write, Edit, Glob, Grep, Skill
                  </li>
                  <li className="flex items-center gap-2">
                    <ChevronRight className="h-3 w-3 text-purple-400" />
                    <strong>Databricks tools:</strong> Dynamically loaded from <code className="px-1 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">databricks-tools-core</code>
                  </li>
                  <li className="flex items-center gap-2">
                    <ChevronRight className="h-3 w-3 text-purple-400" />
                    <strong>System prompt:</strong> Includes cluster/catalog context from UI selection
                  </li>
                </ul>
              </div>
            </div>
          </div>

          {/* Session Resumption */}
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-5">
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-green-500/20 flex items-center justify-center text-green-400 font-semibold text-sm">3</div>
              <div>
                <h3 className="font-semibold text-[var(--color-text-heading)]">Multi-Turn Conversations</h3>
                <p className="text-sm text-[var(--color-text-muted)] mt-1">
                  Each conversation stores a <code className="px-1.5 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">session_id</code>.
                  When you continue a conversation, the SDK resumes from that session - Claude remembers context from previous messages.
                </p>
              </div>
            </div>
          </div>

          {/* File Backup */}
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-5">
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-orange-500/20 flex items-center justify-center text-orange-400 font-semibold text-sm">4</div>
              <div>
                <h3 className="font-semibold text-[var(--color-text-heading)]">File Backup & Restore</h3>
                <p className="text-sm text-[var(--color-text-muted)] mt-1">
                  After each agent query, project files are marked for backup. A background worker (every 10 min) ZIPs the project folder and stores it in PostgreSQL.
                </p>
                <p className="text-sm text-[var(--color-text-muted)] mt-2">
                  On app restart, if the project directory is missing, it's automatically restored from the backup. Skills are re-injected.
                </p>
              </div>
            </div>
          </div>

          {/* Streaming */}
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-5">
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-[var(--color-accent-primary)]/20 flex items-center justify-center text-[var(--color-accent-primary)] font-semibold text-sm">5</div>
              <div>
                <h3 className="font-semibold text-[var(--color-text-heading)]">Real-Time Streaming</h3>
                <p className="text-sm text-[var(--color-text-muted)] mt-1">
                  The backend streams events via Server-Sent Events (SSE): <code className="px-1.5 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">text</code>, <code className="px-1.5 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">thinking</code>, <code className="px-1.5 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">tool_use</code>, <code className="px-1.5 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">tool_result</code>.
                  You see Claude's reasoning and tool calls in real-time.
                </p>
              </div>
            </div>
          </div>

          {/* Per-User Auth */}
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-5">
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-purple-500/20 flex items-center justify-center text-purple-400 font-semibold text-sm">6</div>
              <div>
                <h3 className="font-semibold text-[var(--color-text-heading)]">Per-User Databricks Auth</h3>
                <p className="text-sm text-[var(--color-text-muted)] mt-1">
                  Databricks credentials are injected per-request using Python <code className="px-1.5 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">contextvars</code>.
                  Each user's tools run with their own Databricks permissions - no shared credentials.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Authentication & MCP Server */}
      <div>
        <h2 className="text-xl font-semibold text-[var(--color-text-heading)] mb-4">
          Authentication & MCP Server
        </h2>
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-5">
          <h3 className="font-semibold text-[var(--color-text-heading)] mb-3">In-Process Tool Execution</h3>
          <p className="text-sm text-[var(--color-text-muted)] mb-3">
            We do <strong>not</strong> use an MCP server as a separate process. Instead, we wrap the Databricks tools directly with the Claude Agent SDK, so everything runs in the same Python process and memory space.
          </p>
          <p className="text-sm text-[var(--color-text-muted)] mb-3">
            This design allows us to use Python <code className="px-1.5 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">contextvars</code> to inject per-user Databricks credentials at request time. Each tool call knows which user is calling it without passing auth tokens through the tool interface.
          </p>
          <div className="rounded-lg border border-[var(--color-accent-primary)]/30 bg-[var(--color-accent-primary)]/5 p-3 mt-4">
            <p className="text-sm text-[var(--color-text-secondary)]">
              <strong>Benefits:</strong> No subprocess overhead, shared memory, per-request auth isolation, dynamic tool discovery from <code className="px-1 py-0.5 rounded bg-[var(--color-background)] text-xs font-mono">databricks-tools-core</code>.
            </p>
          </div>
        </div>
      </div>

      {/* Security Warning */}
      <div>
        <h2 className="text-xl font-semibold text-[var(--color-text-heading)] mb-4">
          Security Note
        </h2>
        <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-5">
          <div className="flex items-start gap-3">
            <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-red-500/20 flex items-center justify-center">
              <span className="text-red-400 font-bold">!</span>
            </div>
            <div>
              <h3 className="font-semibold text-red-400 mb-2">MVP - Trusted Environment Only</h3>
              <p className="text-sm text-[var(--color-text-muted)]">
                This MVP is <strong>not secure for production use</strong>. Claude Code can execute arbitrary local code, read/write files, and run shell commands within the project directory.
              </p>
              <p className="text-sm text-[var(--color-text-muted)] mt-2">
                A malicious user could potentially execute code on the server. Only deploy this application in trusted environments where all users are authorized and trusted.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Tech Stack */}
      <div>
        <h2 className="text-xl font-semibold text-[var(--color-text-heading)] mb-4">
          Tech Stack
        </h2>
        <div className="grid gap-4 md:grid-cols-3">
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
            <h3 className="font-semibold text-[var(--color-text-heading)] mb-2">Frontend</h3>
            <div className="flex flex-wrap gap-2">
              {['React', 'TypeScript', 'TailwindCSS', 'Vite'].map((tech) => (
                <span key={tech} className="text-xs px-2 py-1 rounded bg-[var(--color-accent-primary)]/10 text-[var(--color-accent-primary)]">
                  {tech}
                </span>
              ))}
            </div>
          </div>
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
            <h3 className="font-semibold text-[var(--color-text-heading)] mb-2">Backend</h3>
            <div className="flex flex-wrap gap-2">
              {['FastAPI', 'Claude Agent SDK', 'PostgreSQL'].map((tech) => (
                <span key={tech} className="text-xs px-2 py-1 rounded bg-green-500/10 text-green-400">
                  {tech}
                </span>
              ))}
            </div>
          </div>
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
            <h3 className="font-semibold text-[var(--color-text-heading)] mb-2">Integration</h3>
            <div className="flex flex-wrap gap-2">
              {['MCP Protocol', 'Databricks SDK', 'OAuth'].map((tech) => (
                <span key={tech} className="text-xs px-2 py-1 rounded bg-purple-500/10 text-purple-400">
                  {tech}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function DocPage() {
  const [activeSection, setActiveSection] = useState<DocSection>('overview');

  const renderSection = () => {
    switch (activeSection) {
      case 'overview':
        return <OverviewSection />;
      case 'tools-skills':
        return <ToolsSkillsSection />;
      case 'app':
        return <AppSection />;
      default:
        return <OverviewSection />;
    }
  };

  return (
    <div className="h-screen bg-[var(--color-background)] flex flex-col overflow-hidden">
      {/* Top Bar */}
      <header className="fixed top-0 left-0 right-0 z-50 h-[var(--header-height)] border-b border-[var(--color-border)] bg-[var(--color-bg-secondary)]">
        <div className="h-full px-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link to="/" className="flex items-center gap-2 hover:opacity-80 transition-opacity">
              <div className="h-8 w-8 rounded-lg bg-[var(--color-accent-primary)] flex items-center justify-center">
                <Database className="h-4 w-4 text-white" />
              </div>
              <span className="font-semibold text-[var(--color-text-heading)]">AI Dev Kit</span>
            </Link>
            <span className="text-[var(--color-text-muted)]">/</span>
            <span className="text-[var(--color-text-secondary)]">Documentation</span>
          </div>
          <Link
            to="/"
            className="flex items-center gap-2 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text-heading)] transition-colors"
          >
            <Home className="h-4 w-4" />
            Back to Projects
          </Link>
        </div>
      </header>

      {/* Spacer for fixed header */}
      <div className="flex-shrink-0 h-[var(--header-height)]" />

      {/* Main Layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Navigation */}
        <nav className="w-64 flex-shrink-0 border-r border-[var(--color-border)] bg-[var(--color-bg-secondary)] overflow-y-auto">
          <div className="p-4 space-y-1">
            {navItems.map((item) => (
              <button
                key={item.id}
                onClick={() => setActiveSection(item.id)}
                className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                  activeSection === item.id
                    ? 'bg-[var(--color-accent-primary)]/10 text-[var(--color-accent-primary)]'
                    : 'text-[var(--color-text-muted)] hover:bg-[var(--color-background)] hover:text-[var(--color-text-heading)]'
                }`}
              >
                {item.icon}
                {item.label}
              </button>
            ))}
          </div>
        </nav>

        {/* Content Area */}
        <main className="flex-1 overflow-y-auto">
          <div className="max-w-7xl mx-auto px-8 py-8">
            {renderSection()}
          </div>
        </main>
      </div>
    </div>
  );
}
