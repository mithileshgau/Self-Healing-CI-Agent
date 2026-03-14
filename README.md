# PatchPilot: CI Failure Analyzer

PatchPilot is an autonomous CI analysis agent built with LangGraph and Gemini. It automatically responds to failed GitHub Action runs, analyzes technical logs, and identifies whether the root cause is a code bug, a broken test, or an environment configuration issue.

## Features
- **Deep Log Analysis**: Ingests thousands of lines of raw GitHub Action logs to pinpoint exactly what failed.
- **Root Cause Categorization**: Automatically classifies failures into `Code`, `Test`, `Environment`, or `Flaky` categories.
- **Automated Fix Suggestions**: Proposes a concise code fix based on the identified error, commit diff, and direct GitHub file context.
- **GitHub-Native**: Operates directly against the GitHub API; no local clone of the target repository is required.
- **Commit Feedback**: Automatically posts analysis results and suggested fixes as comments on the specific commit that triggered the failure.

## Architecture
The agent uses a simplified LangGraph flow:
1. `analyze`: Fetches logs, extracts the error session, and performs a deep analysis using Gemini 2.5 Flash-Lite.

## Setup

### 1. Set Up Virtual Environment
```bash
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Environment Variables
Create a `.env` file with:
```env
GOOGLE_API_KEY=your_gemini_api_key
GITHUB_TOKEN=your_github_personal_access_token
```

### 4. Run the Webhook Receiver
```bash
python main.py
```

## Local Development (Tunneling)
Since PatchPilot runs on `localhost`, GitHub cannot reach it directly. You need to expose your local port using a tunneling service like **ngrok**:

1. [Install ngrok](https://ngrok.com/download).
2. Start a tunnel to your local port (default 8000):
   ```bash
   ngrok http 8000
   ```
3. Copy the **Forwarding URL** provided by ngrok (e.g., `https://random-id.ngrok-free.app`).
4. In GitHub, go to **Settings > Webhooks > Add webhook**:
   - **Payload URL**: `https://random-id.ngrok-free.app/webhook`
   - **Content type**: `application/json`
   - **Events**: Select `Workflow runs`.

## How it works
The agent exposes a `/webhook` endpoint locally. Configure your GitHub repository to send `workflow_run.completed` events to this endpoint (via your ngrok URL). When a CI run fails, GitHub sends a webhook to your local machine. PatchPilot catches it, runs the LangGraph logic using Gemini to analyze the logs and generate a fix, and then posts the entire analysis as a comment directly on the failed commit.