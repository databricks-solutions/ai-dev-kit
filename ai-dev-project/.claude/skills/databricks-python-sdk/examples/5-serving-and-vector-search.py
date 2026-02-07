"""
Databricks SDK - Model Serving and Vector Search Examples

Serving Endpoints: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/serving/serving_endpoints.html
Vector Search: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/vectorsearch/vector_search_indexes.html
"""

from datetime import timedelta
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    EndpointCoreConfigInput,
    ServedEntityInput,
    TrafficConfig,
    Route,
)

w = WorkspaceClient()

# =============================================================================
# MODEL SERVING ENDPOINTS
# =============================================================================

# List all serving endpoints
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/serving/serving_endpoints.html
for endpoint in w.serving_endpoints.list():
    print(f"{endpoint.name}: {endpoint.state}")


# Get endpoint details
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/serving/serving_endpoints.html
endpoint = w.serving_endpoints.get(name="my-endpoint")
print(f"Endpoint: {endpoint.name}")
print(f"State: {endpoint.state}")
if endpoint.config:
    for entity in endpoint.config.served_entities:
        print(f"  Model: {entity.entity_name} v{entity.entity_version}")


# Create a serving endpoint for a Unity Catalog model
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/serving/serving_endpoints.html
created = w.serving_endpoints.create_and_wait(
    name="my-model-endpoint",
    config=EndpointCoreConfigInput(
        served_entities=[
            ServedEntityInput(
                entity_name="main.ml.my_model",  # Unity Catalog model path
                entity_version="1",
                workload_size="Small",
                scale_to_zero_enabled=True,
            )
        ],
        traffic_config=TrafficConfig(
            routes=[
                Route(served_model_name="my_model-1", traffic_percentage=100)
            ]
        ),
    ),
    timeout=timedelta(minutes=30)
)


# Query endpoint (for custom models)
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/serving/serving_endpoints.html
response = w.serving_endpoints.query(
    name="my-model-endpoint",
    inputs=[{"feature1": 1.0, "feature2": "value"}]
)
print(f"Predictions: {response.predictions}")


# Query chat/completions endpoint (LLM)
response = w.serving_endpoints.query(
    name="my-llm-endpoint",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"}
    ],
    max_tokens=100
)
print(f"Response: {response.choices[0].message.content}")


# Query embeddings endpoint
response = w.serving_endpoints.query(
    name="my-embedding-endpoint",
    input=["text to embed", "another text"]
)
print(f"Embeddings: {response.data}")


# Get OpenAI-compatible client for Databricks endpoints
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/serving/serving_endpoints.html
openai_client = w.serving_endpoints.get_open_ai_client()
# Now use standard OpenAI SDK:
# completion = openai_client.chat.completions.create(
#     model="databricks-meta-llama-3-1-70b-instruct",
#     messages=[{"role": "user", "content": "Hello!"}]
# )


# Update endpoint configuration
w.serving_endpoints.update_config(
    name="my-endpoint",
    served_entities=[
        ServedEntityInput(
            entity_name="main.ml.my_model",
            entity_version="2",  # Update to new version
            workload_size="Medium",
            scale_to_zero_enabled=True,
        )
    ]
).result()


# Get endpoint logs
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/serving/serving_endpoints.html
logs = w.serving_endpoints.logs(
    name="my-endpoint",
    served_model_name="my_model-1"
)
print(logs.logs)


# Export metrics (Prometheus format)
metrics = w.serving_endpoints.export_metrics(name="my-endpoint")
print(metrics.contents)


# Delete endpoint
w.serving_endpoints.delete(name="my-endpoint")


# =============================================================================
# VECTOR SEARCH
# =============================================================================

# List vector search endpoints
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/vectorsearch/vector_search_endpoints.html
for vs_endpoint in w.vector_search_endpoints.list_endpoints():
    print(f"{vs_endpoint.name}: {vs_endpoint.endpoint_status}")


# List indexes on an endpoint
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/vectorsearch/vector_search_indexes.html
for index in w.vector_search_indexes.list_indexes(endpoint_name="my-vs-endpoint"):
    print(f"Index: {index.name}")


# Get index details
index = w.vector_search_indexes.get_index(index_name="main.default.my_index")
print(f"Index: {index.name}")
print(f"Primary Key: {index.primary_key}")
print(f"Status: {index.status}")


# Query vector search index with text
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/vectorsearch/vector_search_indexes.html
results = w.vector_search_indexes.query_index(
    index_name="main.default.my_index",
    columns=["id", "text", "metadata"],
    query_text="What is machine learning?",
    num_results=5,
    filters_json='{"category": "ai"}'  # Optional filter
)

for doc in results.result.data_array:
    print(f"Score: {doc[-1]}, Text: {doc[1][:100]}...")


# Query with embedding vector directly
results = w.vector_search_indexes.query_index(
    index_name="main.default.my_index",
    columns=["id", "text"],
    query_vector=[0.1, 0.2, 0.3, ...],  # Your embedding vector
    num_results=10
)


# Get next page of results
if results.next_page_token:
    next_results = w.vector_search_indexes.query_next_page(
        index_name="main.default.my_index",
        page_token=results.next_page_token
    )


# Upsert data into a Direct Vector Access index
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/vectorsearch/vector_search_indexes.html
import json
w.vector_search_indexes.upsert_data_vector_index(
    index_name="main.default.direct_index",
    inputs_json=json.dumps([
        {"id": "1", "text": "Hello world", "embedding": [0.1, 0.2, 0.3]},
        {"id": "2", "text": "Another doc", "embedding": [0.4, 0.5, 0.6]},
    ])
)


# Delete data from Direct Vector Access index
w.vector_search_indexes.delete_data_vector_index(
    index_name="main.default.direct_index",
    primary_keys=["1", "2"]
)


# Sync a Delta Sync index (trigger refresh from source table)
w.vector_search_indexes.sync_index(index_name="main.default.delta_sync_index")


# Scan index (retrieve all entries)
scan_result = w.vector_search_indexes.scan_index(
    index_name="main.default.my_index",
    num_results=100
)
for entry in scan_result.data:
    print(entry)
