"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import {
  isAnyNavItemActive,
  isNavItemActive,
  PRIMARY_NAV_ITEMS,
  SECONDARY_NAV_ITEMS,
  WORKFLOW_NAV_ITEMS,
  type NavItem,
} from "@/lib/navigation";

export default function Nav() {
  const pathname = usePathname();
  const [moreOpen, setMoreOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [mockMode, setMockMode] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const moreActive = isAnyNavItemActive(
    [...WORKFLOW_NAV_ITEMS, ...SECONDARY_NAV_ITEMS],
    pathname,
  );
  const primaryItems = PRIMARY_NAV_ITEMS;

  useEffect(() => {
    setMoreOpen(false);
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    let cancelled = false;
    api
      .health()
      .then((data) => {
        if (!cancelled) setMockMode(data.mock_mode);
      })
      .catch(() => {
        // An unavailable backend is surfaced on workflow pages, not in nav.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!moreOpen && !mobileOpen) return;
    function closeOnOutsidePointer(event: PointerEvent) {
      if (
        menuRef.current &&
        event.target instanceof Node &&
        !menuRef.current.contains(event.target)
      ) {
        setMoreOpen(false);
        setMobileOpen(false);
      }
    }
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMoreOpen(false);
        setMobileOpen(false);
      }
    }
    document.addEventListener("pointerdown", closeOnOutsidePointer);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsidePointer);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [mobileOpen, moreOpen]);

  return (
    <nav
      className="sticky top-0 z-50 border-b border-[var(--edge)] bg-[rgba(7,16,25,0.9)] shadow-lg shadow-black/10 backdrop-blur-xl"
      aria-label="Primary"
    >
      <div ref={menuRef} className="mx-auto max-w-[1240px] px-4 sm:px-6">
        <div className="flex min-h-[68px] items-center gap-4">
          <Link
            href="/"
            className="group flex shrink-0 items-center gap-2.5"
            aria-label="openmc2donjon overview"
          >
            <span className="grid h-9 w-9 place-items-center rounded-xl border border-emerald-200/20 bg-emerald-300/10 font-mono text-[11px] font-bold text-[var(--accent)] shadow-inner shadow-emerald-300/10">
              O→D
            </span>
            <span>
              <span className="block text-[13px] font-bold tracking-[-0.02em] text-[var(--fg-0)]">
                openmc2donjon
              </span>
              <span className="hidden text-[9px] uppercase tracking-[0.16em] text-[var(--fg-3)] xl:block">
                Converter workflow
              </span>
            </span>
          </Link>

          <div className="hidden min-w-0 flex-1 items-center justify-center gap-1 md:flex">
            {primaryItems.map((item) => (
              <NavLink
                key={item.href}
                item={item}
                active={isNavItemActive(item, pathname)}
              />
            ))}
          </div>

          <div className="ml-auto flex shrink-0 items-center gap-2">
            {mockMode ? (
              <span className="hidden rounded-full border border-amber-300/25 bg-amber-300/10 px-2 py-1 text-[9px] font-bold uppercase tracking-[0.14em] text-amber-200 sm:inline-flex">
                mock
              </span>
            ) : null}

            <div className="relative hidden md:block">
              <button
                type="button"
                onClick={() => setMoreOpen((value) => !value)}
                className={navButtonClass(moreActive || moreOpen)}
                aria-expanded={moreOpen}
                aria-controls="tools-navigation"
              >
                Tools
                <Chevron open={moreOpen} />
              </button>
              {moreOpen ? (
                <ToolMenu pathname={pathname} onNavigate={() => setMoreOpen(false)} />
              ) : null}
            </div>

            <button
              type="button"
              onClick={() => setMobileOpen((value) => !value)}
              className="btn btn-secondary md:hidden"
              aria-expanded={mobileOpen}
              aria-controls="mobile-navigation"
            >
              {mobileOpen ? "Close" : "Menu"}
            </button>
          </div>
        </div>

        {mobileOpen ? (
          <div
            id="mobile-navigation"
            className="border-t border-[var(--edge)] py-4 md:hidden"
          >
            <MenuSectionLabel>Core</MenuSectionLabel>
            <div className="grid gap-2 sm:grid-cols-2">
              {primaryItems.map((item) => (
                <MobileLink
                  key={item.href}
                  item={item}
                  active={isNavItemActive(item, pathname)}
                  onNavigate={() => setMobileOpen(false)}
                />
              ))}
            </div>
            <div className="my-4 border-t border-[var(--edge)]" />
            <MenuSectionLabel>Model workflows</MenuSectionLabel>
            <div className="grid gap-2 sm:grid-cols-2">
              {WORKFLOW_NAV_ITEMS.map((item) => (
                <MobileLink
                  key={item.href}
                  item={item}
                  active={isNavItemActive(item, pathname)}
                  onNavigate={() => setMobileOpen(false)}
                />
              ))}
            </div>
            <div className="my-4 border-t border-[var(--edge)]" />
            <MenuSectionLabel>Advanced tools</MenuSectionLabel>
            <div className="grid gap-2 sm:grid-cols-2">
              {SECONDARY_NAV_ITEMS.map((item) => (
                <MobileLink
                  key={item.href}
                  item={item}
                  active={isNavItemActive(item, pathname)}
                  onNavigate={() => setMobileOpen(false)}
                />
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </nav>
  );
}

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  const isUtility = item.step == null && item.href !== "/";
  const isConverter = item.label === "Converter";
  return (
    <Link
      href={item.href}
      className={
        "flex min-h-[42px] items-center gap-1.5 whitespace-nowrap rounded-lg border px-3 text-[13px] font-semibold transition " +
        (active
          ? "border-emerald-300/25 bg-emerald-300/10 text-emerald-100"
          : isConverter
            ? "border-emerald-300/20 bg-emerald-300/[0.055] text-[var(--fg-0)] hover:border-emerald-300/35 hover:bg-emerald-300/10"
          : isUtility
            ? "border-transparent text-[var(--fg-2)] hover:border-[var(--edge)] hover:bg-white/[0.04] hover:text-[var(--fg-0)]"
            : "border-transparent text-[var(--fg-2)] hover:bg-white/[0.04] hover:text-[var(--fg-0)]")
      }
      aria-current={active ? "page" : undefined}
    >
      {item.step ? (
        <span
          className={
            "font-mono text-[9px] " +
            (active ? "text-[var(--accent)]" : "text-[var(--fg-3)]")
          }
        >
          {item.step}
        </span>
      ) : null}
      {item.label}
    </Link>
  );
}

function MobileLink({
  item,
  active,
  onNavigate,
}: {
  item: NavItem;
  active: boolean;
  onNavigate: () => void;
}) {
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      className={
        "rounded-xl border px-3 py-3 transition " +
        (active
          ? "border-emerald-300/25 bg-emerald-300/10"
          : "border-[var(--edge)] bg-white/[0.025]")
      }
      aria-current={active ? "page" : undefined}
    >
      <span className="flex items-center gap-2 text-sm font-semibold">
        {item.step ? (
          <span className="font-mono text-[10px] text-[var(--accent)]">
            {item.step}
          </span>
        ) : null}
        {item.label}
      </span>
      {item.description ? (
        <span className="mt-1 block text-[11px] leading-4 text-[var(--fg-3)]">
          {item.description}
        </span>
      ) : null}
    </Link>
  );
}

function ToolMenu({
  pathname,
  onNavigate,
}: {
  pathname: string;
  onNavigate: () => void;
}) {
  return (
    <div
      id="tools-navigation"
      className="absolute right-0 top-full mt-2 w-[21rem] rounded-xl border border-[var(--edge-bright)] bg-[rgba(10,22,32,0.98)] p-2 shadow-2xl shadow-black/45"
      aria-label="Additional navigation"
    >
      <div className="px-2 pb-2 pt-1 text-[9px] font-bold uppercase tracking-[0.16em] text-[var(--fg-3)]">
        Model workflows
      </div>
      {WORKFLOW_NAV_ITEMS.map((item) => (
        <ToolMenuLink
          key={item.href}
          item={item}
          active={isNavItemActive(item, pathname)}
          onNavigate={onNavigate}
        />
      ))}
      <div className="my-2 border-t border-[var(--edge)]" />
      <div className="px-2 pb-2 pt-1 text-[9px] font-bold uppercase tracking-[0.16em] text-[var(--fg-3)]">
        Advanced tools
      </div>
      {SECONDARY_NAV_ITEMS.map((item) => (
        <ToolMenuLink
          key={item.href}
          item={item}
          active={isNavItemActive(item, pathname)}
          onNavigate={onNavigate}
        />
      ))}
    </div>
  );
}

function ToolMenuLink({
  item,
  active,
  onNavigate,
}: {
  item: NavItem;
  active: boolean;
  onNavigate: () => void;
}) {
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      className={
        "block rounded-lg border px-3 py-2.5 transition " +
        (active
          ? "border-emerald-300/20 bg-emerald-300/[0.08]"
          : "border-transparent hover:bg-white/[0.05]")
      }
      aria-current={active ? "page" : undefined}
    >
      <span className="block text-sm font-semibold text-[var(--fg-0)]">
        {item.label}
      </span>
      {item.description ? (
        <span className="mt-0.5 block text-[11px] leading-4 text-[var(--fg-3)]">
          {item.description}
        </span>
      ) : null}
    </Link>
  );
}

function MenuSectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-2 px-1 text-[9px] font-bold uppercase tracking-[0.16em] text-[var(--fg-3)]">
      {children}
    </div>
  );
}

function Chevron({ open }: { open: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={
        "h-0 w-0 border-x-[3px] border-t-[4px] border-x-transparent border-t-current transition " +
        (open ? "rotate-180" : "")
      }
    />
  );
}

function navButtonClass(active: boolean): string {
  return (
    "flex min-h-[42px] items-center gap-1.5 rounded-lg border px-3 text-[13px] font-semibold transition " +
    (active
      ? "border-emerald-300/25 bg-emerald-300/10 text-emerald-100"
      : "border-[var(--edge)] text-[var(--fg-2)] hover:border-[var(--edge-bright)] hover:text-[var(--fg-0)]")
  );
}
