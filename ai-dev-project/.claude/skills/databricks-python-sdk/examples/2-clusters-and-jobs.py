"""
Databricks SDK - Clusters and Jobs Examples

Clusters API: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/compute/clusters.html
Jobs API: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/jobs/jobs.html
"""

from datetime import timedelta
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.compute import ClusterSpec, AutoScale
from databricks.sdk.service.jobs import Task, NotebookTask, JobCluster

w = WorkspaceClient()

# =============================================================================
# CLUSTERS
# =============================================================================

# List all clusters
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/compute/clusters.html
for cluster in w.clusters.list():
    print(f"{cluster.cluster_name}: {cluster.state}")


# Get cluster details
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/compute/clusters.html
cluster = w.clusters.get(cluster_id="0123-456789-abcdef")
print(f"Cluster: {cluster.cluster_name}")
print(f"State: {cluster.state}")
print(f"Spark Version: {cluster.spark_version}")


# Select best Spark version and node type automatically
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/compute/clusters.html
spark_version = w.clusters.select_spark_version(latest=True, long_term_support=True)
node_type = w.clusters.select_node_type(local_disk=True, min_memory_gb=16)

print(f"Selected Spark: {spark_version}")
print(f"Selected Node: {node_type}")


# Create a cluster (non-blocking - returns Wait object)
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/compute/clusters.html
wait = w.clusters.create(
    cluster_name="my-test-cluster",
    spark_version=spark_version,
    node_type_id=node_type,
    num_workers=2,
    autotermination_minutes=30
)
# Wait for cluster to be running
cluster = wait.result()
print(f"Cluster {cluster.cluster_id} is now {cluster.state}")


# Create cluster with autoscaling (blocking call)
cluster = w.clusters.create_and_wait(
    cluster_name="autoscale-cluster",
    spark_version=spark_version,
    node_type_id=node_type,
    autoscale=AutoScale(min_workers=1, max_workers=4),
    timeout=timedelta(minutes=30)
)


# Start/stop/delete cluster
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/compute/clusters.html
w.clusters.start(cluster_id="...").result()  # Wait for running
w.clusters.stop(cluster_id="...")             # Non-blocking
w.clusters.delete(cluster_id="...")           # Terminates and removes


# Ensure cluster is running (starts if needed, waits if starting)
w.clusters.ensure_cluster_is_running(cluster_id="...")


# =============================================================================
# JOBS
# =============================================================================

# List all jobs
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/jobs/jobs.html
for job in w.jobs.list():
    print(f"{job.job_id}: {job.settings.name}")


# Get job details
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/jobs/jobs.html
job = w.jobs.get(job_id=123456)
print(f"Job: {job.settings.name}")
print(f"Tasks: {[t.task_key for t in job.settings.tasks]}")


# Create a job with notebook task
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/jobs/jobs.html
created = w.jobs.create(
    name="my-notebook-job",
    tasks=[
        Task(
            task_key="main",
            notebook_task=NotebookTask(
                notebook_path="/Users/me/my-notebook",
                base_parameters={"param1": "value1"}
            ),
            existing_cluster_id="0123-456789-abcdef"
        )
    ],
    max_concurrent_runs=1
)
print(f"Created job: {created.job_id}")


# Create job with job cluster (ephemeral)
created = w.jobs.create(
    name="job-with-ephemeral-cluster",
    job_clusters=[
        JobCluster(
            job_cluster_key="main-cluster",
            new_cluster=ClusterSpec(
                spark_version=spark_version,
                node_type_id=node_type,
                num_workers=2
            )
        )
    ],
    tasks=[
        Task(
            task_key="main",
            job_cluster_key="main-cluster",
            notebook_task=NotebookTask(notebook_path="/Users/me/notebook")
        )
    ]
)


# Run job immediately and wait for completion
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/jobs/jobs.html
run = w.jobs.run_now_and_wait(
    job_id=created.job_id,
    notebook_params={"date": "2024-01-01"},
    timeout=timedelta(hours=1)
)
print(f"Run {run.run_id} finished: {run.state.result_state}")


# Submit one-time run (without creating a job)
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/jobs/jobs.html
run = w.jobs.submit_and_wait(
    run_name="one-time-run",
    tasks=[
        Task(
            task_key="main",
            existing_cluster_id="...",
            notebook_task=NotebookTask(notebook_path="/Users/me/notebook")
        )
    ],
    timeout=timedelta(hours=1)
)


# List runs for a job
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/jobs/jobs.html
for run in w.jobs.list_runs(job_id=123456, active_only=True):
    print(f"Run {run.run_id}: {run.state.life_cycle_state}")


# Get run output
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/jobs/jobs.html
output = w.jobs.get_run_output(run_id=123456)
if output.notebook_output:
    print(f"Notebook result: {output.notebook_output.result}")


# Cancel a running job
w.jobs.cancel_run(run_id=123456).result()


# Update job settings
w.jobs.update(
    job_id=123456,
    new_settings=job.settings  # Modified settings object
)


# Delete job
w.jobs.delete(job_id=123456)
