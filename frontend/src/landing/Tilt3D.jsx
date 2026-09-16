import { useEffect, useRef } from "react";

// Real CSS 3D, not a bigger drop-shadow: the wrapped element sits in a
// perspective scene and tilts toward the pointer (rotateX/rotateY) with a
// translateZ lift and a pointer-tracked specular highlight, all through
// native transforms -- no canvas, no WebGL, hardware-accelerated. Disabled
// entirely under prefers-reduced-motion and on touch (no hover to track),
// where the element just renders flat and static.
export default function Tilt3D({ children, className, strength = 10, lift = 18, glare = true, as: Tag = "div", ...rest }) {
  const ref = useRef(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const touch = window.matchMedia("(hover: none)").matches;
    if (reduced || touch) return undefined;

    let raf = null;
    function onMove(e) {
      const rect = el.getBoundingClientRect();
      const px = (e.clientX - rect.left) / rect.width;   // 0..1
      const py = (e.clientY - rect.top) / rect.height;
      if (raf) cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const rx = (0.5 - py) * strength;
        const ry = (px - 0.5) * strength;
        el.style.transform = `perspective(900px) rotateX(${rx}deg) rotateY(${ry}deg) translateZ(${lift}px)`;
        if (glare) {
          el.style.setProperty("--tilt-glare-x", `${px * 100}%`);
          el.style.setProperty("--tilt-glare-y", `${py * 100}%`);
          el.style.setProperty("--tilt-glare-o", "1");
        }
      });
    }
    function onLeave() {
      if (raf) cancelAnimationFrame(raf);
      el.style.transform = "perspective(900px) rotateX(0deg) rotateY(0deg) translateZ(0px)";
      if (glare) el.style.setProperty("--tilt-glare-o", "0");
    }
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", onLeave);
    return () => {
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
      if (raf) cancelAnimationFrame(raf);
    };
  }, [strength, lift, glare]);

  return (
    <Tag ref={ref} className={`tilt-3d${glare ? " tilt-3d-glare" : ""}${className ? ` ${className}` : ""}`} {...rest}>
      {children}
    </Tag>
  );
}
