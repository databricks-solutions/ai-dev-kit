"""
Simple Databricks App for MCP Integration Tests.

This is a minimal Gradio app that just displays a greeting.
"""

import gradio as gr


def greet(name: str) -> str:
    """Return a greeting message."""
    return f"Hello, {name}! This is a test app for MCP integration tests."


# Create simple Gradio interface
demo = gr.Interface(
    fn=greet,
    inputs=gr.Textbox(label="Your Name", placeholder="Enter your name"),
    outputs=gr.Textbox(label="Greeting"),
    title="MCP Test App",
    description="A simple test app for integration tests.",
)

# For Databricks Apps
app = demo.app
