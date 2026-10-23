"""Generate a short burst of traffic for the Grafana API Gateway dashboard."""

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


GATEWAY_URL = "http://localhost:8000"
API_KEY = "dashboard-demo-key"


def request_json(url, method="GET", body=None, headers=None):
    request_headers = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"

    request = Request(url, data=data, headers=request_headers, method=method)
    with urlopen(request, timeout=10) as response:
        payload = response.read()
        return response.status, dict(response.headers.items()), payload


def demo_request(url):
    return request_json(
        url,
        headers={"Authorization": f"ApiKey {API_KEY}"},
    )


def main():
    try:
        with urlopen(f"{GATEWAY_URL}/health", timeout=3) as response:
            if response.status != 200:
                raise RuntimeError(f"Gateway health check returned HTTP {response.status}")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(
            "Gateway is unavailable at http://localhost:8000. Start Docker Compose first."
        ) from exc

    request_json(
        f"{GATEWAY_URL}/admin/keys/{API_KEY}",
        method="POST",
        body={
            "plan_name": "dashboard_demo",
            "default_qps": 100,
            "burst_capacity": 1000,
            "hard_max_qps": 1000,
        },
        headers={"X-Forwarded-For": "127.0.0.1"},
    )

    run_id = str(time.time_ns())

    print("Generating cache traffic...")
    cache_url = f"{GATEWAY_URL}/benchmark/cache?demo_run={run_id}"
    cache_results = [demo_request(cache_url) for _ in range(12)]
    cache_states = {}
    for _, headers, _ in cache_results:
        state = headers.get("x-cache", "header not set")
        cache_states[state] = cache_states.get(state, 0) + 1
    print(f"  /benchmark/cache: 12 requests; cache headers: {cache_states}")

    print("Generating concurrent coalescing traffic...")
    coalesce_url = f"{GATEWAY_URL}/benchmark/coalesce?demo_run={run_id}"
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = [
            executor.submit(demo_request, coalesce_url)
            for _ in range(12)
        ]
        for future in as_completed(futures):
            future.result()
    print("  /benchmark/coalesce: 12 concurrent requests completed")

    print("Generating downstream/cost traffic...")
    proxy_urls = [
        f"{GATEWAY_URL}/proxy/process?data=dashboard-{run_id}-{index}"
        for index in range(8)
    ]
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(demo_request, url) for url in proxy_urls]
        for future in as_completed(futures):
            future.result()
    print("  /proxy/process: 8 downstream requests completed")

    print("\nDone. Open http://localhost:3001 and view the 'Intelligent API Gateway Demo' dashboard.")
    print("Use the last 15 minutes time range and refresh the dashboard if needed.")
    print("Grafana's default login is admin / admin.")


if __name__ == "__main__":
    main()
