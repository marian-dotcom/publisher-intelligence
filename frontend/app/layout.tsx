import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AuthProvider } from "@/lib/auth-client";

import "./styles.css";

export const metadata: Metadata = {
  title: "Publisher Incident Intelligence",
  description: "Repository foundation for publisher operational memory.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
