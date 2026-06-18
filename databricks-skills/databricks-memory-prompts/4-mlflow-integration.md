# MLflow Integration

Deep integration between memory-aware prompts and MLflow Prompt Registry + Tracing.

## Overview

This guide shows how to:
1. Link prompts to the memories that shaped them
2. Log memory context in MLflow traces
3. Use experiments to compare memory variants
4. Track prompt evolution over time

## Prompt Registry Integration

### Register with Memory Context

```python
import mlflow
from typing import Optional
import json

def register_memory_prompt(
    name: str,
    template: str,
    task_description: str,
    enhancer: "MemoryPromptEnhancer",
    commit_message: str,
    alias: Optional[str] = None
) -> "mlflow.genai.Prompt":
    """
    Register a prompt with full memory context tracking.
    
    This creates:
    1. A new prompt version in the registry
    2. An MLflow run logging the memory context
    3. Links in the prompt_memory_links table
    """
    # Retrieve relevant memories
    context = enhancer.retrieve_context(task_description, k=10)
    
    # Build memory summary for tags
    memory_summary = {
        "decisions_count": len(context.get("decisions", [])),
        "patterns_count": len(context.get("patterns", [])),
        "feedback_count": len(context.get("feedback", [])),
        "top_decision": context["decisions"][0]["content"][:100] if context.get("decisions") else "",
        "top_pattern": context["patterns"][0]["content"][:100] if context.get("patterns") else "",
    }
    
    # Register the prompt
    prompt = mlflow.genai.register_prompt(
        name=name,
        template=template,
        commit_message=commit_message,
        tags={
            "memory_enhanced": "true",
            "task": task_description,
            **{f"memory.{k}": str(v) for k, v in memory_summary.items()}
        }
    )
    
    # Log detailed context in an MLflow run
    with mlflow.start_run(run_name=f"prompt_reg_{name.split('.')[-1]}_v{prompt.version}"):
        mlflow.log_param("prompt_name", name)
        mlflow.log_param("prompt_version", prompt.version)
        mlflow.log_param("task_description", task_description)
        
        # Log full memory context as artifact
        mlflow.log_dict(context, "memory_context.json")
        
        # Log individual memory IDs for lineage
        all_memory_ids = []
        for mem_type, memories in context.items():
            for i, mem in enumerate(memories):
                mlflow.log_param(f"{mem_type}_{i}_id", mem.get("id", "unknown"))
                all_memory_ids.append((mem_type, mem.get("id")))
        
        mlflow.log_metric("total_memories_used", len(all_memory_ids))
    
    # Record links in database
    _record_memory_links(name, prompt.version, all_memory_ids)
    
    # Set alias if provided
    if alias:
        mlflow.genai.set_prompt_alias(name=name, alias=alias, version=prompt.version)
    
    return prompt


def _record_memory_links(prompt_name: str, version: int, memory_ids: list):
    """Record which memories influenced this prompt version."""
    from pyspark.sql import SparkSession
    spark = SparkSession.builder.getOrCreate()
    
    for mem_type, mem_id in memory_ids:
        spark.sql(f"""
            INSERT INTO my_catalog.memory.prompt_memory_links
            (prompt_name, prompt_version, memory_type, memory_id, influence_score)
            VALUES ('{prompt_name}', {version}, '{mem_type}', '{mem_id}', 1.0)
        """)
```

### Load with Memory Refresh

```python
def load_memory_prompt(
    name_or_uri: str,
    enhancer: "MemoryPromptEnhancer",
    task_description: str,
    refresh_memory: bool = False
) -> tuple:
    """
    Load a prompt, optionally refreshing with latest memory.
    
    Returns:
        (prompt_template, memory_context)
    """
    # Load from registry
    prompt = mlflow.genai.load_prompt(name_or_uri)
    
    if refresh_memory:
        # Get fresh memory context
        context = enhancer.retrieve_context(task_description)
        # Enhance the template
        enhanced_template = enhancer.enhance_prompt(prompt.template, task_description)
        return enhanced_template, context
    else:
        return prompt.template, None
```

