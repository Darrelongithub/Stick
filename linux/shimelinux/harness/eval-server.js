// SPDX-License-Identifier: BSD-3-Clause
// Test-only JavaScript expression evaluator for the headless core harness.
// Production ShimeLinux uses Nashorn; no scheduling state lives in this file.
'use strict';
const readline = require('readline');
const vm = require('vm');

function border(area, kind, point) {
  const isOn = () => {
    if (!area.visible) return false;
    if (kind === 'floor') return point.y === area.bottom && point.x >= area.left && point.x <= area.right;
    if (kind === 'ceiling') return point.y === area.top && point.x >= area.left && point.x <= area.right;
    if (kind === 'left') return point.x === area.left && point.y >= area.top && point.y <= area.bottom;
    if (kind === 'right') return point.x === area.right && point.y >= area.top && point.y <= area.bottom;
    return false;
  };
  return { isOn, left: area.left, right: area.right, top: area.top, bottom: area.bottom,
           width: area.right - area.left, height: area.bottom - area.top };
}
function area(left, top, right, bottom, visible = true) {
  const a = { left, top, right, bottom, visible, width: right - left, height: bottom - top };
  return a;
}
function borders(a, point) {
  return { leftBorder: border(a, 'left', point), rightBorder: border(a, 'right', point),
           topBorder: border(a, 'ceiling', point), bottomBorder: border(a, 'floor', point) };
}
function evaluate(input) {
  const point = input.anchor;
  const workArea = area(0, 0, 1920, 1080);
  const screen = area(0, 0, 1920, 1080);
  const activeIE = area(0, 0, 0, 0, false);
  const floor = border(workArea, 'floor', point);
  const ceiling = border(workArea, 'ceiling', point);
  const wall = border(workArea, input.lookRight ? 'right' : 'left', point);
  const mascot = {
    anchor: point, totalCount: input.totalCount, count: input.count, time: input.time,
    lookRight: input.lookRight, isLookRight: input.lookRight,
    affordances: { contains: () => false },
    environment: {
      floor, ceiling, wall,
      workArea: Object.assign({}, workArea, borders(workArea, point)),
      screen: Object.assign({}, screen, borders(screen, point)),
      activeIE: Object.assign({}, activeIE, borders(activeIE, point)),
      cursor: { x: 960, y: 540, dx: 0, dy: 0 },
      activeIETitle: '',
    },
  };
  const context = vm.createContext({ mascot, action: { time: input.actionTime }, Math, JSON });
  const cache = Object.create(null);
  const evaluating = new Set();
  for (const [key, value] of Object.entries(input.variables || {})) {
    if (value && typeof value === 'object' && typeof value.__script === 'string') {
      Object.defineProperty(context, key, {
        configurable: true, enumerable: true,
        get() {
          if (Object.prototype.hasOwnProperty.call(cache, key)) return cache[key];
          if (evaluating.has(key)) throw new Error('cyclic script variable: ' + key);
          evaluating.add(key);
          try {
            const result = vm.runInContext(value.__script, context, { timeout: 1000 });
            cache[key] = result === undefined ? null : result;
            return cache[key];
          } finally { evaluating.delete(key); }
        },
      });
    } else {
      context[key] = value;
    }
  }
  return vm.runInContext(input.source, context, { timeout: 1000 });
}

const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
rl.on('line', line => {
  try {
    const value = evaluate(JSON.parse(line));
    process.stdout.write(JSON.stringify({ value: value === undefined ? null : value }) + '\n');
  } catch (error) {
    process.stdout.write(JSON.stringify({ error: String(error) }) + '\n');
  }
});
