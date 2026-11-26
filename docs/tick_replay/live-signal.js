/* Browser counterpart of USDJPY_Speed_Denial_Break.mq4 v1.05 defaults. */
const UsdJpySignal = (() => {
  const config = Object.freeze({
    pip: 0.01, lookback: 30, minBreak: 0.5, minRejection: 5,
    speedMinutes: 60, minSpeedBars: 45, expiryMinutes: 60, cooldownMinutes: 15,
  });
  const sides = ['long', 'short'];
  const minuteSeconds = 60;
  const epsilon = 1e-9;

  function speedAt(bars, minute, end = bars.length) {
    const from = minute - config.speedMinutes * minuteSeconds;
    let up = 0, down = 0, upCount = 0, downCount = 0, count = 0;
    for (let i = end - 1; i >= 0; i--) {
      const bar = bars[i];
      if (bar.time >= minute) continue;
      if (bar.time < from) break;
      count++;
      const body = (bar.close - bar.open) / config.pip;
      if (body > 0) { up += body; upCount++; }
      else if (body < 0) { down -= body; downCount++; }
    }
    up = upCount ? up / upCount : 0;
    down = downCount ? down / downCount : 0;
    const ready = count >= config.minSpeedBars;
    const diff = up - down;
    const bias = ready && upCount && downCount && Math.abs(diff) > 1e-6
      ? (diff > 0 ? 'long' : 'short') : null;
    return { up, down, diff, count, ready, bias, from, to: minute };
  }

  function extremes(bars, end) {
    if (end < config.lookback) return null;
    let high = -Infinity, low = Infinity;
    for (let i = end - config.lookback; i < end; i++) {
      high = Math.max(high, bars[i].high);
      low = Math.min(low, bars[i].low);
    }
    return { high, low };
  }

  function step(state, bar, getSpeed) {
    const signals = {};
    for (const side of sides) {
      const candidate = state.pending[side];
      if (!candidate) continue;
      if (bar.time - candidate.time > config.expiryMinutes * minuteSeconds) {
        state.pending[side] = null;
        continue;
      }
      const crossed = side === 'long' ? bar.high >= candidate.level : bar.low <= candidate.level;
      if (!crossed) continue;

      const last = state.lastEntry[side];
      const inCooldown = last !== null && bar.time - last < config.cooldownMinutes * minuteSeconds;
      const speed = inCooldown ? null : getSpeed();
      const status = inCooldown ? 'cooldown' : !speed.ready ? 'insufficient-speed'
        : speed.bias === side ? 'triggered' : 'filtered';
      signals[side] = { ...candidate, status };
      if (!inCooldown) state.lastEntry[side] = bar.time;
      state.pending[side] = null;
    }
    return signals;
  }

  function prepare(bars, minute) {
    const completed = bars.filter(bar => bar.time < minute);
    const state = { pending: { long: null, short: null }, lastEntry: { long: null, short: null } };
    for (let i = config.lookback; i < completed.length; i++) {
      const bar = completed[i];
      step(state, bar, () => speedAt(completed, bar.time, i));
      const { high, low } = extremes(completed, i);
      const minBreak = config.minBreak * config.pip, minRejection = config.minRejection * config.pip;
      if (bar.high + epsilon >= high + minBreak && bar.close <= high
          && bar.high - bar.close + epsilon >= minRejection) {
        state.pending.long = { level: bar.high, time: bar.time };
      }
      if (bar.low - epsilon <= low - minBreak && bar.close >= low
          && bar.close - bar.low + epsilon >= minRejection) {
        state.pending.short = { level: bar.low, time: bar.time };
      }
    }
    return {
      ...state, speed: speedAt(completed, minute), range: extremes(completed, completed.length),
    };
  }

  function evaluate(context, current) {
    const state = { pending: { ...context.pending }, lastEntry: { ...context.lastEntry } };
    const signals = step(state, current, () => context.speed);
    const entries = {};
    for (const side of sides) {
      if (signals[side]) {
        entries[side] = signals[side];
        continue;
      }
      const candidate = state.pending[side];
      if (candidate) {
        const distance = side === 'long' ? candidate.level - current.close : current.close - candidate.level;
        entries[side] = {
          status: 'pending', level: candidate.level, distance: Math.max(0, distance / config.pip),
          minutes: config.expiryMinutes - Math.floor((current.time - candidate.time) / minuteSeconds),
        };
      } else if (context.range) {
        const level = side === 'long'
          ? context.range.high + config.minBreak * config.pip
          : context.range.low - config.minBreak * config.pip;
        const broke = side === 'long' ? current.high + epsilon >= level : current.low - epsilon <= level;
        const returned = side === 'long' ? current.close <= context.range.high : current.close >= context.range.low;
        const rejectionPips = (side === 'long' ? current.high - current.close : current.close - current.low) / config.pip;
        entries[side] = { level, returned, rejectionPips, status: broke ? 'confirm-close' : 'waiting' };
      } else {
        entries[side] = { status: 'insufficient-history' };
      }
    }
    return { speed: context.speed, entries };
  }

  return { config, prepare, evaluate, speedAt };
})();

if (typeof module !== 'undefined') module.exports = UsdJpySignal;
