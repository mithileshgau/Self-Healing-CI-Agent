"""
PatchPilot: Shared Tools & Utilities
------------------------------------
Contains helper functions for interacting with GitHub APIs,
reading from the local filesystem, and running shell commands.
"""
import os
import httpx
import sys
import subprocess
from github import Github
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# --- Configuration & Auth ---
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
gh = Github(GITHUB_TOKEN) if GITHUB_TOKEN else None

# For local development, we assume all repos are in the same parent directory.
# REPO_BASE_PATH is the parent directory of this agent's directory.
REPO_BASE_PATH = os.path.dirname(os.getcwd())

def get_local_repo_path(repo_name: str) -> str:
    """Get the local filesystem path for a given repo name (e.g., 'user/repo' -> 'd:/Coding/repo')."""
    repo_folder = repo_name.split("/")[-1]
    return os.path.join(REPO_BASE_PATH, repo_folder)

# --- GitHub API Helpers ---

async def fetch_github_logs(repo_name: str, run_id: str) -> str:
    """Fetch raw logs for a specific GitHub Action run."""
    if not GITHUB_TOKEN:
        return "Error: GITHUB_TOKEN not set."
    
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    
    try:
        async with httpx.AsyncClient() as client:
            # 1. Fetch the jobs for this run
            jobs_url = f"https://api.github.com/repos/{repo_name}/actions/runs/{run_id}/jobs"
            jobs_response = await client.get(jobs_url, headers=headers)
            
            if jobs_response.status_code != 200:
                return f"Error fetching jobs: {jobs_response.status_code} - {jobs_response.text}"
                
            jobs_data = jobs_response.json().get("jobs", [])
            failed_jobs = [j for j in jobs_data if j.get("conclusion") == "failure"]
            
            if not failed_jobs:
                return "Error: No failed jobs found in this run."
            
            all_logs = []
            for job in failed_jobs:
                # 2. Fetch the text logs for the failed job
                log_url = f"https://api.github.com/repos/{repo_name}/actions/jobs/{job['id']}/logs"
                log_response = await client.get(log_url, headers=headers, follow_redirects=True)
                
                if log_response.status_code == 200:
                    all_logs.append(f"--- Logs for Job: {job['name']} ---\n{log_response.text}")
                else:
                    all_logs.append(f"--- Error fetching logs for Job: {job['name']} ({log_response.status_code}) ---")
                    
            return "\n\n".join(all_logs)
            
    except Exception as e:
        return f"Exception fetching logs: {str(e)}"

def get_github_file_content(repo_name: str, path: str, ref: str = "main") -> str:
    """Fetch file content directly from GitHub repository."""
    if not gh:
        return "Error: GitHub client not initialized."
    try:
        repo = gh.get_repo(repo_name)
        file_content = repo.get_contents(path, ref=ref)
        return file_content.decoded_content.decode('utf-8')
    except Exception as e:
        return f"Error fetching file {path} from GitHub: {str(e)}"

def get_commit_diff(repo_name: str, commit_sha: str) -> str:
    """Fetch the diff for a specific commit from GitHub."""
    if not gh:
        return "Error: GitHub client not initialized."
    try:
        repo = gh.get_repo(repo_name)
        commit = repo.get_commit(commit_sha)
        files = commit.files
        diff_text = ""
        for file in files:
            diff_text += f"--- {file.filename}\n{file.patch}\n\n"
        return diff_text
    except Exception as e:
        return f"Error fetching diff for commit {commit_sha}: {str(e)}"

def read_repo_file(repo_name: str, path: str) -> str:
    """[LOCAL ONLY] Read a file from the local repository."""
    local_path = get_local_repo_path(repo_name)
    full_path = os.path.join(local_path, path)
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file {full_path}: {str(e)}"

def run_sandbox_test(repo_name: str, command: str) -> tuple[bool, str]:
    """Simulate a local build/test command."""
    local_path = get_local_repo_path(repo_name)
    try:
        # Run command in the repository's directory
        result = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=local_path)
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)

def push_branch(repo_name: str, branch: str):
    """Commit changes and push to a new branch."""
    local_path = get_local_repo_path(repo_name)
    try:
        # Configure git (required in CI environment)
        subprocess.run(["git", "config", "user.name", "PatchPilot Agent"], check=True, cwd=local_path)
        subprocess.run(["git", "config", "user.email", "patchpilot@ai.com"], check=True, cwd=local_path)
        
        # Create and switch to new branch
        subprocess.run(["git", "checkout", "-b", branch], check=True, cwd=local_path)
        
        # Add all changed files (PatchPilot only modifies target_file)
        subprocess.run(["git", "add", "."], check=True, cwd=local_path)
        
        # Commit
        subprocess.run(["git", "commit", "-m", f"AI Fix: Automated patch for branch {branch}"], check=True, cwd=local_path)
        
        # Push to remote (using TOKEN for auth if needed, but checkout usually handles this)
        subprocess.run(["git", "push", "origin", branch, "--force"], check=True, cwd=local_path)
        return True, "Successfully pushed branch"
    except Exception as e:
        return False, f"Git operation failed at {local_path}: {str(e)}"

def submit_pull_request(repo_name: str, branch: str, title: str, body: str, base_branch: str = "main"):
    """Open a Pull Request on GitHub."""
    if not gh:
        return "Error: GitHub client not initialized."
    
    try:
        repo = gh.get_repo(repo_name)
        pr = repo.create_pull(title=title, body=body, head=branch, base=base_branch)
        return f"PR created: {pr.html_url}"
    except Exception as e:
        return f"Error creating PR: {str(e)}"

def post_commit_comment(repo_name: str, commit_sha: str, body: str):
    """Post a comment on a specific GitHub commit."""
    if not gh:
        return "Error: GitHub client not initialized."
    
    try:
        repo = gh.get_repo(repo_name)
        commit = repo.get_commit(commit_sha)
        comment = commit.create_comment(body)
        return f"Comment posted: {comment.html_url}"
    except Exception as e:
        return f"Error posting comment: {str(e)}"
