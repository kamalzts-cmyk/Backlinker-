class AIGenerationError(Exception):
    """Raised when an AI provider fails to produce a valid structured response.

    Covers transport failure (the provider is unreachable or returns a
    non-2xx response), malformed output (the provider's response isn't
    valid JSON), and schema failure (the JSON doesn't match the caller's
    requested `response_model`). Callers should treat all three the same
    way: the AI-assisted step didn't produce usable output, fall back to
    whatever the deterministic path would otherwise do.
    """
