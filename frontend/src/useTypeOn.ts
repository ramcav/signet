import { useEffect, useState } from "react";

/**
 * Progressively reveal `full` char-by-char once it becomes non-empty.
 * Restarts whenever `full` changes.
 */
export function useTypeOn(full: string | null | undefined, msPerChar = 8): string {
  const [shown, setShown] = useState("");
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(preference.matches);
    update();
    preference.addEventListener("change", update);
    return () => preference.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (!full) {
      setShown("");
      return;
    }
    if (reducedMotion) {
      setShown(full);
      return;
    }
    setShown("");
    let i = 0;
    const id = window.setInterval(() => {
      i += 1;
      setShown(full.slice(0, i));
      if (i >= full.length) window.clearInterval(id);
    }, msPerChar);
    return () => window.clearInterval(id);
  }, [full, msPerChar, reducedMotion]);
  return reducedMotion ? full ?? "" : shown;
}
