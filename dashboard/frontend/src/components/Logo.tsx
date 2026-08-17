// The Data Eyes mark: a database cylinder whose top rim doubles as an eye —
// "a database that watches itself." Same geometry as public/favicon.svg, but
// inline so the gradient can reference the live --eyes-primary/--eyes-accent
// CSS custom properties and stay in sync with light/dark theme (a static
// favicon file can't do that, so it hardcodes the light-mode hex values).
export default function Logo({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Data Eyes">
      <defs>
        <linearGradient id="eyesLogoGradient" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="var(--eyes-primary)" />
          <stop offset="100%" stopColor="var(--eyes-accent)" />
        </linearGradient>
      </defs>

      <ellipse cx="16" cy="24" rx="11" ry="4" fill="url(#eyesLogoGradient)" />
      <rect x="5" y="7" width="22" height="17" fill="url(#eyesLogoGradient)" />
      <path d="M6 13 Q16 17 26 13" fill="none" stroke="#ffffff" strokeOpacity="0.55" strokeWidth="1.3" strokeLinecap="round" />
      <path d="M6 19 Q16 23 26 19" fill="none" stroke="#ffffff" strokeOpacity="0.55" strokeWidth="1.3" strokeLinecap="round" />
      <ellipse cx="16" cy="7" rx="11" ry="4" fill="url(#eyesLogoGradient)" />
      <ellipse cx="16" cy="7" rx="11" ry="4" fill="none" stroke="#ffffff" strokeOpacity="0.35" strokeWidth="1" />
      <circle cx="16" cy="7" r="2.6" fill="#ffffff" />
      <circle cx="16" cy="7" r="1.15" fill="#14122a" />
    </svg>
  );
}
