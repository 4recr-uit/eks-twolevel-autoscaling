import { optionsFor, setupFor } from './workload-common.js';
export { teardown, sendJob as default } from './workload-common.js';

// Chỉ chọn mức đỉnh; baseline và thời lượng được cố định cho các lượt pilot.
const low = 5;
const high = Number(__ENV.HIGH_RATE);
if (__ENV.LOW_RATE !== undefined) throw new Error('Burst cố định LOW_RATE=5; không truyền LOW_RATE');
if (!Number.isInteger(high) || high <= low) throw new Error('Cần HIGH_RATE là số nguyên lớn hơn 5 request/s');
export const options = optionsFor(low, [
  { target: low, duration: '1m' }, { target: high, duration: '0s' },
  { target: high, duration: '30s' }, { target: low, duration: '0s' },
  { target: low, duration: '1m' },
]);
export function setup() { setupFor('burst', low, high, 3); }