## Tracing Integration

### Memory-Aware Spans

```python
import mlflow
from mlflow import trace

@trace
def memory_enhanced_generation(
    input_text: str,
    task: str,
    enhancer: "MemoryPromptEnhancer",
    model: str = "databricks-meta-llama-3-3-70b-instruct"
):
    """Generate with memory context logged to trace."""
    
    # Retrieve memory
    with mlflow.start_span(name="memory_retrieval") as span:
        context = enhancer.retrieve_context(task)
        span.set_attributes({
            "memory.decisions_count": len(context.get("decisions", [])),
            "memory.patterns_count": len(context.get("patterns", [])),
            "memory.feedback_count": len(context.get("feedback", [])),
        })
        
        # Log individual memory IDs
        for mem_type, memories in context.items():
            for i, mem in enumerate(memories[:3]):  # Top 3 per type
                span.set_attribute(f"memory.{mem_type}_{i}", mem.get("id", ""))
    
    # Enhance prompt
    with mlflow.start_span(name="prompt_enhancement") as span:
        base_prompt = mlflow.genai.load_prompt(f"prompts:/catalog.schema.{task}@production")
        enhanced = enhancer.enhance_prompt(base_prompt.template, task)
        span.set_inputs({"base_prompt_length": len(base_prompt.template)})
        span.set_outputs({"enhanced_prompt_length": len(enhanced)})
    
    # Generate
    with mlflow.start_span(name="llm_generation") as span:
        from databricks.sdk import WorkspaceClient
        llm = WorkspaceClient().serving_endpoints.get_open_ai_client()
        
        response = llm.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": enhanced.format(input=input_text)}]
        )
        
        result = response.choices[0].message.content
        span.set_inputs({"input_text": input_text[:200]})
        span.set_outputs({"output": result[:200]})
    
    return result, context
```

### Trace Attributes for Memory

Standard attributes to include in traces:

```python
MEMORY_TRACE_ATTRIBUTES = {
    # Counts
    "memory.total_retrieved": "Total memories retrieved",
    "memory.decisions_count": "Number of decisions used",
    "memory.patterns_count": "Number of patterns used",
    "memory.feedback_count": "Number of feedback items used",
    
    # Confidence
    "memory.avg_confidence": "Average confidence of used memories",
    "memory.min_confidence": "Minimum confidence threshold applied",
    
    # IDs (for lineage)
    "memory.decision_ids": "Comma-separated decision IDs",
    "memory.pattern_ids": "Comma-separated pattern IDs",
    
    # Task scope
    "memory.task_scope": "Task scope filter applied",
}
```

## Experiment Tracking

### Compare Memory Variants

```python
def run_memory_experiment(
    task: str,
    test_inputs: list,
    enhancer: "MemoryPromptEnhancer",
    variants: list = ["no_memory", "decisions_only", "full_memory"]
):
    """
    Run an experiment comparing different memory configurations.
    """
    experiment_name = f"/memory_experiments/{task}"
    mlflow.set_experiment(experiment_name)
    
    base_prompt = mlflow.genai.load_prompt(f"prompts:/catalog.schema.{task}@production")
    
    results = {}
    
    for variant in variants:
        with mlflow.start_run(run_name=variant):
            mlflow.log_param("variant", variant)
            mlflow.log_param("task", task)
            mlflow.log_param("test_inputs_count", len(test_inputs))
            
            # Configure memory inclusion
            if variant == "no_memory":
                template = base_prompt.template
                memory_types = []
            elif variant == "decisions_only":
                template = enhancer.enhance_prompt(
                    base_prompt.template, task, include=["decisions"]
                )
                memory_types = ["decisions"]
            else:  # full_memory
                template = enhancer.enhance_prompt(base_prompt.template, task)
                memory_types = ["decisions", "patterns", "feedback"]
            
            mlflow.log_param("memory_types", ",".join(memory_types))
            mlflow.log_text(template, "enhanced_prompt.txt")
            
            # Run inference on test inputs
            outputs = []
            latencies = []
            
            for input_text in test_inputs:
                import time
                start = time.time()
                
                result = generate(template, input_text)  # Your generation function
                
                latencies.append(time.time() - start)
                outputs.append(result)
            
            # Log metrics
            mlflow.log_metric("avg_latency_ms", sum(latencies) / len(latencies) * 1000)
            mlflow.log_metric("p95_latency_ms", sorted(latencies)[int(len(latencies) * 0.95)] * 1000)
            
            # Log outputs for evaluation
            mlflow.log_dict(
                {"inputs": test_inputs, "outputs": outputs},
                "inference_results.json"
            )
            
            results[variant] = outputs
    
    return results
```

