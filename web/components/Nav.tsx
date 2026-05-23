"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type Item = {
  href: string;
  label: string;
};

const ITEMS: Item[] = [
  { href: "/", label: "Home" },
  { href: "/inspect", label: "Inspect" },
];

export default function Nav() {
  const pathname = usePathname();

  return (
    <nav
      className="sticky top-0 z-10 border-b border-[var(--edge)] bg-[rgba(10,11,15,0.7)] backdrop-blur"
      aria-label="Primary"
    >
      <div className="mx-auto max-w-5xl px-6 py-3 flex items-center justify-between gap-6">
        <Link
          href="/"
          className="text-sm font-semibold tracking-tight"
          aria-label="openmc2donjon home"
        >
          <span className="grad-text">openmc2donjon</span>
        </Link>
        <ul className="flex items-center gap-1 text-sm">
          {ITEMS.map((item) => {
            const active = pathname === item.href;
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={
                    "px-3 py-1.5 rounded-md border transition " +
                    (active
                      ? "border-[var(--edge-bright)] bg-white/[0.06] text-[var(--fg-0)]"
                      : "border-transparent text-[var(--fg-2)] hover:text-[var(--fg-0)] hover:bg-white/[0.04]")
                  }
                  aria-current={active ? "page" : undefined}
                >
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </div>
    </nav>
  );
}
