---
name: mlflow-onboarding
description: Onboards users to MLflow by determining their use case (GenAI agents/apps or traditional ML/deep learning) and guiding them through relevant quickstart tutorials and initial integration. If an experiment ID is available, it should be supplied as input to help determine the use case. Use when the user asks to get started with MLflow, set up tracking, add observability, or integrate MLflow into their project. Triggers on "get started with MLflow", "set up MLflow", "onboard to MLflow", "add MLflow to my project", "how do I use MLflow".
---

# MLflow Onboarding

MLflow supports two broad use cases that require different onboarding paths:

- **GenAI applications and agents**: LLM-powered apps, chatbots, RAG pipelines, tool-calling agents. Key MLflow features include **tracing** for observability, **evaluation** with LLM judges, and **prompt management**, among others.
- **Traditional ML / deep learning models**: scikit-learn, PyTorch, TensorFlow, XGBoost, etc. Key MLflow features include **experiment tracking** (parameters, metrics, artifacts), **model logging**, and **model deployment**, among others.

Determining which use case applies is the first and most important step. The onboarding path, quickstart tutorials, and integration steps differ significantly between the two.

## Step 1: Determine the Use Case

Before recommending tutorials or integration steps, determine which use case the user is working on. Use the signals below, checking them in order. **If the signals are ambiguous or absent, you MUST ask the user directly.**

### Signal 1: Check the Codebase

Search the user's project for imports and usage patterns that indicate the use case:

**GenAI indicators** (any of these suggest GenAI):
- Imports from LLM client libraries: `openai`, `anthropic`, `google.generativeai`, `langchain`, `langchain_openai`, `langgraph`, `llamaindex`, `litellm`, `autogen`, `crewai`, `dspy`
- Imports from MLflow GenAI modules: `mlflow.genai`, `mlflow.tracing`, `mlflow.openai`, `mlflow.langchain`
- Usage of chat completions, embeddings, or agent frameworks
- Prompt templates or prompt engineering code

**Traditional ML indicators** (any of these suggest ML):
- Imports from ML frameworks: `sklearn`, `torch`, `tensorflow`, `keras`, `xgboost`, `lightgbm`, `catboost`, `statsmodels`, `scipy`
- Imports from MLflow ML modules: `mlflow.sklearn`, `mlflow.pytorch`, `mlflow.tensorflow`
- Model training loops, `.fit()` calls, hyperparameter tuning code
- Dataset loading with tabular/image/time-series data

```bash
# Search for GenAI indicators
grep -rl --include='*.py' -E '(import openai|import anthropic|from langchain|from langgraph|import litellm|from mlflow\.genai|from mlflow\.tracing|mlflow\.openai|mlflow\.langchain|ChatCompletion|chat\.completions)' .

# Search for ML indicators
grep -rl --include='*.py' -E '(from sklearn|import torch|import tensorflow|import keras|import xgboost|import lightgbm|mlflow\.sklearn|mlflow\.pytorch|mlflow\.tensorflow|\.fit\()' .
```

### Signal 2: Check the Experiment Type Tag

If the codebase or project directory is the MLflow repository itself, skip to Signal 3 — the MLflow repo contains code for all use cases and does not indicate the user's intent.

If the experiment ID is known, check its `mlflow.experimentKind` tag. This tag is set by MLflow to indicate the experiment type:

```bash
mlflow experiments get --experiment-id <EXPERIMENT_ID> --output json > /tmp/exp_detail.json
jq -r '.tags["mlflow.experimentKind"] // "not set"' /tmp/exp_detail.json
```

- **`genai_development`** → GenAI use case
- **`custom_model_development`** → Traditional ML use case
- **Not set** → Proceed to Signal 3

If the experiment ID is not known, skip to Signal 3.

### Signal 3: Ask the User

If the codebase and experiment signals are inconclusive, ask directly:

> Are you building a **GenAI application** (e.g., an LLM-powered chatbot, RAG pipeline, or tool-calling agent) or a **traditional ML/deep learning model** (e.g., training a classifier, regression model, or neural network)?

