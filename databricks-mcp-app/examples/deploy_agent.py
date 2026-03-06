#!/usr/bin/env python
"""
Deploy the AI Dev Kit Agent to Databricks Model Serving.

This script logs the agent to MLflow and deploys it as a serving endpoint,
allowing it to be used from the Databricks UI or via API.

Based on the Databricks managed MCP documentation:
https://learn.microsoft.com/en-us/azure/databricks/generative-ai/mcp/managed-mcp

Usage:
    python deploy_agent.py --profile <profile> --mcp-url <url> --model-name <name>
"""

import os
import argparse

import mlflow
from mlflow.models.resources import DatabricksServingEndpoint, DatabricksApp
from databricks.sdk import WorkspaceClient
from databricks import agents


def deploy_agent(
    profile: str,
    mcp_url: str,
    model_name: str,
    llm_endpoint: str = "databricks-claude-sonnet-4-5",
):
    """Deploy the AI Dev Kit agent to Databricks."""
    
    print("=" * 60)
    print("Deploying AI Dev Kit Agent")
    print("=" * 60)
    print(f"Profile: {profile}")
    print(f"MCP URL: {mcp_url}")
    print(f"Model Name: {model_name}")
    print(f"LLM Endpoint: {llm_endpoint}")
    print()
    
    # Configure workspace client
    workspace_client = WorkspaceClient(profile=profile)
    current_user = workspace_client.current_user.me().user_name
    
    # Configure MLflow
    mlflow.set_tracking_uri(f"databricks://{profile}")
    mlflow.set_registry_uri(f"databricks-uc://{profile}")
    mlflow.set_experiment(f"/Users/{current_user}/ai-dev-kit-agent")
    os.environ["DATABRICKS_CONFIG_PROFILE"] = profile
    
    # Set environment variables for the agent
    os.environ["AI_DEV_KIT_MCP_URL"] = mcp_url
    os.environ["LLM_ENDPOINT_NAME"] = llm_endpoint
    os.environ["DATABRICKS_CLI_PROFILE"] = profile
    
    # Define resources the agent needs
    resources = [
        DatabricksServingEndpoint(endpoint_name=llm_endpoint),
        # Add the MCP app as a resource
        # DatabricksApp(app_name="ai-dev-kit-mcp"),
    ]
    
    print("Logging agent to MLflow...")
    
    # Get the path to the agent script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    agent_script = os.path.join(script_dir, "agent_example.py")
    
    with mlflow.start_run():
        logged_model_info = mlflow.pyfunc.log_model(
            artifact_path="ai_dev_kit_agent",
            python_model=agent_script,
            resources=resources,
        )
    
    print(f"Logged model: {logged_model_info.model_uri}")
    print()
    
    # Register the model
    print(f"Registering model as {model_name}...")
    registered_model = mlflow.register_model(
        logged_model_info.model_uri, 
        model_name
    )
    print(f"Registered version: {registered_model.version}")
    print()
    
    # Deploy the agent
    print("Deploying agent...")
    deployment = agents.deploy(
        model_name=model_name,
        model_version=registered_model.version,
    )
    
    print()
    print("=" * 60)
    print("Deployment Complete!")
    print("=" * 60)
    print()
    print(f"Model: {model_name}")
    print(f"Version: {registered_model.version}")
    print()
    print("The agent is now available in your Databricks workspace.")
    print("You can find it under: Machine Learning > Serving")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Deploy AI Dev Kit Agent to Databricks"
    )
    parser.add_argument(
        "--profile", "-p",
        required=True,
        help="Databricks CLI profile name"
    )
    parser.add_argument(
        "--mcp-url", "-u",
        required=True,
        help="AI Dev Kit MCP Server URL (e.g., https://app.apps.databricks.com/mcp)"
    )
    parser.add_argument(
        "--model-name", "-m",
        default="main.default.ai_dev_kit_agent",
        help="Unity Catalog model name (default: main.default.ai_dev_kit_agent)"
    )
    parser.add_argument(
        "--llm-endpoint", "-l",
        default="databricks-claude-sonnet-4-5",
        help="LLM serving endpoint name"
    )
    
    args = parser.parse_args()
    
    deploy_agent(
        profile=args.profile,
        mcp_url=args.mcp_url,
        model_name=args.model_name,
        llm_endpoint=args.llm_endpoint,
    )


if __name__ == "__main__":
    main()
