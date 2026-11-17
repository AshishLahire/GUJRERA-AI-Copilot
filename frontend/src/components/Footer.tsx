import React from "react";

export const Footer: React.FC = () => {
  return (
    <footer className="mt-auto border-t border-warm-border bg-card py-4 text-center">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6">
        <p className="text-[11px] text-muted leading-relaxed">
          &copy; 2026 YellowSense Technologies &middot; Prototype for the Nasscom &times; Fujitsu (FRIPL) collaboration &middot; Decision support, not a content-removal tool.
        </p>
      </div>
    </footer>
  );
};
