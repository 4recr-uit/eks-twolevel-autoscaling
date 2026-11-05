import { optionsFor, setupFor } from './workload-common.js';
export { teardown, sendJob as default } from './workload-common.js';

if (__ENV.LOW_RATE || __ENV.HIGH_RATE) throw new Error('Step cố định các bậc; không truyền LOW_RATE hoặc HIGH_RATE');
// Chuyển mức tức thời và giữ cố định mỗi bậc trong hai phút.
export const options = optionsFor(5, [
  { target: 5, duration: '2m' },
  { target: 10, duration: '0s' }, { target: 10, duration: '1m' },
  { target: 15, duration: '0s' }, { target: 15, duration: '1m' },
  { target: 20, duration: '0s' }, { target: 20, duration: '1m' },
  { target: 15, duration: '0s' }, { target: 15, duration: '1m' },
  { target: 10, duration: '0s' }, { target: 10, duration: '1m' },
  { target: 5, duration: '0s' }, { target: 5, duration: '1m' },
]);
export function setup() { setupFor('step', 5, 20, 3); }
