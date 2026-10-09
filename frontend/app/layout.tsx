import type { Metadata, Viewport } from "next";
import { DM_Sans } from "next/font/google";
import "./globals.css";
import ClientProviders from "./ClientProviders";

// DM Sans — the only font for Pixie dashboard
const dmSans = DM_Sans({
  subsets: ["latin"],
  variable: "--font-dm-sans",
  weight: ["400", "500", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Pixie Demo | Study Partner",
  description: "A patient study partner that learns how you think.",
  manifest: "/manifest.webmanifest",
  other: { "pixie-build-revision": process.env.NEXT_PUBLIC_BUILD_REVISION || "unversioned" },
  appleWebApp: { capable: true, statusBarStyle: "default", title: "Pixie Demo" },
};

export const viewport: Viewport = {
  themeColor: "#FAF8F3",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={dmSans.variable}>
      <body>
        <ClientProviders>{children}</ClientProviders>
      </body>
    </html>
  );
}
