import { optionsFor, setupFor } from './workload-common.js';
export { teardown, sendJob as default } from './workload-common.js';

if (__ENV.LOW_RATE || __ENV.HIGH_RATE) throw new Error('Steady cố định 5 request/s; không truyền LOW_RATE hoặc HIGH_RATE');
export const options = optionsFor(5, [{ target: 5, duration: '2m' }]);
export function setup() { setupFor('steady', 5, 5, 3); }
