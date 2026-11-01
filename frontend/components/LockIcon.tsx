/** Drawn in the text color, so it stays clear on a bright button, where an emoji does not. */
export function LockIcon({ className = "" }: { className?: string }) {
  return (
    <svg aria-hidden viewBox="0 0 16 16" width="13" height="13" fill="none" className={`inline-block ${className}`}>
      <rect x="3" y="7" width="10" height="7" rx="1.5" fill="currentColor" />
      <path d="M5 7V5a3 3 0 0 1 6 0v2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export function GlobeIcon({ className = "" }: { className?: string }) {
  return (
    <svg aria-hidden viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="1.4" className={`inline-block ${className}`}>
      <circle cx="8" cy="8" r="6.3" />
      <path d="M1.7 8h12.6M8 1.7c-3.6 4-3.6 8.6 0 12.6M8 1.7c3.6 4 3.6 8.6 0 12.6" />
    </svg>
  );
}
