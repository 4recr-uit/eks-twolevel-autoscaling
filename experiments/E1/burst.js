import { optionsFor, setupFor } from './workload-common.js';
export { teardown, sendJob as default } from './workload-common.js';

// Tải Burst được cố định cho các lượt pilot.
const low = 5;
const high = 40;
if (__ENV.LOW_RATE !== undefined || __ENV.HIGH_RATE !== undefined) throw new Error('Burst cố định 5 → 40 → 5 request/s; không truyền LOW_RATE hoặc HIGH_RATE');
export const options = optionsFor(low, [
  { target: low, duration: '1m' }, { target: high, duration: '0s' },
  { target: high, duration: '30s' }, { target: low, duration: '0s' },
  { target: low, duration: '1m' },
]);
export function setup() { setupFor('burst', low, high, 3); }
