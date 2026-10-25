import asyncio

import httpx
import pytest

from transfermarkt_api.tfmkt.client import TfmktClient

pytestmark = pytest.mark.anyio


async def test_concurrent_identical_requests_share_one_upstream_call() -> None:
    """Twenty simultaneous identical requests make one upstream call."""
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return httpx.Response(200, json={"success": True, "data": {"id": 1}})

    client = TfmktClient(transport=httpx.MockTransport(handler))
    results = await asyncio.gather(*(client.get("/x") for _ in range(20)))
    await client.aclose()
    assert calls == 1
    assert all(r == {"id": 1} for r in results)
