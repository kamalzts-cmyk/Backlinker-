class AISearchError(Exception):
    """Raised when a search provider fails to produce a usable result:
    transport failure, an API-level error, or a malformed response. A
    caller that catches this has one honest option -- treat the check
    as not having happened (never record a fabricated result to stand
    in for it).
    """
