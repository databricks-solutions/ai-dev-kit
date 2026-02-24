# MLflow Tracing - TypeScript Guide

## Contents
- Quick Start
- API Reference (Core APIs, Span Manipulation, Auto-Tracing Wrappers, Span Types)
- Instrumentation Methods (Function Wrapper, Manual Spans)
- User/Session Tracking
- Combining Auto-Tracing with Custom Tracing
- Common Issues

---

## Quick Start

### Install and Configure

```bash
npm install mlflow-tracing
```

```typescript
import * as mlflow from "mlflow-tracing";

mlflow.init({
    trackingUri: "http://localhost:5000",
    experimentId: "my-agent",
});
```

### Enable Tracing

```typescript
const myFunction = mlflow.trace(
    (query: string) => {
        // Your code here
        return result;
    },
    { name: "my_function", spanType: mlflow.SpanType.CHAIN }
);
```

---

## API Reference

### Core Tracing APIs

```typescript
import * as mlflow from "mlflow-tracing";

// Initialize (required before tracing)
mlflow.init({
    trackingUri: "http://localhost:5000",
    experimentId: "my-experiment",
});

// Function wrapper - creates traced version of a function
const tracedFn = mlflow.trace(
    (arg: string) => { return result; },
    { name: "my_function", spanType: mlflow.SpanType.CHAIN }
);

// Manual span - for dynamic names or non-function code
const result = await mlflow.withSpan(
    { name: "dynamic_span", spanType: mlflow.SpanType.TOOL },
    async (span) => {
        span.setInputs({ key: "value" });
        const result = await doWork();
        span.setOutputs({ result });
        return result;
    }
);

// Flush traces before process exit
await mlflow.flushTraces();
```

### Span Manipulation

```typescript
// Get current active span (inside a traced function)
const span = mlflow.getCurrentActiveSpan();
if (span) {
    span.setInputs({ query });
    span.setOutputs({ result });
    span.setAttribute("model", "gpt-4o-mini");
}

// Update current trace metadata/tags
mlflow.updateCurrentTrace({
    tags: { environment: "production" },
    metadata: {
        "mlflow.trace.user": userId,
        "mlflow.trace.session": sessionId,
    },
    requestPreview: "Custom request summary...",
    responsePreview: "Custom response summary...",
});
```

### Auto-Tracing Wrappers

```typescript
import { tracedOpenAI } from "mlflow-openai";
import { OpenAI } from "openai";

// Wrap OpenAI client - all calls auto-traced
const openai = tracedOpenAI(new OpenAI());
```

### Span Types

```typescript
mlflow.SpanType.LLM        // LLM inference calls
mlflow.SpanType.CHAIN      // Multi-step pipelines
mlflow.SpanType.TOOL       // Tool/function calls
mlflow.SpanType.AGENT      // Agent orchestration
mlflow.SpanType.RETRIEVER  // Document retrieval
mlflow.SpanType.EMBEDDING  // Embedding generation
mlflow.SpanType.RERANKER   // Result reranking
mlflow.SpanType.PARSER     // Output parsing
mlflow.SpanType.UNKNOWN    // Default/other
```

---

## Instrumentation Methods

### Method 1: Function Wrapper (Recommended)

**Prefer wrapper over manual spans** - it auto-captures function name, inputs, and outputs.

```typescript
const retrieveDocuments = mlflow.trace(
    (query: string): string[] => {
        return documents;
    },
    { name: "retrieve_documents", spanType: mlflow.SpanType.RETRIEVER }
);

const searchDatabase = mlflow.trace(
    (sql: string): Record<string, unknown> => {
        return results;
    },
    { name: "search_database", spanType: mlflow.SpanType.TOOL }
);
```

### Method 2: Manual Spans with withSpan

Use when you can't use a function wrapper (dynamic span names, non-function code):

```typescript
const result = await mlflow.withSpan(
    { name: `process_${itemId}` },
    async (span) => {
        span.setInputs({ query });
        const result = await process(query);
        span.setOutputs({ result });
        return result;
    }
);
```

---

## User/Session Tracking

For multi-turn applications, use standard metadata fields `mlflow.trace.user` and `mlflow.trace.session`.

```typescript
app.post('/chat', async (req, res) => {
    const userId = req.header('X-User-ID') || 'anonymous';
    const sessionId = req.header('X-Session-ID') || 'default';
    const response = await chat(req.body.message, userId, sessionId);
    res.json({ response });
});

const chat = mlflow.trace(
    async (message: string, userId: string, sessionId: string) => {
        await mlflow.updateCurrentTrace({
            metadata: {
                "mlflow.trace.user": userId,
                "mlflow.trace.session": sessionId,
            },
        });
        return response;
    },
    { name: "chat", spanType: mlflow.SpanType.CHAIN }
);
```

---

## Combining Auto-Tracing with Custom Tracing

```typescript
import * as mlflow from "mlflow-tracing";
import { tracedOpenAI } from "mlflow-openai";
import { OpenAI } from "openai";

// Wrap OpenAI client for auto-tracing
const openai = tracedOpenAI(new OpenAI());

const retrieveDocuments = mlflow.trace(
    async (query: string): Promise<string[]> => {
        // Your retrieval logic
        return docs;
    },
    { name: "retrieve_documents", spanType: mlflow.SpanType.RETRIEVER }
);

const ragQuery = mlflow.trace(
    async (question: string): Promise<string> => {
        const docs = await retrieveDocuments(question);  // Custom traced function

        const response = await openai.chat.completions.create({  // Auto-traced
            model: "gpt-4o-mini",
            messages: [{ role: "user", content: formatPrompt(docs, question) }],
        });

        return response.choices[0].message.content || "";
    },
    { name: "rag_pipeline", spanType: mlflow.SpanType.CHAIN }
);
```

---

## Common Issues

**Traces not appearing?**
1. Verify `mlflow.init()` is called with correct tracking URI
2. Check experiment ID is set

**Traces not sent before exit?**
- Call `await mlflow.flushTraces()` before process exit to ensure all spans are sent