**Do not guess.** The onboarding paths are different enough that starting down the wrong one wastes the user's time.

## Step 2: Recommend Quickstart Tutorials

Once the use case is determined, recommend the appropriate quickstart tutorials from the MLflow documentation. Present them to the user and ask if they'd like to follow along or jump directly to integrating MLflow into their project.

### GenAI Path

The MLflow GenAI documentation is at: https://mlflow.org/docs/latest/genai/getting-started/

Choose the most relevant tutorials based on the user's context and what they've told you. Available tutorials include:

- **Tracing Quickstart** (https://mlflow.org/docs/latest/genai/tracing/quickstart/) — Enabling automatic tracing for LLM calls. Covers starting an MLflow server, creating an experiment, enabling autologging, and viewing traces in the UI.
  - Python + OpenAI variant: https://mlflow.org/docs/latest/genai/tracing/quickstart/python-openai/
  - TypeScript + OpenAI variant: https://mlflow.org/docs/latest/genai/tracing/quickstart/typescript-openai
  - OpenTelemetry (language-agnostic) variant: also linked from the quickstart page
- **Evaluation Quickstart** (https://mlflow.org/docs/latest/genai/eval-monitor/quickstart/) — Evaluating GenAI application quality using LLM judges (scorers). Covers defining datasets, prediction functions, and built-in + custom scorers.
- **Version Tracking Quickstart** (https://mlflow.org/docs/latest/genai/version-tracking/quickstart/) — Prompt management, application versioning, and connecting tracing to versioned prompts.

If none of these match the user's needs, look up the MLflow GenAI documentation for more relevant guides.

### Traditional ML Path

The MLflow ML documentation is at: https://mlflow.org/docs/latest/ml/getting-started/

Choose the most relevant tutorials based on the user's context and what they've told you. Available tutorials include:

- **Tracking Quickstart** (https://mlflow.org/docs/latest/ml/tracking/quickstart/) — Experiment tracking with scikit-learn: autologging, manual parameter/metric/model logging, and exploring results in the MLflow UI.
- **Deep Learning Tutorial** (https://mlflow.org/docs/latest/ml/getting-started/deep-learning/) — Training a PyTorch model with MLflow logging: parameters, metrics, checkpoints, and system metrics (GPU utilization, memory).
- **Hyperparameter Tuning Tutorial** (https://mlflow.org/docs/latest/ml/getting-started/hyperparameter-tuning/) — Running hyperparameter searches with Optuna + MLflow, comparing results, and selecting the best model.

If none of these match the user's needs, look up the MLflow ML documentation for more relevant guides.

## Step 3: Integrate MLflow into the User's Project

After the user has reviewed the quickstart tutorials (or opted to skip them), offer to help integrate MLflow directly into their codebase. **Always ask for the user's consent before making changes to their code.**

### GenAI Integration

The core integration for GenAI apps is **tracing** — capturing LLM calls, tool invocations, and agent steps automatically.

**If asked to create an example project:** Do not assume the user has LLM API keys (e.g., OpenAI, Anthropic). Instead, create traces with mock data using `@mlflow.trace` and `mlflow.start_span()` to demonstrate tracing without requiring external API access. For example:

```python
import mlflow

mlflow.set_experiment("example-genai-app")

@mlflow.trace
def mock_chat(query: str) -> str:
    with mlflow.start_span(name="retrieve_context") as span:
        context = "Mock retrieved context for: " + query
        span.set_inputs({"query": query})
        span.set_outputs({"context": context})
    with mlflow.start_span(name="generate_response") as span:
        response = "Mock response based on: " + context
        span.set_inputs({"context": context, "query": query})
        span.set_outputs({"response": response})
    return response

mock_chat("What is MLflow?")
```

**What to set up (for an existing project):**

1. **Autologging** — If the user's code uses a supported framework, a single line automatically traces all calls to their LLM provider. See https://mlflow.org/docs/latest/genai/tracing/ for the full list of supported providers. If the provider is supported:

   ```python
   import mlflow

   # Pick the one that matches the user's LLM provider:
   mlflow.openai.autolog()       # OpenAI SDK
   mlflow.anthropic.autolog()    # Anthropic SDK
   mlflow.langchain.autolog()    # LangChain / LangGraph
   mlflow.litellm.autolog()      # LiteLLM
   ```

   Add this call once at application startup (e.g., top of `main.py`, `app.py`, or the entry point module). It must execute before any LLM calls are made.

   If the provider is **not** supported by autologging, skip to step 3 (Custom tracing) and use `@mlflow.trace` to manually instrument the relevant functions.

2. **Experiment configuration** — Set the experiment so traces are organized:

   ```python
   mlflow.set_experiment("my-genai-app")
   ```

   Or via environment variable: `export MLFLOW_EXPERIMENT_NAME="my-genai-app"`

3. **Custom tracing** (optional) — For functions that aren't automatically traced (custom tools, business logic), use the `@mlflow.trace` decorator:

   ```python
   @mlflow.trace
   def my_custom_tool(query: str) -> str:
       # ... tool logic ...
       return result
   ```

**Where to add it:** Find the application's entry point or initialization module and add the autologging call there. Search for the main LLM client instantiation (e.g., `openai.OpenAI()`, `ChatOpenAI()`) to find the right location.

### Traditional ML Integration

The core integration for ML is **experiment tracking** — capturing parameters, metrics, and models from training runs.

**What to set up:**

1. **Autologging** — If the user's code uses a supported framework, a single line automatically logs parameters, metrics, and models during training. See https://mlflow.org/docs/latest/ml/ for the full list of supported frameworks. If the framework is supported:

   ```python
   import mlflow

   # Pick the one that matches the user's ML framework:
   mlflow.sklearn.autolog()      # scikit-learn
   mlflow.pytorch.autolog()      # PyTorch / PyTorch Lightning
   mlflow.tensorflow.autolog()   # TensorFlow / Keras
   mlflow.xgboost.autolog()      # XGBoost
   mlflow.lightgbm.autolog()     # LightGBM
   ```

   Add this call once before training starts. It automatically captures `model.fit()` calls, logged metrics, and model artifacts.

   If the framework is **not** supported by autologging, skip to step 3 (Manual logging) and use `mlflow.log_param()`, `mlflow.log_metric()`, and `mlflow.log_artifact()` to log data explicitly.

2. **Experiment configuration** — Set the experiment so runs are organized:

   ```python
   mlflow.set_experiment("my-ml-experiment")
   ```

   Or via environment variable: `export MLFLOW_EXPERIMENT_NAME="my-ml-experiment"`

3. **Manual logging** (optional) — For metrics or parameters not captured by autologging:

   ```python
   with mlflow.start_run():
       mlflow.log_param("custom_param", value)
       mlflow.log_metric("custom_metric", value)
   ```

**Where to add it:** Find the training script or module where `model.fit()` (or equivalent) is called. Add the autologging call before the training loop begins.

## Verification

After integration, verify that MLflow is capturing data correctly:

### GenAI Verification

1. Run the application and trigger at least one LLM call
2. Check for traces:
   ```bash
   mlflow traces search \
     --experiment-id <EXPERIMENT_ID> \
     --max-results 5 \
     --extract-fields 'info.trace_id,info.state,info.request_time' \
     --output json > /tmp/verify_traces.json
   jq '.traces | length' /tmp/verify_traces.json
   ```
3. If traces appear, open the MLflow UI to inspect them visually

### ML Verification

1. Run the training script
2. Check for runs:
   ```bash
   mlflow runs search \
     --experiment-id <EXPERIMENT_ID> \
     --max-results 5 \
     --output json > /tmp/verify_runs.json
   jq '.runs | length' /tmp/verify_runs.json
   ```
3. If runs appear, open the MLflow UI to inspect logged parameters, metrics, and artifacts
