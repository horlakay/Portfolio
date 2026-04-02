import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  vus: 10,
  duration: "30s",
  thresholds: {
    http_req_duration: ["p(95)<75", "p(99)<150"],
    http_req_failed: ["rate<0.01"],
  },
};

const payload = JSON.stringify({
  event: {
    event_id: "44444444-4444-4444-8444-444444444444",
    event_type: "transaction_initiated",
    timestamp: "2026-04-01T08:06:00Z",
    user_id: "user-1001",
    account_id: "acct-1001",
    session_id: "sess-k6",
    device_id: "device-new-london",
    ip_address: "203.0.113.24",
    geolocation: {
      region: "GB-LND",
      country: "GB",
      city: "London",
      latitude: 51.5074,
      longitude: -0.1278,
    },
    amount: 3250.0,
    currency: "USD",
    metadata: {
      payment_rail: "wire",
    },
  },
});

export default function () {
  const event = JSON.parse(payload);
  event.event.event_id = `${__VU}-${__ITER}-${Date.now()}`;
  event.event.session_id = `sess-k6-${__VU}-${__ITER}`;
  const response = http.post("http://localhost:8005/v1/decisions/score", JSON.stringify(event), {
    headers: { "Content-Type": "application/json" },
  });
  check(response, {
    "status is 200": (r) => r.status === 200,
  });
  sleep(1);
}
