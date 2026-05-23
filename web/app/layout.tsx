import type { Metadata } from "next";
import Nav from "@/components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "openmc2donjon",
  description:
    "Web interface for openmc2donjon: build production handoffs from OpenMC MGXS to DRAGON/DONJON deterministic workflows.",
  applicationName: "openmc2donjon",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <Nav />
        {children}
      </body>
    </html>
  );
}
