import math
import re
import time


RATE_LIMIT_MARKERS = (
    "ratelimiterror",
    "rate limit",
    "rate_limit_exceeded",
    "too many requests",
    "tokens per minute",
    "status code: 429",
    "status_code=429",
)


def _is_rate_limit_error(error):
    message = str(error or "").lower()

    return any(
        marker in message
        for marker in RATE_LIMIT_MARKERS
    )


def _retry_after_seconds(error):
    message = str(error or "")

    patterns = (
        r"try again in\s*([0-9.]+)s",
        r"retry after\s*([0-9.]+)",
        r"retry-after[^0-9]*([0-9.]+)",
    )

    for pattern in patterns:
        match = re.search(
            pattern,
            message,
            re.IGNORECASE,
        )

        if match:
            try:
                seconds = float(match.group(1))

                return max(
                    2,
                    min(
                        30,
                        int(math.ceil(seconds)) + 2,
                    ),
                )
            except Exception:
                pass

    return 15


def kickoff_with_retry(
    crew,
    label="LabTwin AI",
    attempts=3,
):
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            return crew.kickoff()

        except Exception as error:
            last_error = error

            if not _is_rate_limit_error(error):
                raise

            if attempt >= attempts:
                raise RuntimeError(
                    "The AI service is temporarily busy. "
                    "LabTwin automatically retried the request, "
                    "but the provider rate limit is still active. "
                    "Please wait about 20 seconds and try again."
                ) from None

            wait_seconds = _retry_after_seconds(error)

            print(
                f"{label}: rate limit detected. "
                f"Waiting {wait_seconds}s before retry "
                f"{attempt + 1}/{attempts}."
            )

            time.sleep(wait_seconds)

    raise RuntimeError(
        "The AI service is temporarily busy."
    ) from last_error
