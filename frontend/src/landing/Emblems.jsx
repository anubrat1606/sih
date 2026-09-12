// National symbols drawn to specification rather than pasted from an
// unlicensed image. The Ashoka Chakra is 24 spokes on a rim; the flag is
// 3:2 with the chakra's diameter three-quarters of the white band's height
// (Flag Code of India, Part I). Band colours are fixed in tokens.css and
// never themed; only --chakra-ink swaps in dark so the emblem stays legible.

function ChakraGeometry() {
  const spokes = Array.from({ length: 24 }, (_, i) => i * 15);
  return (
    <>
      <circle cx="50" cy="50" r="46" fill="none" stroke="currentColor" strokeWidth="5.5" />
      <circle cx="50" cy="50" r="7.5" fill="currentColor" />
      {spokes.map((deg) => (
        <polygon key={deg} points="48.6,50 50,7 51.4,50" fill="currentColor" transform={`rotate(${deg} 50 50)`} />
      ))}
      {spokes.map((deg) => (
        <circle key={`n${deg}`} cx="50" cy="9.5" r="1.9" fill="currentColor" transform={`rotate(${deg + 7.5} 50 50)`} />
      ))}
    </>
  );
}

export function AshokaChakra({ size = 48, className, title }) {
  return (
    <svg viewBox="0 0 100 100" width={size} height={size} className={className}
         role={title ? "img" : "presentation"} aria-hidden={title ? undefined : "true"} focusable="false">
      {title && <title>{title}</title>}
      <ChakraGeometry />
    </svg>
  );
}

export function IndianFlag({ height = 16, className, title = "Flag of India" }) {
  return (
    <svg viewBox="0 0 300 200" width={height * 1.5} height={height} className={className}
         role="img" aria-label={title} focusable="false">
      <rect width="300" height="66.67" fill="var(--india-saffron)" />
      <rect y="66.67" width="300" height="66.66" fill="var(--india-white)" />
      <rect y="133.33" width="300" height="66.67" fill="var(--india-green)" />
      <g transform="translate(125 75) scale(0.5)" style={{ color: "var(--india-navy)" }}>
        <ChakraGeometry />
      </g>
    </svg>
  );
}

export function EmblemRoundel({ size = 44, className }) {
  return (
    <svg viewBox="0 0 100 100" width={size} height={size} className={className} aria-hidden="true" focusable="false">
      <circle cx="50" cy="50" r="48" fill="var(--color-surface)" stroke="currentColor" strokeWidth="2.5" />
      <circle cx="50" cy="50" r="41" fill="none" stroke="currentColor" strokeWidth="0.75" opacity="0.5" />
      <g transform="translate(19 19) scale(0.62)"><ChakraGeometry /></g>
    </svg>
  );
}

const PATHS = {
  upload: "M12 16V4m0 0l-4 4m4-4l4 4M4 20h16",
  scan: "M4 7V4h3M17 4h3v3M20 17v3h-3M7 20H4v-3M8 12h8",
  shield: "M12 3l8 3v6c0 5-3.5 8.5-8 9-4.5-.5-8-4-8-9V6l8-3zM9 12l2 2 4-4",
  scale: "M12 3v18M6 7l-3 7a3.5 3.5 0 006 0L6 7zm12 0l-3 7a3.5 3.5 0 006 0l-3-7zM4 7h16",
  stamp: "M7 21h10M9 13h6l2 4H7l2-4zM12 3a3 3 0 00-3 3v7h6V6a3 3 0 00-3-3z",
  chain: "M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1-1",
  crosshair: "M12 2v4m0 12v4M2 12h4m12 0h4M12 8a4 4 0 100 8 4 4 0 000-8z",
  ban: "M12 3a9 9 0 100 18 9 9 0 000-18zM5.6 5.6l12.8 12.8",
  cpu: "M9 3v2m6-2v2M9 19v2m6-2v2M3 9h2m-2 6h2m14-6h2m-2 6h2M7 5h10a2 2 0 012 2v10a2 2 0 01-2 2H7a2 2 0 01-2-2V7a2 2 0 012-2zm2 4h6v6H9V9z",
  user: "M20 21a8 8 0 10-16 0M12 13a4 4 0 100-8 4 4 0 000 8z",
  arrow: "M5 12h14m-6-6l6 6-6 6",
  sun: "M12 4V2m0 20v-2m8-8h2M2 12h2m13.7-5.7l1.4-1.4M4.9 19.1l1.4-1.4m0-11.4L4.9 4.9m14.2 14.2l-1.4-1.4M12 8a4 4 0 100 8 4 4 0 000-8z",
  moon: "M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z",
  monitor: "M4 5h16v11H4zM8 21h8m-4-5v5",
  menu: "M4 6h16M4 12h16M4 18h16",
  close: "M6 6l12 12M18 6L6 18",
  file: "M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8l-5-5zm0 0v5h5M9 13h6m-6 4h6",
};

export function Icon({ name, size = 20, className }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} className={className} aria-hidden="true" focusable="false"
         fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d={PATHS[name]} />
    </svg>
  );
}