### Evaluate with MLflow Scorers

```python
from mlflow.genai.scorers import Correctness, Relevance

def evaluate_memory_impact(experiment_name: str):
    """Evaluate memory variants using MLflow scorers."""
    
    # Load runs from experiment
    runs = mlflow.search_runs(experiment_names=[experiment_name])
    
    for _, run in runs.iterrows():
        run_id = run["run_id"]
        variant = run["params.variant"]
        
        # Load inference results
        artifact_path = mlflow.artifacts.download_artifacts(
            run_id=run_id, artifact_path="inference_results.json"
        )
        with open(artifact_path) as f:
            results = json.load(f)
        
        # Build eval dataset
        eval_data = [
            {"inputs": inp, "outputs": out}
            for inp, out in zip(results["inputs"], results["outputs"])
        ]
        
        # Run evaluation
        eval_results = mlflow.genai.evaluate(
            data=eval_data,
            model=None,  # Outputs already generated
            scorers=[
                Correctness(),
                Relevance(),
            ]
        )
        
        # Log eval metrics back to run
        with mlflow.start_run(run_id=run_id):
            for metric, value in eval_results.metrics.items():
                mlflow.log_metric(f"eval_{metric}", value)
```

## Prompt Evolution Tracking

### View Prompt History with Memory

```python
def get_prompt_evolution(prompt_name: str) -> list:
    """
    Get the evolution of a prompt with memory context at each version.
    """
    from pyspark.sql import SparkSession
    spark = SparkSession.builder.getOrCreate()
    
    # Get all versions
    versions = mlflow.genai.search_prompts(name=prompt_name)
    
    evolution = []
    for v in versions:
        # Get memory links for this version
        links = spark.sql(f"""
            SELECT memory_type, memory_id, influence_score
            FROM my_catalog.memory.prompt_memory_links
            WHERE prompt_name = '{prompt_name}' AND prompt_version = {v.version}
        """).collect()
        
        # Get the actual memories
        memories = []
        for link in links:
            mem = spark.sql(f"""
                SELECT * FROM my_catalog.memory.{link.memory_type}s
                WHERE id = '{link.memory_id}'
            """).first()
            if mem:
                memories.append({
                    "type": link.memory_type,
                    "content": mem.get("decision") or mem.get("pattern") or mem.get("correction"),
                    "influence": link.influence_score
                })
        
        evolution.append({
            "version": v.version,
            "commit_message": v.commit_message,
            "created_at": v.creation_time,
            "memories_used": memories
        })
    
    return evolution
```

### Visualize in Dashboard

```sql
-- Prompt versions over time with memory counts
SELECT 
    p.prompt_name,
    p.prompt_version,
    p.created_at,
    COUNT(DISTINCT l.memory_id) AS memories_used,
    SUM(CASE WHEN l.memory_type = 'decision' THEN 1 ELSE 0 END) AS decisions,
    SUM(CASE WHEN l.memory_type = 'pattern' THEN 1 ELSE 0 END) AS patterns
FROM prompt_versions p
LEFT JOIN my_catalog.memory.prompt_memory_links l
    ON p.prompt_name = l.prompt_name AND p.prompt_version = l.prompt_version
GROUP BY 1, 2, 3
ORDER BY p.prompt_name, p.prompt_version;
```
