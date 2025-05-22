import hashlib
import hmac
import json
from typing import Any, Tuple
from fastapi import Request
import logging

logger = logging.getLogger(__name__)


class WebhookHandler:
    def __init__(self, secret: str):
        if not secret:
            raise ValueError("Webhook secret cannot be empty")
        self.secret = secret.encode("utf-8")

    async def _verify_signature(self, request: Request) -> None:
        signature_header = request.headers.get("x-hub-signature-256")
        if not signature_header:
            logger.error("Missing X-Hub-Signature-256 header")
            raise ValueError("Missing X-Hub-Signature-256 header")

        try:
            signature_type, signature_hash = signature_header.split("=", 1)
            if signature_type.lower() != "sha256":
                logger.error(f"Unsupported signature type: {signature_type}")
                raise ValueError(f"Unsupported signature type: {signature_type}")
        except ValueError:
            logger.error(f"Malformed signature header: {signature_header}")
            raise ValueError("Malformed signature header")

        request_body = await request.body()
        mac = hmac.new(self.secret, msg=request_body, digestmod=hashlib.sha256)
        expected_signature = mac.hexdigest()
        if not hmac.compare_digest(expected_signature, signature_hash):
            logger.error(f"Invalid webhook signature. Expected: {expected_signature}")
            raise ValueError("Invalid webhook signature")

        logger.info("Webhook signature verified successfully")

    async def _handle_pull_request_event(self, payload: dict[str, Any]) -> None:
        action = payload.get("action", "unknown")
        pr = payload.get("pull_request", {})
        repo = payload.get("repository", {})
        logger.info(
            f"Pull request event: action={action}, PR #{pr.get('number', 'N/A')} in {repo.get('full_name', 'N/A')}"
        )

    async def _handle_issues_event(self, payload: dict[str, Any]) -> None:
        action = payload.get("action", "unknown")
        issue = payload.get("issue", {})
        repo = payload.get("repository", {})
        logger.info(
            f"Issue event: action={action}, Issue #{issue.get('number', 'N/A')} in {repo.get('full_name', 'N/A')}"
        )

    async def _handle_push_event(self, payload: dict[str, Any]) -> None:
        repo = payload.get("repository", {})
        ref = payload.get("ref", "N/A")
        commits = len(payload.get("commits", []))
        logger.info(
            f"Push event: {repo.get('full_name', 'N/A')}, ref={ref}, commits={commits}"
        )

    async def handle_webhook(self, request: Request) -> Tuple[dict[str, Any], int]:
        try:
            await self._verify_signature(request)
        except ValueError as e:
            logger.error(f"Webhook verification failed: {e}")
            return {"ok": False, "error": str(e)}, 400

        try:
            payload = await request.json()
        except json.JSONDecodeError:
            logger.error("Invalid JSON payload")
            return {"ok": False, "error": "Invalid JSON payload"}, 400

        event_type = request.headers.get("x-github-event")
        delivery_id = request.headers.get("x-github-delivery", "N/A")
        logger.info(f"Received webhook event: {event_type}, delivery_id={delivery_id}")

        if not event_type:
            return {"ok": False, "error": "Missing X-GitHub-Event header"}, 400

        if event_type == "ping":
            logger.info("Received ping event")
            return {"ok": True, "message": "Ping event received"}, 200
        elif event_type == "pull_request":
            await self._handle_pull_request_event(payload)
        elif event_type == "issues":
            await self._handle_issues_event(payload)
        elif event_type == "push":
            await self._handle_push_event(payload)
        else:
            logger.warning(f"Unhandled event type: {event_type}")
            return {"ok": True, "message": f"Event {event_type} not handled"}, 200

        return {"ok": True, "message": f"Event {event_type} processed"}, 200
