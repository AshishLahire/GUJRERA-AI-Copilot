import React from "react";
import { useSaathi } from "./context";
import { StringKey, tr } from "./strings";

/** The English text of a label, shown small under it when the page is in Gujarati or Hindi, so
 * English readers can follow. Shows nothing in English mode. */
export const En: React.FC<{ k: StringKey; className?: string }> = ({ k, className = "" }) => {
  const { lang } = useSaathi();
  if (lang === "en") return null;
  return (
    <span lang="en" className={`block text-[0.72em] leading-snug font-medium opacity-70 ${className}`}>
      {tr(k, "en")}
    </span>
  );
};
