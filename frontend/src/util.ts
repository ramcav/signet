export function truncMid(s: string, head = 10, tail = 8): string {
  if (!s) return "";
  if (s.length <= head + tail + 1) return s;
  return `${s.slice(0, head)}…${s.slice(-tail)}`;
}

export function truncMemo(hex: string): string {
  if (!hex) return "";
  const clean = hex.replace(/^0x/i, "");
  if (clean.length <= 16) return `0x${clean}`;
  return `0x${clean.slice(0, 8)}…${clean.slice(-8)}`;
}
