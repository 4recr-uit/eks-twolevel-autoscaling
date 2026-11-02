import http from 'k6/http';
import { check } from 'k6';
import { Counter, Rate } from 'k6/metrics';

// Giá trị mặc định chỉ dành cho pilot; giữ nguyên giữa các lượt so sánh.
const profile = __ENV.PROFILE || 'steady';
const low = Number(__ENV.LOW_RATE || 1);
const high = Number(__ENV.HIGH_RATE || 5);
const batchSize = Number(__ENV.BATCH_SIZE || 1);
const workUnits = Number(__ENV.WORK_UNITS || 100);
const baseUrl = (__ENV.BASE_URL || 'http://localhost:8082').replace(/\/$/, '');
const vus = Number(__ENV.VUS || 50);
const dbMode = __ENV.DB_MODE || 'light';

if (!['steady', 'step', 'burst'].includes(profile)) throw new Error('PROFILE phải là steady, step hoặc burst');
if (!['none', 'light', 'full'].includes(dbMode)) throw new Error('DB_MODE phải là none, light hoặc full');
if (![low, high, batchSize, workUnits, vus].every(Number.isInteger) || low < 1 || high < low || batchSize < 1 || batchSize > 10 || workUnits < 1 || workUnits > 10000 || vus < 1) {
  throw new Error('Kiểm tra LOW_RATE, HIGH_RATE, BATCH_SIZE (1–10), WORK_UNITS (1–10000) và VUS');
}

const stages = {
  steady: [{ target: low, duration: '2m' }],
  step: [{ target: low, duration: '1m' }, { target: high, duration: '0s' }, { target: high, duration: '2m' }, { target: low, duration: '0s' }, { target: low, duration: '1m' }],
  burst: [{ target: low, duration: '1m' }, { target: high, duration: '0s' }, { target: high, duration: '30s' }, { target: low, duration: '0s' }, { target: low, duration: '1m' }],
};

export const options = {
  scenarios: {
    jobs: { executor: 'ramping-arrival-rate', startRate: low, timeUnit: '1s', preAllocatedVUs: vus, maxVUs: vus, stages: stages[profile] },
  },
};

const acceptedJobs = new Counter('e1_accepted_jobs');
const failedRequests = new Rate('e1_failed_requests');

export default function () {
  const response = http.post(`${baseUrl}/jobs`, JSON.stringify({ workUnits, dbMode, batchSize, customerId: 'test-e1' }), { headers: { 'Content-Type': 'application/json' } });
  let body;
  try { body = response.json(); } catch (_) { body = {}; }
  const accepted = Array.isArray(body.jobIds) ? body.jobIds.length : 0;
  acceptedJobs.add(accepted);
  const complete = response.status === 200 && body.status === 'published' && accepted === batchSize;
  failedRequests.add(!complete);
  check(response, { 'tất cả job được chấp nhận': () => complete });
}
