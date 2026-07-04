"""Load test for the Basecamp API.

Run from basecamp-server/ and point --host at the SERVER ROOT (not an endpoint):

    locust -f locustfile.py --host=http://localhost:8000

Then open http://localhost:8089 to drive it.

IMPORTANT: --host must be the base URL. Locust appends each task's path to it,
so passing ".../api/v1/health" turns "/api/data" into ".../api/v1/health/api/data"
(a 404) — which is what tanked the earlier run. Paths below are full from root.
"""

from locust import HttpUser, between, task


class BasecampUser(HttpUser):
    # Pause 1-3s between tasks, like a real user clicking around.
    wait_time = between(1, 3)

    @task(3)
    def health(self):
        # The real health check: no auth, fast, pings Mongo. Best baseline for
        # "can the server take load". `name=` groups all hits under one stat row.
        self.client.get("/api/v1/health", name="GET /health")

    @task(1)
    def login_with_bad_credentials(self):
        # Exercise a real POST route under load. We send wrong credentials on
        # purpose, so 401 is the EXPECTED, correct answer — mark it success so it
        # doesn't count as a failure. Only a 5xx/timeout is a genuine problem.
        with self.client.post(
            "/api/v1/auth/login",
            json={"email": "loadtest@example.com", "password": "wrong-password"},
            name="POST /auth/login (expect 401)",
            catch_response=True,
        ) as resp:
            if resp.status_code in (401, 403, 429):
                resp.success()
            elif resp.status_code >= 500:
                resp.failure(f"server error: {resp.status_code}")
