"""
Secret Loader

Loads secrets from various sources:
- Docker secrets (/run/secrets/*)
- Kubernetes secrets (mounted files)
- Environment variables
"""

import os
from pathlib import Path
from typing import Any


def load_secret(secret_name: str, default: Any = None) -> str | None:
    """
    Load a secret from multiple sources in order of priority:
    1. Docker secret: /run/secrets/{secret_name}
    2. Kubernetes secret: /var/run/secrets/{secret_name}
    3. Environment variable: {SECRET_NAME}
    4. Default value

    Args:
        secret_name: Name of the secret (e.g., "database_password")
        default: Default value if secret not found

    Returns:
        Secret value or default

    Example:
        >>> db_password = load_secret("database_password", "default_pwd")
    """
    # Try Docker secrets
    docker_secret_path = Path(f"/run/secrets/{secret_name}")
    if docker_secret_path.exists():
        return docker_secret_path.read_text().strip()

    # Try Kubernetes secrets
    k8s_secret_path = Path(f"/var/run/secrets/{secret_name}")
    if k8s_secret_path.exists():
        return k8s_secret_path.read_text().strip()

    # Try environment variable (uppercase with underscores)
    env_var = secret_name.upper().replace("-", "_")
    env_value = os.getenv(env_var)
    if env_value is not None:
        return env_value

    # Return default
    return default


def load_secret_or_raise(secret_name: str) -> str:
    """
    Load a secret or raise an error if not found.

    Args:
        secret_name: Name of the secret

    Returns:
        Secret value

    Raises:
        ValueError: If secret not found

    Example:
        >>> api_key = load_secret_or_raise("api_key")
    """
    secret = load_secret(secret_name)
    if secret is None:
        raise ValueError(
            f"Secret '{secret_name}' not found. "
            f"Check /run/secrets/, /var/run/secrets/, or environment variables."
        )
    return secret


def secrets_available() -> bool:
    """
    Check if any secrets directory is available.

    Returns:
        True if Docker or K8s secrets directory exists

    Example:
        >>> if secrets_available():
        ...     password = load_secret("db_password")
    """
    return Path("/run/secrets").exists() or Path("/var/run/secrets").exists()
