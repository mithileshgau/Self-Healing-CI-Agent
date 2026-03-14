"""
PatchPilot: CI Failure Analyzer
-------------------------------
This script uses LangGraph and Gemini to analyze GitHub Action failure logs
and categorize the root cause (Code, Test, Environment, or Flaky).
"""
import os
from typing import TypedDict, Literal
from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from tools import fetch_github_logs, post_commit_comment, get_github_file_content, get_commit_diff
from dotenv import load_dotenv

load_dotenv()

# 1. State Definition (Pydantic style TypedDict for LangGraph)
class CIState(TypedDict):
    repo_name: str
    run_id: str
    head_sha: str
    commit_diff: str
    error_summary: str
    target_file: str
    proposed_patch: str
    logic_fix: str
    iteration_count: int
    status: Literal["analyzing", "fixing", "validating", "success", "failed"]
    logs: str
    test_output: str

# LLM Configuration
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=os.getenv("GOOGLE_API_KEY"))

# 2. Node Architecture

async def log_analyzer_node(state: CIState) -> CIState:
    print("---ANALYZING LOGS---")
    raw_logs = await fetch_github_logs(state["repo_name"], state["run_id"])
    logs = str(raw_logs)
    
    print("\n--- [DEBUG] LOGS FETCHED FROM GITHUB ---")
    truncated_logs = logs[-8000:] if len(logs) > 8000 else logs
    print("... (Skipping startup logs) ...")
    print(truncated_logs)
    print("----------------------------------------\n")
    
    os.makedirs("agent_patches", exist_ok=True)
    raw_logs_filename = f"agent_patches/raw_logs_{state['run_id']}.txt"
    try:
        with open(raw_logs_filename, "w", encoding='utf-8') as f:
            f.write(logs)
        print(f"--- [DEBUG] Saved raw logs to {raw_logs_filename} ---")
    except Exception as e:
        print(f"--- [DEBUG] Could not save raw logs to disk: {e} ---")
    
    # Fetch the commit diff for more context
    print("---FETCHING COMMIT DIFF---")
    commit_diff = get_commit_diff(state["repo_name"], state["head_sha"])
    
    prompt = f"""
    Analyze the following GitHub Action logs and the commit diff that triggered the run.
    
    Logs (last 8000 chars):
    {truncated_logs}
    
    Commit Diff:
    {commit_diff}

    As a Senior DevOps and Software Engineer, identify the root cause of this failure. 
    It could be any of the following:
    1. A bug in the application source code (e.g., logic error, typo).
    2. A broken or outdated test case.
    3. An environment issue (e.g., missing secrets, wrong version of language/dependency).
    4. A flaky test or infrastructure failure.

    Provide a concise summary explaining:
    - WHAT failed.
    - WHY it failed.
    - WHICH files or configurations are likely involved.

    Return your response IN EXACTLY THIS FORMAT AND NOTHING ELSE:
    Summary: <concise_explanation_of_root_cause>
    Cause: <Code|Test|Environment|Flaky>
    File: <primary_file_to_check_or_fix>
    """
    
    response = llm.invoke([HumanMessage(content=prompt)])
    content = response.content
    
    print("\n--- [DEBUG] RAW GEMINI RESPONSE ---")
    print(content)
    print("----------------------------------\n")
    
    # Simple extraction logic
    analysis_summary = "Unknown"
    cause_type = "Unknown"
    target_file = "Unknown"
    
    for line in content.split("\n"):
        if line.startswith("Summary:"):
            analysis_summary = line.replace("Summary:", "").strip()
        elif line.startswith("Cause:"):
            cause_type = line.replace("Cause:", "").strip()
        elif line.startswith("File:"):
            target_file = line.replace("File:", "").strip()
            
    print("\n--- [DEBUG] ANALYSIS RESULTS ---")
    print(f"Analysis Summary: {analysis_summary}")
    print(f"Root Cause Category: {cause_type}")
    print(f"Target File/Config: {target_file}")
    print("--------------------------------\n")
            
    return {
        **state,
        "error_summary": analysis_summary,
        "target_file": target_file,
        "commit_diff": commit_diff,
        "status": "fixing",
        "logs": logs
    }

async def fix_generator_node(state: CIState) -> CIState:
    print("---GENERATING SUGGESTED FIX---")
    # Fetch file content from GitHub instead of local filesystem
    source_code = get_github_file_content(state["repo_name"], state["target_file"], ref=state["head_sha"])
    
    # Handle fetch errors gracefully
    if source_code.startswith("Error"):
        print(f"--- [WARNING] Could not fetch source code for {state['target_file']}. Proceeding with logs and diff only. ---")
        source_code_context = "[Could not fetch source code from GitHub]"
    else:
        source_code_context = source_code

    prompt = f"""
    You are a Senior AI Engineer. Your goal is to propose a fix for a CI failure.
    You have access to the error summary, the commit diff, and (optionally) the source code of the target file.
    
    Error: {state["error_summary"]}
    File Path: {state["target_file"]}
    
    Commit Diff:
    {state["commit_diff"]}
    
    Source Code context for {state["target_file"]}:
    {source_code_context}
    
    Propose a concise fix for this issue. 
    1. If the source code is available, provide the specific code changes.
    2. If the source code is NOT available, describe the intended fix based on the logs and commit diff.
    3. Explain what changed and why.
    """
    
    response = llm.invoke([HumanMessage(content=prompt)])
    logic_fix = response.content
    
    print("\n--- [DEBUG] SUGGESTED FIX ---")
    print(logic_fix)
    print("------------------------------\n")
    
    return {
        **state,
        "logic_fix": logic_fix,
        "status": "success"
    }

async def comment_exporter_node(state: CIState) -> CIState:
    print("---POSTING GITHUB COMMENT---")
    
    comment_body = f"""
### 🚀 PatchPilot Analysis Results
**Root Cause Summary:** {state['error_summary']}
**Target File:** `{state['target_file']}`

**Suggested Fix:**
{state['logic_fix']}

*This analysis was generated automatically by PatchPilot.*
"""
    
    result = post_commit_comment(state["repo_name"], state["head_sha"], comment_body)
    print(result)
    
    return {
        **state,
        "status": "success"
    }

# 3. Graph Logic & Edges

def build_graph():
    workflow = StateGraph(CIState)
    
    workflow.add_node("analyze", log_analyzer_node)
    workflow.add_node("generate_fix", fix_generator_node)
    workflow.add_node("post_comment", comment_exporter_node)
    
    workflow.set_entry_point("analyze")
    workflow.add_edge("analyze", "generate_fix")
    workflow.add_edge("generate_fix", "post_comment")
    workflow.add_edge("post_comment", END)
    
    return workflow.compile()
