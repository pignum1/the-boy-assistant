import time
import asyncio


class TokenBucket:
    """Token bucket rate limiter for LLM API calls"""

    def __init__(self, rpm: int = 60, tpm: int = 100000):
        self.rpm = rpm
        self.tpm = tpm
        self._rpm_tokens: float = rpm
        self._tpm_tokens: float = tpm
        self._last_refill: float = time.time()
        self._lock = asyncio.Lock()

    def _refill(self):
        """Refill tokens based on elapsed time"""
        now = time.time()
        elapsed = now - self._last_refill

        # Refill RPM: rpm tokens per 60 seconds
        self._rpm_tokens = min(self.rpm, self._rpm_tokens + elapsed * (self.rpm / 60.0))

        # Refill TPM: tpm tokens per 60 seconds
        self._tpm_tokens = min(self.tpm, self._tpm_tokens + elapsed * (self.tpm / 60.0))

        self._last_refill = now

    async def acquire(self, tokens_needed: int = 1) -> bool:
        """
        Acquire tokens. Returns True if successful.
        Blocks briefly if rate limited (waits up to 2 seconds).
        """
        async with self._lock:
            self._refill()

            if self._rpm_tokens >= 1 and self._tpm_tokens >= tokens_needed:
                self._rpm_tokens -= 1
                self._tpm_tokens -= tokens_needed
                return True

        # Rate limited - wait and retry once
        await asyncio.sleep(1.0)

        async with self._lock:
            self._refill()

            if self._rpm_tokens >= 1 and self._tpm_tokens >= tokens_needed:
                self._rpm_tokens -= 1
                self._tpm_tokens -= tokens_needed
                return True

        return False

    @property
    def rpm_remaining(self) -> float:
        self._refill()
        return self._rpm_tokens

    @property
    def tpm_remaining(self) -> float:
        self._refill()
        return self._tpm_tokens
