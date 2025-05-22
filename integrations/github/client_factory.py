from typing import Any, Optional
from port_ocean.context.ocean import ocean
import logging
from client import GitHubClient

logger = logging.getLogger(__name__)

_github_client: Optional[GitHubClient] = None


def create_github_client() -> GitHubClient:
    global _github_client
    if _github_client is not None:
        return _github_client

    integration_config: dict[str, Any] = ocean.integration_config
    logger.info(f"Integration config: {integration_config}")
    github_host = integration_config.get("github_host", "https://api.github.com")
    github_token = integration_config.get("github_token")

    if not github_token:
        logger.error("Missing required github_token in integration config")
        raise KeyError("Missing github_token in integration config")

    _github_client = GitHubClient(github_host, github_token)
    return _github_client
