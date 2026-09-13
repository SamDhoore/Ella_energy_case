import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Belgian Weather Explorer",
  description: "Open-Meteo forecasts for Belgian cities and how they were revised over time.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-background font-sans antialiased">{children}</body>
    </html>
  );
}
