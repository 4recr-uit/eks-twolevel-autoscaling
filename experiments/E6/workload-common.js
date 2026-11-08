import http from 'k6/http';
import { check } from 'k6';
import { Counter, Gauge, Rate } from 'k6/metrics';

// Kịch bản được chọn bằng tên file; tránh âm thầm bỏ qua lệnh cũ.
if (__ENV.PROFILE) throw new Error('Không dùng PROFILE: chọn stead.js, step.js hoặc burst.js');

export const settings = {
  batchSize: Number(__ENV.BATCH_SIZE || 1),
  workUnits: Number(__ENV.WORK_UNITS || 100),
  vus: Number(__ENV.VUS || 50),
  dbMode: __ENV.DB_MODE || 'light',
  baseUrl: (__ENV.BASE_URL || 'http://localhost:8082').replace(/\/$/, ''),
};
const { batchSize, workUnits, vus, dbMode, baseUrl } = settings;
if (!['none', 'light', 'full'].includes(dbMode) ||
    ![batchSize, workUnits, vus].every(Number.isInteger) ||
    batchSize < 1 || batchSize > 10 ||
    workUnits < 1 || workUnits > 10000 || vus < 1) {
  throw new Error('Kiểm tra BATCH_SIZE (1–10), WORK_UNITS (1–10000), VUS và DB_MODE');
}
if (batchSize !== 1 || workUnits !== 100 || vus !== 50 || dbMode !== 'light') {
  throw new Error('E6 cần cấu hình baseline E1: BATCH_SIZE=1, WORK_UNITS=100, VUS=50, DB_MODE=light');
}

export function optionsFor(startRate, stages) {
  return { scenarios: { jobs: { executor: 'ramping-arrival-rate', startRate,
    timeUnit: '1s', preAllocatedVUs: vus, maxVUs: vus, stages } } };
}

const acceptedJobs = new Counter('e1_accepted_jobs');
const failedRequests = new Rate('e1_failed_requests');
const workloadStartedAt = new Gauge('workload_started_at_unix_ms');
const workloadFinishedAt = new Gauge('workload_finished_at_unix_ms');
const config = {
  profile: new Gauge('workload_profile_code'), low: new Gauge('workload_low_rate'),
  high: new Gauge('workload_high_rate'), batch: new Gauge('workload_batch_size'),
  units: new Gauge('workload_work_units'), db: new Gauge('workload_db_mode_code'),
  version: new Gauge('workload_model_version'),
};

export function setupFor(profile, low, high, version) {
  const startedAt = Date.now();
  workloadStartedAt.add(startedAt);
  config.profile.add({ steady: 0, step: 1, burst: 2 }[profile]);
  config.low.add(low); config.high.add(high); config.batch.add(batchSize);
  config.units.add(workUnits); config.db.add({ none: 0, light: 1, full: 2 }[dbMode]);
  config.version.add(version);
  console.log(`Workload bắt đầu (UTC): ${new Date(startedAt).toISOString()}`);
}

export function teardown() {
  const finishedAt = Date.now();
  workloadFinishedAt.add(finishedAt);
  console.log(`Workload kết thúc (UTC): ${new Date(finishedAt).toISOString()}`);
}

export function sendJob() {
  const response = http.post(`${baseUrl}/jobs`, JSON.stringify({ workUnits, dbMode, batchSize, customerId: 'test-e1' }),
    { headers: { 'Content-Type': 'application/json' } });
  let body;
  try { body = response.json(); } catch (_) { body = {}; }
  const accepted = Array.isArray(body.jobIds) ? body.jobIds.length : 0;
  acceptedJobs.add(accepted);
  const complete = response.status === 200 && body.status === 'published' && accepted === batchSize;
  failedRequests.add(!complete);
  check(response, { 'tất cả job được chấp nhận': () => complete });
}
