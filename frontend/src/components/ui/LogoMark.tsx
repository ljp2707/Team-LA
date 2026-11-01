/** The NMU Launches mark: two light blue waves on a dark rounded square. */
export function LogoMark({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true">
      <rect width="40" height="40" rx="10" fill="#0D2438" />
      <path
        d="M8 16q6-5 12 0t12 0M8 25q6-5 12 0t12 0"
        fill="none"
        stroke="#A9D3F3"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}
