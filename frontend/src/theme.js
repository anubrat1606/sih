// Canvas APIs (react-force-graph-2d's nodeColor/linkColor/fillStyle) don't
// understand CSS custom properties -- var() only resolves inside the CSS
// cascade, never as a literal string handed to a 2D rendering context. This
// reads the live resolved value instead. Safe to call every animation
// frame: it's cheap, and re-reading each time is what keeps canvas colours
// correct across a theme toggle without any extra wiring.
export function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
