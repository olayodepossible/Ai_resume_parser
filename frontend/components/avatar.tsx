import { initialsOf } from "@/lib/screening";

/**
 * Initials on a hue derived from the name, so the same person keeps the same
 * colour across renders without storing anything.
 */
export function Avatar({
  name,
  size = 36,
  className = "",
}: {
  name: string;
  size?: number;
  className?: string;
}) {
  const hue = hueOf(name);

  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-full font-semibold select-none ${className}`}
      style={{
        width: size,
        height: size,
        fontSize: Math.max(10, Math.round(size * 0.36)),
        backgroundColor: `oklch(0.72 0.11 ${hue})`,
        color: "oklch(0.22 0.06 " + hue + ")",
      }}
      aria-hidden="true"
    >
      {initialsOf(name)}
    </span>
  );
}

function hueOf(value: string): number {
  let hash = 0;

  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) % 360;
  }

  return hash;
}
