import type { Metadata, Viewport } from "next";
import "./globals.css";
import "./field-theme.css";
import { Providers } from "./providers";
import { AppShell } from "./app-shell";

export const metadata: Metadata = {
  title: "AgroAmigo",
  description:
    "Clima, cultivos, precios y cuentas claras para el campo colombiano",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#ffffff",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es">
      <body>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
