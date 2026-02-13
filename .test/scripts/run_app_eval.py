#!/usr/bin/env python3
"""Run integration tests for Databricks App skills by deploying to a real workspace.

Unlike run_eval.py (which runs code on clusters/warehouses), this script:
1. Extracts Python + YAML code blocks from ground truth test cases
2. Deploys each as a Databricks App
3. Verifies the app starts successfully
4. Reports pass/fail per test case
5. Cleans up all test apps

Usage:
    DATABRICKS_CONFIG_PROFILE=ffe python run_app_eval.py databricks-app-python [--test-ids id1 id2]
    DATABRICKS_CONFIG_PROFILE=ffe python run_app_eval.py databricks-app-python --keep  # Don't delete apps after
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

from _common import find_repo_root, print_result, handle_error, setup_path

setup_path()


def extract_code_blocks(response: str) -> dict[str, list[str]]:
    """Extract code blocks by language from a markdown response."""
    blocks = {}
    pattern = r"```(\w+)\n(.*?)```"
    for match in re.finditer(pattern, response, re.DOTALL):
        lang = match.group(1).lower()
        code = match.group(2).strip()
        if lang == "python":
            blocks.setdefault("python", []).append(code)
        elif lang == "yaml":
            blocks.setdefault("yaml", []).append(code)
        elif lang in ("bash", "shell", "sh"):
            blocks.setdefault("bash", []).append(code)
        elif lang == "text":
            blocks.setdefault("text", []).append(code)
    return blocks


def strip_value_from_env(yaml_content: str) -> str:
    """Strip env vars with valueFrom (resources not attached during testing).

    Keeps only the command section and any env vars with literal values.
    """
    try:
        data = yaml.safe_load(yaml_content)
        if not isinstance(data, dict):
            return yaml_content

        # Keep command
        result = {}
        if "command" in data:
            result["command"] = data["command"]

        # Filter env: only keep entries with literal 'value', drop 'valueFrom'
        if "env" in data and isinstance(data["env"], list):
            filtered_env = [
                e for e in data["env"]
                if isinstance(e, dict) and "value" in e and "valueFrom" not in e
            ]
            if filtered_env:
                result["env"] = filtered_env

        return yaml.dump(result, default_flow_style=False)
    except Exception:
        # If YAML parsing fails, just return the command portion
        return yaml_content


def deploy_test_app(
    workspace_client,
    app_name: str,
    python_code: str,
    app_yaml_content: str | None,
    requirements: str | None = None,
) -> dict:
    """Deploy a test app and return status.

    Returns dict with: success, app_name, url, status, error, logs
    """
    profile = os.environ.get("DATABRICKS_CONFIG_PROFILE", "DEFAULT")
    workspace_path = f"/Workspace/Users/{workspace_client.current_user.me().user_name}/skill-test-apps/{app_name}"

    # Write files to temp dir
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write app.py
        with open(os.path.join(tmpdir, "app.py"), "w") as f:
            f.write(python_code)

        # Write app.yaml — strip valueFrom env vars (resources not attached in test)
        # Only keep the command section so the app can start
        if app_yaml_content:
            yaml_content = strip_value_from_env(app_yaml_content)
            with open(os.path.join(tmpdir, "app.yaml"), "w") as f:
                f.write(yaml_content)
        else:
            # Auto-detect framework from imports and generate app.yaml
            yaml_content = detect_framework_yaml(python_code)
            with open(os.path.join(tmpdir, "app.yaml"), "w") as f:
                f.write(yaml_content)

        # Write requirements.txt if provided
        if requirements:
            with open(os.path.join(tmpdir, "requirements.txt"), "w") as f:
                f.write(requirements)

        # Upload to workspace
        result = subprocess.run(
            ["databricks", "workspace", "mkdirs", workspace_path, "--profile", profile],
            capture_output=True, text=True,
        )
        result = subprocess.run(
            ["databricks", "workspace", "import-dir", tmpdir, workspace_path, "--profile", profile, "--overwrite"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            return {"success": False, "app_name": app_name, "error": f"Upload failed: {result.stderr}"}

    # Create app
    result = subprocess.run(
        ["databricks", "apps", "create", app_name, "--profile", profile],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        if "already exists" in result.stderr.lower() or "already exists" in result.stdout.lower():
            pass  # App exists, we'll redeploy
        else:
            return {"success": False, "app_name": app_name, "error": f"Create failed: {result.stderr or result.stdout}"}

    # Deploy
    result = subprocess.run(
        ["databricks", "apps", "deploy", app_name, "--source-code-path", workspace_path, "--profile", profile],
        capture_output=True, text=True, timeout=300,
    )
    deploy_output = result.stdout + result.stderr
    if result.returncode != 0:
        return {
            "success": False,
            "app_name": app_name,
            "error": f"Deploy failed: {deploy_output}",
            "stage": "deploy",
        }

    # Parse deployment result
    try:
        deploy_info = json.loads(result.stdout)
        status = deploy_info.get("status", {}).get("state", "UNKNOWN")
        message = deploy_info.get("status", {}).get("message", "")
    except json.JSONDecodeError:
        status = "UNKNOWN"
        message = deploy_output

    # Get app info
    result = subprocess.run(
        ["databricks", "apps", "get", app_name, "--profile", profile],
        capture_output=True, text=True,
    )
    try:
        app_info = json.loads(result.stdout)
        app_status = app_info.get("app_status", {}).get("state", "UNKNOWN")
        url = app_info.get("url", "")
    except json.JSONDecodeError:
        app_status = "UNKNOWN"
        url = ""

    success = status == "SUCCEEDED" and app_status == "RUNNING"

    return {
        "success": success,
        "app_name": app_name,
        "url": url,
        "deploy_status": status,
        "app_status": app_status,
        "message": message,
    }


def delete_test_app(app_name: str) -> bool:
    """Delete a test app."""
    profile = os.environ.get("DATABRICKS_CONFIG_PROFILE", "DEFAULT")
    result = subprocess.run(
        ["databricks", "apps", "delete", app_name, "--profile", profile],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def detect_framework_yaml(python_code: str) -> str:
    """Auto-detect framework from Python imports and return app.yaml content."""
    code_lower = python_code.lower()

    if "import streamlit" in code_lower or "from streamlit" in code_lower:
        return (
            'command:\n  - "streamlit"\n  - "run"\n  - "app.py"\n'
            '  - "--server.port"\n  - "8080"\n  - "--server.address"\n'
            '  - "0.0.0.0"\n  - "--server.headless"\n  - "true"\n'
        )
    elif "import dash" in code_lower or "from dash" in code_lower:
        return 'command:\n  - "python"\n  - "app.py"\n'
    elif "import gradio" in code_lower or "from gradio" in code_lower:
        return 'command:\n  - "python"\n  - "app.py"\n'
    elif "from fastapi" in code_lower or "import fastapi" in code_lower:
        return (
            'command:\n  - "uvicorn"\n  - "app:app"\n'
            '  - "--host"\n  - "0.0.0.0"\n  - "--port"\n  - "8080"\n'
        )
    elif "from flask" in code_lower or "import flask" in code_lower:
        return (
            'command:\n  - "gunicorn"\n  - "app:app"\n'
            '  - "-w"\n  - "4"\n  - "-b"\n  - "0.0.0.0:8080"\n'
        )
    else:
        return 'command:\n  - "python"\n  - "app.py"\n'


def main():
    parser = argparse.ArgumentParser(description="Run app skill integration tests on Databricks")
    parser.add_argument("skill_name", help="Name of skill to evaluate (e.g., databricks-app-python)")
    parser.add_argument("--test-ids", nargs="+", help="Specific test IDs to run")
    parser.add_argument("--keep", action="store_true", help="Don't delete apps after testing")
    args = parser.parse_args()

    # Find repo root
    repo_root = find_repo_root()

    # Load ground truth
    gt_path = repo_root / ".test" / "skills" / args.skill_name / "ground_truth.yaml"
    if not gt_path.exists():
        sys.exit(handle_error(FileNotFoundError(f"No ground_truth.yaml at {gt_path}"), args.skill_name))

    with open(gt_path) as f:
        data = yaml.safe_load(f)

    test_cases = data.get("test_cases", [])
    if args.test_ids:
        test_cases = [t for t in test_cases if t["id"] in args.test_ids]

    # Set up Databricks client
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()

    print(f"Running {len(test_cases)} app integration tests on {w.config.host}")
    print(f"Profile: {os.environ.get('DATABRICKS_CONFIG_PROFILE', 'DEFAULT')}")
    print("=" * 60)

    results = []
    deployed_apps = []

    for tc in test_cases:
        test_id = tc["id"]
        prompt = tc.get("inputs", {}).get("prompt", "")
        response = tc.get("outputs", {}).get("response", "")

        print(f"\n--- {test_id} ---")
        print(f"Prompt: {prompt[:80]}...")

        # Extract code blocks
        blocks = extract_code_blocks(response)
        python_blocks = blocks.get("python", [])
        yaml_blocks = blocks.get("yaml", [])

        if not python_blocks:
            print(f"  SKIP: No Python code blocks found")
            results.append({"id": test_id, "status": "skipped", "reason": "no python code"})
            continue

        # Use first Python block as app.py, first YAML block as app.yaml
        python_code = python_blocks[0]
        app_yaml = yaml_blocks[0] if yaml_blocks else None

        # Extract requirements from text blocks or untagged blocks
        requirements = None
        text_blocks = blocks.get("text", [])
        for tb in text_blocks:
            # Any text block that looks like pip packages (one per line, no spaces)
            lines = [l.strip() for l in tb.strip().splitlines() if l.strip()]
            if lines and all(
                re.match(r'^[a-zA-Z0-9_\-\[\]>=<.,!]+$', l) for l in lines
            ):
                requirements = "\n".join(lines)

        # Deploy
        app_name = f"skill-test-{test_id.replace('_', '-')}"[:63]  # Max 63 chars
        print(f"  Deploying as: {app_name}")

        try:
            result = deploy_test_app(w, app_name, python_code, app_yaml, requirements)
            deployed_apps.append(app_name)

            if result["success"]:
                print(f"  PASS: {result.get('app_status')} @ {result.get('url', 'N/A')}")
            else:
                print(f"  FAIL: {result.get('error', result.get('message', 'unknown'))}")

            results.append({"id": test_id, **result})

        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({"id": test_id, "success": False, "error": str(e)})
            deployed_apps.append(app_name)  # Still try to clean up

    # Summary
    passed = sum(1 for r in results if r.get("success"))
    failed = sum(1 for r in results if not r.get("success") and r.get("status") != "skipped")
    skipped = sum(1 for r in results if r.get("status") == "skipped")
    total_deployable = passed + failed

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed, {skipped} skipped / {len(results)} total")

    # Compute metrics
    metrics = {
        "deploy_success_rate": passed / total_deployable if total_deployable > 0 else 0.0,
        "total_tests": float(len(results)),
        "passed": float(passed),
        "failed": float(failed),
        "skipped": float(skipped),
    }

    # Log to MLflow
    run_id = None
    try:
        import mlflow

        tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "databricks")
        experiment_name = os.environ.get(
            "MLFLOW_EXPERIMENT_NAME",
            f"/Users/{w.current_user.me().user_name}/skill-test",
        )
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(experiment_name)

        with mlflow.start_run(run_name=f"{args.skill_name}_app_eval"):
            mlflow.set_tags({
                "skill_name": args.skill_name,
                "evaluation_type": "app_deployment",
                "test_count": len(results),
                "profile": os.environ.get("DATABRICKS_CONFIG_PROFILE", "DEFAULT"),
                "host": w.config.host,
            })
            mlflow.log_metrics(metrics)
            mlflow.log_dict(
                {"results": results, "metrics": metrics},
                "app_eval_results.json",
            )
            run_id = mlflow.active_run().info.run_id

        print(f"\nMLflow run logged: {run_id}")
        print(f"  Experiment: {experiment_name}")
    except Exception as e:
        print(f"\nMLflow logging skipped: {e}")

    # Save baseline
    try:
        baselines_dir = repo_root / ".test" / "baselines" / args.skill_name
        baselines_dir.mkdir(parents=True, exist_ok=True)
        baseline_path = baselines_dir / "baseline.yaml"

        baseline_data = {
            "skill_name": args.skill_name,
            "evaluation_type": "app_deployment",
            "run_id": run_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "metrics": metrics,
            "test_count": len(results),
            "results_summary": [
                {"id": r["id"], "success": r.get("success", False), "status": r.get("app_status", r.get("status", "unknown"))}
                for r in results
            ],
        }
        with open(baseline_path, "w") as f:
            yaml.dump(baseline_data, f, default_flow_style=False)

        print(f"Baseline saved: {baseline_path}")
    except Exception as e:
        print(f"Baseline save skipped: {e}")

    # Cleanup
    if not args.keep and deployed_apps:
        print(f"\nCleaning up {len(deployed_apps)} test apps...")
        for app_name in deployed_apps:
            ok = delete_test_app(app_name)
            print(f"  {'OK' if ok else 'FAIL'}: {app_name}")

    # Output full results
    output = {
        "success": failed == 0,
        "skill_name": args.skill_name,
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "mlflow_run_id": run_id,
        "metrics": metrics,
        "results": results,
    }
    sys.exit(print_result(output))


if __name__ == "__main__":
    main()
