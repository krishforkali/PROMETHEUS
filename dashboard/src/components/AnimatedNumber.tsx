import { useEffect, useRef, useState } from "react";

interface Props {
  value: number;
  format?: (n: number) => string;
  durationMs?: number;
}

/** Tweens between values so KPI changes are visible on a projector. */
export function AnimatedNumber({ value, format = (n) => Math.round(n).toLocaleString("en-IN"), durationMs = 600 }: Props) {
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  const shownRef = useRef(value);
  shownRef.current = shown;

  useEffect(() => {
    from.current = shownRef.current;
    const start = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const f = Math.min(1, (now - start) / durationMs);
      const eased = 1 - (1 - f) ** 3;
      setShown(from.current + (value - from.current) * eased);
      if (f < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value, durationMs]);

  return <>{format(shown)}</>;
}
