// Header logosu — çizim src/brand/logo.js'ten (favicon ile aynı kaynak).
import React from "react";
import { LOGO_ELEMENTS, LOGO_STROKE, LOGO_VIEWBOX } from "../brand/logo.js";

export default function Logo({ className = "h-5 w-5 text-accent", strokeWidth = LOGO_STROKE }) {
  return (
    <svg
      viewBox={LOGO_VIEWBOX}
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {LOGO_ELEMENTS.map(({ tag: Tag, ...attrs }, i) => (
        <Tag key={i} {...attrs} />
      ))}
    </svg>
  );
}
