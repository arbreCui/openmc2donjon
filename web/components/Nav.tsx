"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  isAnyNavItemActive,
  isNavItemActive,
  PRIMARY_NAV_ITEMS,
  SECONDARY_NAV_ITEMS,
  type NavItem,
} from "@/lib/navigation";

export default function Nav() {
  const pathname = usePathname();
  const [moreOpen, setMoreOpen] = useState(false);
  const moreActive = isAnyNavItemActive(SECONDARY_NAV_ITEMS, pathname);

  useEffect(() => {
    setMoreOpen(false);
  }, [pathname]);

  return (
    <nav
      className="sticky top-0 z-10 border-b border-[var(--edge)] bg-[rgba(10,11,15,0.7)] backdrop-blur"
      aria-label="Primary"
    >
      <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-3 px-6 py-3 lg:flex-row lg:items-center lg:gap-6">
        <Link
          href="/"
          className="shrink-0 text-sm font-semibold tracking-tight"
          aria-label="openmc2donjon home"
        >
          <span className="grad-text">openmc2donjon</span>
        </Link>
        <ul className="flex w-full flex-wrap items-center gap-1 text-sm lg:w-auto lg:justify-end">
          {PRIMARY_NAV_ITEMS.map((item) => (
            <li key={item.href}>
              <NavLink item={item} active={isNavItemActive(item, pathname)} />
            </li>
          ))}
          <li className="relative">
            <button
              type="button"
              onClick={() => setMoreOpen((value) => !value)}
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  setMoreOpen(false);
                }
              }}
              className={
                navClass(moreActive || moreOpen) +
                " inline-flex items-center gap-1.5"
              }
              aria-haspopup="menu"
              aria-expanded={moreOpen}
            >
              More
              <span
                aria-hidden="true"
                className={
                  "h-0 w-0 border-x-[4px] border-t-[5px] border-x-transparent border-t-current transition " +
                  (moreOpen ? "rotate-180" : "")
                }
              />
            </button>
            {moreOpen ? (
              <div
                className="absolute right-auto top-full mt-2 w-[min(21rem,calc(100vw-3rem))] rounded-lg border border-[var(--edge-bright)] bg-[rgba(14,16,22,0.98)] p-2 shadow-2xl shadow-black/40 backdrop-blur lg:right-0"
                role="menu"
              >
                {SECONDARY_NAV_ITEMS.map((item) => {
                  const active = isNavItemActive(item, pathname);
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      role="menuitem"
                      className={
                        "block rounded-md border px-3 py-2 transition " +
                        (active
                          ? "border-[var(--edge-bright)] bg-white/[0.06]"
                          : "border-transparent hover:bg-white/[0.045]")
                      }
                      aria-current={active ? "page" : undefined}
                    >
                      <span className="block text-sm font-medium text-[var(--fg-0)]">
                        {item.label}
                      </span>
                      {item.description ? (
                        <span className="mt-0.5 block text-[12px] leading-5 text-[var(--fg-2)]">
                          {item.description}
                        </span>
                      ) : null}
                    </Link>
                  );
                })}
              </div>
            ) : null}
          </li>
        </ul>
      </div>
    </nav>
  );
}

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  return (
    <Link
      href={item.href}
      className={navClass(active)}
      aria-current={active ? "page" : undefined}
    >
      {item.label}
    </Link>
  );
}

function navClass(active: boolean): string {
  return (
    "block whitespace-nowrap rounded-md border px-3 py-1.5 transition " +
    (active
      ? "border-[var(--edge-bright)] bg-white/[0.06] text-[var(--fg-0)]"
      : "border-transparent text-[var(--fg-2)] hover:bg-white/[0.04] hover:text-[var(--fg-0)]")
  );
}
