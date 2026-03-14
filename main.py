"""
CI Analyser Agent: Webhook Receiver
----------------------------------
FastAPI server that listens for GitHub Action failures and triggers
the analysis agent.
"""
from fastapi import FastAPI, Request, BackgroundTasks
from patch_pilot import build_graph
import uvicorn
import os
import asyncio

app = FastAPI(title="CI Analyser Agent Receiver")

# Compile the graph once
agent = build_graph()

async def run_patch_pilot(repo_name: str, run_id: str, head_sha: str):
    """Background task to run the analysis agent."""
    initial_state = {
        "repo_name": repo_name,
        "run_id": str(run_id),
        "head_sha": head_sha,
        "commit_diff": "",
        "error_summary": "",
        "target_file": "",
        "proposed_patch": "",
        "logic_fix": "",
        "iteration_count": 0,
        "status": "analyzing",
        "logs": "",
        "test_output": ""
    }
    
    print(f"\n🚀 Starting CI Analyser Agent for {repo_name} (Run: {run_id})")
    async for output in agent.astream(initial_state):
        for key, value in output.items():
            status = value.get('status')
            print(f"✅ Node '{key}' completed.")
            
            if status == "success" and key == "post_comment":
                 print("\n✨ Analysis complete! Fix suggested and posted as a GitHub comment.")
            elif status == "failed":
                 print("\n❌ Analysis failed to process the logs.")

@app.post("/webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Handle GitHub Actions workflow_run.completed events.
    Expected payload contains action: 'completed' and conclusion: 'failure'.
    """
    try:
        payload = await request.json()
    except Exception:
        return {"status": "Error parsing JSON payload"}
    
    # Basic check for GitHub Action failure
    action = payload.get("action")
    workflow_run = payload.get("workflow_run", {})
    conclusion = workflow_run.get("conclusion")
    
    if action == "completed" and conclusion == "failure":
        repo_name = payload.get("repository", {}).get("full_name")
        run_id = workflow_run.get("id")
        head_sha = workflow_run.get("head_sha")
        
        if repo_name and run_id and head_sha:
            # Trigger the agent in the background
            background_tasks.add_task(run_patch_pilot, repo_name, run_id, head_sha)
            return {"status": "PatchPilot triggered", "run_id": run_id, "repo": repo_name}
        else:
            return {"status": "Error: Missing repo_name, run_id, or head_sha in payload"}
            
    return {"status": f"Ignored - Action is '{action}', conclusion is '{conclusion}' (Expected completed/failure)"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    print(f"Server starting on port {port}. Use ngrok to expose this port to GitHub.")
    uvicorn.run(app, host="0.0.0.0", port=port)
