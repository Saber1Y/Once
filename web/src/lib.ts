export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

export function money(n: number) {
  return `$${n.toFixed(2)}`;
}
