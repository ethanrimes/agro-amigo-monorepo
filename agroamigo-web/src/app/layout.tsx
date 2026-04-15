import type { Metadata } from 'next';
import './globals.css';
import { Providers } from './providers';
import { AppShell } from './app-shell';

export const metadata: Metadata = {
  title: 'AgroAmigo',
  description: 'Precios y abastecimiento agropecuario de Colombia',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
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
