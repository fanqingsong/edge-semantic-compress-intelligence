"""Join an OpenAI-compatible base URL with a standard resource path."""


def openai_url(base_url: str, resource: str) -> str:
    base = base_url.strip().rstrip("/")
    if not base:
        raise ValueError("base_url must not be empty")
    suffix = resource.strip().lstrip("/")
    if not suffix:
        raise ValueError("resource must not be empty")
    if base.endswith("/v1"):
        return f"{base}/{suffix}"
    return f"{base}/v1/{suffix}"
