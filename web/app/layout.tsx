import type { Metadata } from "next";
import { Suspense } from "react";
import Nav from "@/components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "openmc2donjon Converter",
  description:
    "Convert validated OpenMC MGXS handoffs into traceable DRAGON/DONJON objects. Project manifests define components, physics contracts, and downstream consumers.",
  applicationName: "openmc2donjon",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <a href="#main-content" className="btn btn-primary skip-link">
          Skip to main content
        </a>
        <Suspense fallback={<div className="h-[68px] border-b border-[var(--edge)] bg-[rgba(7,16,25,0.9)]" />}>
          <Nav />
        </Suspense>
        <div id="main-content" tabIndex={-1}>
          {children}
        </div>
      </body>
    </html>
  );
}
