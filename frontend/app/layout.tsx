import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Tatva AI - Bengaluru Rental Expert",
  description: "Find your perfect home with commute optimization.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased bg-white text-slate-900">
        {children}
      </body>
    </html>
  );
}