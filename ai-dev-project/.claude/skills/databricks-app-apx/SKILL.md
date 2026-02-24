---
name: databricks-app-apx
description: "Build full-stack Databricks applications using APX framework (FastAPI + React)."
---

# Databricks APX Application

Build full-stack Databricks applications using APX framework (FastAPI + React).

## Trigger Conditions

**Invoke when user requests**:
- "Databricks app" or "Databricks application"
- Full-stack app for Databricks without specifying framework
- Mentions APX framework

**Do NOT invoke if user specifies**: Streamlit, Dash, Node.js, Shiny, Gradio, Flask, or other frameworks.

## Prerequisites Check

Option A)
Repository configured for use with APX.
1.. Verify APX MCP available: `mcp-cli tools | grep apx`
2. Verify shadcn MCP available: `mcp-cli tools | grep shadcn`
3. Confirm APX project (check `pyproject.toml`)

Option B)
Install APX
1. Verify uv available or prompt for install. On Mac, suggest: `brew install uv`.
2. Verify bun available or prompt for install. On Mac, suggest: 
```
brew tap oven-sh/bun
brew install bun
```
3. Verify git available or prompt for install.
4. Run APX setup commands:
```
uvx --from git+https://github.com/databricks-solutions/apx.git apx init
```


## Workflow Overview

Total time: 55-70 minutes

1. **Initialize** (5 min) - Start servers, create todos
2. **Backend** (15-20 min) - Models + routes with mock data
3. **Frontend** (20-25 min) - Components + pages
4. **Test** (5-10 min) - Type check + manual verification
5. **Document** (10 min) - README + code structure guide

## Phase 1: Initialize

```bash
# Start APX development server
mcp-cli call apx/start '{}'
mcp-cli call apx/status '{}'
```

Create TodoWrite with tasks:
- Start servers ✓
- Design models
- Create API routes
- Add UI components
- Create pages
- Test & document

## Phase 2: Backend Development

### Create Pydantic Models

In `src/{app_name}/backend/models.py`:

**Follow 3-model pattern**:
- `EntityIn` - Input validation
- `EntityOut` - Complete output with computed fields
- `EntityListOut` - Performance-optimized summary

**See [backend-patterns.md](backend-patterns.md) for complete code templates.**

### Create API Routes

In `src/{app_name}/backend/router.py`:

**Critical requirements**:
- Always include `response_model` (enables OpenAPI generation)
- Always include `operation_id` (becomes frontend hook name)
- Use naming pattern: `listX`, `getX`, `createX`, `updateX`, `deleteX`
- Initialize 3-4 mock data samples for testing

**See [backend-patterns.md](backend-patterns.md) for complete CRUD templates.**

### Type Check

```bash
mcp-cli call apx/dev_check '{}'
```

Fix any Python type errors reported by basedpyright.

## Phase 3: Frontend Development

**Wait 5-10 seconds** after backend changes for OpenAPI client regeneration.

### Add UI Components

```bash
# Get shadcn add command
mcp-cli call shadcn/get_add_command_for_items '{
  "items": ["@shadcn/button", "@shadcn/card", "@shadcn/table",
            "@shadcn/badge", "@shadcn/select", "@shadcn/skeleton"]
}'
```

Run the command from project root with `--yes` flag.

### Create Pages

**List page**: `src/{app_name}/ui/routes/_sidebar/{entity}.tsx`
- Table view with all entities
- Suspense boundaries with skeleton fallback
- Formatted data (currency, dates, status colors)

**Detail page**: `src/{app_name}/ui/routes/_sidebar/{entity}.$id.tsx`
- Complete entity view with cards
- Update/delete mutations
- Back navigation

**See [frontend-patterns.md](frontend-patterns.md) for complete page templates.**

### Update Navigation

In `src/{app_name}/ui/routes/_sidebar/route.tsx`, add new item to `navItems` array.

## Phase 4: Testing

```bash
# Type check both backend and frontend
mcp-cli call apx/dev_check '{}'

# Test API endpoints
curl http://localhost:8000/api/{entities} | jq .
curl http://localhost:8000/api/{entities}/{id} | jq .

# Get frontend URL
mcp-cli call apx/get_frontend_url '{}'
```

Manually verify in browser:
- List page displays data
- Detail page shows complete info
- Mutations work (update, delete)
- Loading states work (skeletons)
- Browser console errors are automatically captured in APX dev logs

## Phase 5: Deployment & Monitoring

### Deploy to Databricks

Use DABs to deploy your APX application to Databricks. See the `asset-bundles` skill for complete deployment guidance.

### Monitor Application Logs

**Automated log checking with APX MCP:**

The APX MCP server can automatically check deployed application logs. Simply ask:
"Please check the deployed app logs for <app-name>"


The APX MCP will retrieve logs and identify issues automatically, including:
- Deployment status and errors
- Runtime exceptions and stack traces
- Both `[SYSTEM]` (deployment) and `[APP]` (application) logs
- Browser console errors (now included in APX dev logs)

**Manual log checking (reference):**

For direct CLI access:
```bash
databricks apps logs <app-name> --profile <profile-name>
```

**Key patterns to look for:**
- ✅ `Deployment successful` - App deployed correctly
- ✅ `App started successfully` - Application is running
- ❌ `Error:` - Check stack traces for issues

## Phase 6: Documentation

Create two markdown files:

**README.md**:
- Features overview
- Technology stack
- How app was created (AI tools + MCP servers used)
- Application architecture
- Getting started instructions
- API documentation
- Development workflow

**CODE_STRUCTURE.md**:
- Directory structure explanation
- Backend structure (models, routes, patterns)
- Frontend structure (routes, components, hooks)
- Auto-generated files warnings
- Guide for adding new features
- Best practices
- Common patterns
- Troubleshooting guide

## Key Patterns

### Backend
- **3-model pattern**: Separate In, Out, and ListOut models
- **operation_id naming**: `listEntities` → `useListEntities()`
- **Type hints everywhere**: Enable validation and IDE support

### Frontend
- **Suspense hooks**: `useXSuspense(selector())`
- **Suspense boundaries**: Always provide skeleton fallback
- **Formatters**: Currency, dates, status colors
- **Never edit**: `lib/api.ts` or `types/routeTree.gen.ts`

## Success Criteria

- [ ] Type checking passes (`apx dev check` succeeds)
- [ ] API endpoints return correct data (curl verification)
- [ ] Frontend displays and mutates data correctly
- [ ] Loading states work (skeletons display)
- [ ] Documentation complete

## Common Issues

**Deployed app not working**: Ask to check deployed app logs (APX MCP will automatically retrieve and analyze them) or manually use `databricks apps logs <app-name>`
**Python type errors**: Use explicit casting for dict access, check Optional fields
**TypeScript errors**: Wait for OpenAPI regen, verify hook names match operation_ids
**OpenAPI not updating**: Check watcher status with `apx dev status`, restart if needed
**Components not added**: Run shadcn from project root with `--yes` flag

## Reference Materials

- **[backend-patterns.md](backend-patterns.md)** - Complete backend code templates
- **[frontend-patterns.md](frontend-patterns.md)** - Complete frontend page templates
- **[best-practices.md](best-practices.md)** - Best practices, anti-patterns, debugging

Read these files only when actively writing that type of code or debugging issues.
