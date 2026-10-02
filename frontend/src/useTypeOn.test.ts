import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useTypeOn } from "./useTypeOn";

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function motionPreference(reduced: boolean) {
  const listeners = new Set<() => void>();
  const preference = {
    matches: reduced,
    addEventListener: (_: string, listener: () => void) => listeners.add(listener),
    removeEventListener: (_: string, listener: () => void) => listeners.delete(listener),
  };
  vi.spyOn(window, "matchMedia").mockReturnValue(preference as unknown as MediaQueryList);
  return (matches: boolean) => {
    preference.matches = matches;
    act(() => listeners.forEach((listener) => listener()));
  };
}

it("reveals text immediately when reduced motion is requested", () => {
  vi.useFakeTimers();
  motionPreference(true);
  const { result, rerender } = renderHook(({ text }) => useTypeOn(text), { initialProps: { text: "Payment checked" } });
  expect(result.current).toBe("Payment checked");
  expect(vi.getTimerCount()).toBe(0);
  rerender({ text: "Next payment" });
  expect(result.current).toBe("Next payment");
});

it("finishes a running reveal when the motion preference changes", () => {
  vi.useFakeTimers();
  const changePreference = motionPreference(false);
  const { result, unmount } = renderHook(() => useTypeOn("Payment checked", 10));
  act(() => vi.advanceTimersByTime(20));
  expect(result.current).toBe("Pa");
  changePreference(true);
  expect(result.current).toBe("Payment checked");
  expect(vi.getTimerCount()).toBe(0);
  unmount();
});
