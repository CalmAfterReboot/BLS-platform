"""Tier-based routing with sequential failover across providers.

I keep all of the routing brains in this module. A caller hands me a
CompletionRequest and I decide which provider(s) to try, in what order, and how
to recover when one of them lets me down.
"""

from __future__ import annotations

import asyncio
import logging
import time

from app.config import Settings
from app.errors import AllProvidersFailedError, UpstreamError
from app.models import CompletionRequest, CompletionResponse, Tier
from app.providers.base import Provider

# I attach a module-level logger so every message I emit is namespaced under
# "app.routing" and can be filtered or routed independently of the rest of the app.
logger = logging.getLogger(__name__)


# TIER_CHAINS is my static policy table: for each pricing/quality tier, I declare
# the *preferred* order of providers to try. The first name is the primary; every
# name after it is a fallback I'll attempt if the previous one fails.
#
# I deliberately keep this as a plain dict rather than hiding it inside the class,
# so tests and operators can introspect or monkey-patch the policy without having
# to instantiate a Router.
TIER_CHAINS: dict[Tier, list[str]] = {
    Tier.ECONOMY: ["mock_fast", "mock_premium"],
    Tier.PREMIUM: ["openai", "mock_premium"],
}


class Router:
    """Routes a CompletionRequest down the effective chain for its tier.

    On construction I filter each declared chain down to providers that are
    actually present in the registry. That way a missing OpenAI key just
    silently shortens the premium chain — I don't blow up with a KeyError when
    a real request arrives.
    """

    def __init__(self, registry: dict[str, Provider], settings: Settings) -> None:
        # I store the registry and settings as private attributes. The leading
        # underscore signals "internal" — callers should go through my public
        # methods rather than poking at these directly.
        self._registry = registry
        self._settings = settings

        # Here I compute the *effective* chain for each tier once, at startup,
        # instead of recomputing it on every request. For each declared chain,
        # I drop any provider name that isn't actually in the registry. This is
        # how a missing OpenAI key gracefully degrades the premium tier from
        # ["openai", "mock_premium"] down to just ["mock_premium"].
        self._chains: dict[Tier, list[str]] = {
            tier: [name for name in chain if name in registry]
            for tier, chain in TIER_CHAINS.items()
        }

        # I walk every tier after filtering and shout (via warning log) if any
        # tier ended up with zero providers. That's a misconfiguration I want
        # operators to notice on boot — not the first time a 5xx hits production.
        for tier, effective in self._chains.items():
            if not effective:
                logger.warning(
                    "tier %s has no registered providers; requests at this tier will fail",
                    tier.value,
                )

    def effective_chain(self, tier: Tier) -> list[str]:
        """Return the provider names I will actually try for this tier.

        I expose this mostly for tests and observability — it lets callers ask
        "what would you do for tier X right now?" without having to send a real
        request. I return a *copy* of the list so the caller can't mutate my
        internal state by appending to or clearing the returned list.
        """
        return list(self._chains.get(tier, []))

    async def route(self, request: CompletionRequest) -> CompletionResponse:
        """Try each provider in the tier's chain until one succeeds.

        This is the heart of the gateway. I walk the effective chain for the
        request's tier in order, give each provider a bounded amount of time
        to respond, and fall over to the next one on any timeout or upstream
        error. If I exhaust the whole chain without a success, I raise
        AllProvidersFailedError carrying the tier and the number of attempts I
        made.
        """
        # I look up the precomputed chain for the request's tier. Using .get
        # with a default of [] means an unknown tier is treated the same as an
        # empty chain — I'll fail cleanly below rather than KeyError.
        chain = self._chains.get(request.tier, [])

        # I count attempts so the response (or the final error) can report how
        # many providers I actually invoked. This is observability gold when
        # debugging "why was my request slow?" — attempts=3 means I failed over
        # twice before getting a healthy provider.
        attempts = 0

        if not chain:
            # If the tier has no providers at all, I refuse to pretend I tried.
            # I log at error level (this is a real misconfiguration) and raise
            # with attempts=0 so the caller can distinguish "nothing to try"
            # from "tried everything and they all failed".
            logger.error("no providers registered for tier %s", request.tier.value)
            raise AllProvidersFailedError(tier=request.tier, attempts=attempts)

        # I read the per-request timeout budget from settings once, up front.
        # Pulling it out into a local makes the wait_for call below a bit more
        # readable and avoids re-reading the settings object inside the loop.
        timeout_s = self._settings.request_timeout_seconds

        # I walk the chain with enumerate so I know each provider's position.
        # The position matters because failover_occurred in the response is just
        # "did I have to move past the primary?" — i.e. index > 0.
        for index, provider_name in enumerate(chain):
            # I resolve the name to the actual Provider instance. By
            # construction this lookup can't fail: my filter at __init__ already
            # guaranteed every name in `chain` exists in the registry.
            provider = self._registry[provider_name]

            # I bump the attempt counter *before* the call so it's accurate
            # whether the call succeeds, times out, or raises.
            attempts += 1

            # I record a start timestamp so I can report wall-clock latency in
            # the timeout log line below. Provider implementations also report
            # their own latency on the response object — that's the source of
            # truth on the success path. This fallback exists only for the
            # failure path, where I never get a ProviderResponse back at all.
            started = time.perf_counter()

            try:
                # I wrap the provider call in asyncio.wait_for so a hung
                # provider can't stall the whole request. If the coroutine
                # doesn't resolve within timeout_s seconds, wait_for cancels
                # the underlying task and raises asyncio.TimeoutError.
                provider_response = await asyncio.wait_for(
                    provider.complete(request.prompt, request.max_tokens),
                    timeout=timeout_s,
                )
            except asyncio.TimeoutError:
                # Timeout: I compute elapsed time for the log, warn so an
                # operator can see *which* provider was slow, then `continue`
                # to try the next one in the chain. Crucially I do NOT re-raise
                # — a single slow provider is exactly what failover exists for.
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                logger.warning(
                    "provider %s timed out after %.0fms (budget=%.1fs); failing over",
                    provider_name,
                    elapsed_ms,
                    timeout_s,
                )
                continue
            except UpstreamError as exc:
                # Upstream error: the provider explicitly told me it couldn't
                # serve this request (HTTP 5xx, network blip, malformed
                # response, etc.). I log and fall over, same as for a timeout.
                # I deliberately catch ONLY UpstreamError here — anything else
                # (a ValueError, an AttributeError) signals a bug in my code,
                # not a flaky upstream, and should propagate so I can fix it.
                logger.warning(
                    "provider %s returned upstream error: %s; failing over",
                    provider_name,
                    exc,
                )
                continue

            # If I got here, the provider returned a real response. I build the
            # public CompletionResponse and hand it back. Notes:
            #   - provider_used comes from the provider's self-reported name,
            #     not my chain lookup, so it matches whatever the adapter wants
            #     to identify itself as.
            #   - failover_occurred is (index > 0): True when this wasn't the
            #     primary provider, False when the primary handled it.
            #   - latency_ms is the provider's own measurement of its call,
            #     not my fallback wall-clock timer.
            return CompletionResponse(
                completion=provider_response.text,
                provider_used=provider_response.provider_name,
                tier=request.tier,
                failover_occurred=index > 0,
                attempts=attempts,
                latency_ms=provider_response.latency_ms,
            )

        # I only reach this line if the for-loop completed without returning,
        # which means every provider in the chain either timed out or raised
        # UpstreamError. I log at error level (this is a real outage from the
        # caller's perspective) and raise AllProvidersFailedError carrying the
        # tier and the attempt count so the caller can log/alert intelligently.
        logger.error(
            "all providers failed for tier %s after %d attempt(s)",
            request.tier.value,
            attempts,
        )
        raise AllProvidersFailedError(tier=request.tier, attempts=attempts)
