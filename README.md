🚀 Zendesk → Slack Automation MVP

Production-ready automation to route Zendesk tickets, prevent duplicated actions, and alert teams in Slack only when it really matters.

This project demonstrates how support teams can reduce manual triage, avoid alert fatigue, and respond faster to high-severity tickets using a secure, testable, and observable webhook-based architecture.

🧠 The Problem

Most support teams struggle with:

Zendesk sending multiple webhook events for the same ticket

Manual routing based on priority/type

Slack channels flooded with low-value notifications

No safe way to test automations before going live

Hard-to-debug webhook failures

✅ The Solution

This automation acts as a decision engine between Zendesk and Slack.

It:

Deduplicates incoming webhook events

Normalizes inconsistent Zendesk data (Portuguese / English)

Applies routing rules deterministically

Sends Slack alerts only for high-severity tickets

Supports debug, dry-run, and production modes

Is fully test-covered and observable

🏗️ Architecture Overview
Zendesk Webhook
      ↓
Signature Validation (HMAC)
      ↓
Normalization Layer
      ↓
Routing Rules Engine
      ↓
Idempotency / Deduplication
      ↓
Slack Notification (optional)
      ↓
Zendesk Update (optional)

🔁 Execution Modes
Mode	Purpose
Debug + Dry-Run	Observe decisions, logs, Slack pings without changing Zendesk
Dry-Run (no debug)	Safe validation before production
Production	Real Slack alerts + Zendesk updates
✨ Key Features

🔐 Secure webhook signature validation

♻️ Idempotency & deduplication

🌍 Priority/status normalization (PT → EN)

📊 Full debug & replay endpoints

🧪 100% test coverage for routing logic

🚦 Dry-run safety switch

🔔 Slack alerts only for critical tickets

🧪 Example Decision Output
{
  "ok": true,
  "decision": {
    "route_to": "support",
    "severity": "critical",
    "notify": true,
    "reason": "High severity → Slack notification"
  },
  "slack_sent": true,
  "zendesk_updated": false,
  "zendesk_dry_run": true
}

⚡ Quickstart
1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

2. Install dependencies
pip install -r requirements.txt

3. Configure environment variables
cp .env.example .env


Fill in values as needed (Slack webhook, Zendesk secrets, etc).

4. Run the API
uvicorn app.main:app --reload

5. (Optional) Expose locally with ngrok
ngrok http 8000

🔔 Zendesk Webhook Configuration

Configure Zendesk to POST JSON events to:

https://<your-ngrok-subdomain>.ngrok.io/webhooks/zendesk


Zendesk signature headers supported:

X-Zendesk-Webhook-Signature

X-Zendesk-Webhook-Timestamp (epoch or ISO-8601)

🧪 Debug & Observability Endpoints
Endpoint	Purpose
/health	Health check
/debug/ping-slack	Test Slack integration
/debug/signature-check	Validate webhook signature
/debug/decisions/recent	Recent routing decisions
/debug/events/recent	Raw webhook events
/debug/decisions/replay?ticket_id=123	Replay routing logic
🧪 Running Tests
pytest -v


Covers:

Routing logic

Deduplication

Normalization

Signature validation

Slack formatting

💼 Use Cases

This project can be positioned as:

✅ Freelancer automation project

✅ Support tooling MVP

✅ Zendesk consulting deliverable

✅ Internal Ops automation

🚀 Foundation for a SaaS product

🧩 Why This Matters

This is not a demo script.

It demonstrates:

Real-world webhook safety

Deterministic routing logic

Production-grade testing

Clear separation of concerns

Business-oriented automation design

📬 Contact / Usage

If you want help adapting this system for:

Your Zendesk instance

Your Slack workspace

Custom routing rules

Production deployment

👉 This architecture is ready to scale.