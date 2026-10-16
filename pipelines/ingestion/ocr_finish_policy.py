"""Sanitized OCR provider outcomes and finite missing-reading retry policy.

No provider body, prompt, image, credentials, or partial transcription belongs
in the attempt ledger. The complete STOP transcription stays in the separate
immutable result table only after schema validation.
"""

from datetime import timedelta


OUTCOME_CODES = frozenset({
    "STOP_VALID", "MAX_TOKENS", "SAFETY", "RECITATION", "BLOCKLIST",
    "PROHIBITED_CONTENT", "NO_CANDIDATE", "OTHER_FINISH",
    "MALFORMED_RESPONSE", "STOP_BAD_JSON", "STOP_BAD_SCHEMA",
    "HTTP_429", "HTTP_RETRYABLE", "HTTP_ERROR", "NETWORK_ERROR",
})
RETRY_DELAY = timedelta(hours=24)


def finish_code(body):
    """Return only an allowlisted label from a provider JSON object."""
    if not isinstance(body, dict):
        return "MALFORMED_RESPONSE"
    feedback = body.get("promptFeedback")
    block = feedback.get("blockReason") if isinstance(feedback, dict) else None
    # Contradictory metadata is never permission to use a STOP candidate.
    if block in {"SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT"}:
        return block
    candidates = body.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return "NO_CANDIDATE"
    first = candidates[0]
    if not isinstance(first, dict):
        return "OTHER_FINISH"
    reason = first.get("finishReason")
    if reason == "STOP":
        return "STOP"
    return reason if reason in {"MAX_TOKENS", "SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT"} else "OTHER_FINISH"


def missing_reading_state(attempts, now):
    """Choose NORMAL, WAIT, RETRY or REVIEW for an absent cached reading.

    `attempts` are (attempt_id, started_at, sanitized_outcome) for exactly one
    image/version/reading. Old unversioned attempts are not in this sequence.
    A missing outcome is a failed audit write and must never be retried.
    """
    if any(code is None or code not in OUTCOME_CODES for _, _, code in attempts):
        return "REVIEW"
    retryable_history = {"MAX_TOKENS", "HTTP_429", "HTTP_RETRYABLE", "NETWORK_ERROR"}
    if any(code not in retryable_history for _, _, code in attempts):
        return "REVIEW"  # Terminal finish or accepted output lost before cache persistence.
    max_tokens = [(attempt_id, started) for attempt_id, started, code in attempts if code == "MAX_TOKENS"]
    if not max_tokens:
        return "NORMAL"
    if len(max_tokens) != 1:
        return "REVIEW"
    failed_id, failed_at = max_tokens[0]
    if any(attempt_id > failed_id for attempt_id, _, _ in attempts):
        return "REVIEW"  # Even a later HTTP 429 spends the one retry.
    if failed_at is None or now is None:
        return "REVIEW"
    return "RETRY" if now - failed_at >= RETRY_DELAY else "WAIT"
