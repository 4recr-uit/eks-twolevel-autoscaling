import http from 'k6/http';
import { check } from 'k6';
import { Counter, Gauge, Rate } from 'k6/metrics';

// Mỗi lần chạy một mức tải; dùng file summary riêng cho từng mức.
const rate = Number(__ENV.RATE || 8);
const batchSize = Number(__ENV.BATCH_SIZE || 1);
const workUnits = Number(__ENV.WORK_UNITS || 100);
const vus = Number(__ENV.VUS || 50);
const dbMode = __ENV.DB_MODE || 'light';
const baseUrl = (__ENV.BASE_URL || 'http://localhost:8082').replace(/\/$/, '');
if (![rate, batchSize, workUnits, vus].every(Number.isInteger) || rate < 1 ||
    batchSize < 1 || batchSize > 10 || workUnits < 1 || workUnits > 10000 || vus < 1 ||
    !['none', 'light', 'full'].includes(dbMode)) throw new Error('Kiểm tra RATE, BATCH_SIZE, WORK_UNITS, VUS, DB_MODE');

export const options = {
  scenarios: { jobs: { executor: 'constant-arrival-rate', rate, timeUnit: '1s',
    duration: __ENV.DURATION || '2m', preAllocatedVUs: vus, maxVUs: vus } },
};

const accepted = new Counter('e0_accepted_jobs');
const failed = new Rate('e0_failed_requests');
const started = new Gauge('workload_started_at_unix_ms');
const finished = new Gauge('workload_finished_at_unix_ms');
const config = {
  rate: new Gauge('workload_rate'), batch: new Gauge('workload_batch_size'),
  units: new Gauge('workload_work_units'), db: new Gauge('workload_db_mode_code'),
};
export function setup() {
  const now = Date.now(); started.add(now);
  config.rate.add(rate); config.batch.add(batchSize); config.units.add(workUnits);
  config.db.add({ none: 0, light: 1, full: 2 }[dbMode]);
  console.log(`Workload bắt đầu (UTC): ${new Date(now).toISOString()}`);
}
export function teardown() {
  const now = Date.now(); finished.add(now); console.log(`Workload kết thúc (UTC): ${new Date(now).toISOString()}`);
}
export default function () {
  const response = http.post(`${baseUrl}/jobs`, JSON.stringify({ workUnits, dbMode, batchSize, customerId: 'test-e0' }),
    { headers: { 'Content-Type': 'application/json' } });
  let body;
  try { body = response.json(); } catch (_) { body = {}; }
  const count = Array.isArray(body.jobIds) ? body.jobIds.length : 0;
  accepted.add(count);
  const ok = response.status === 200 && body.status === 'published' && count === batchSize;
  failed.add(!ok);
  check(response, { 'tất cả job được chấp nhận': () => ok });
}
