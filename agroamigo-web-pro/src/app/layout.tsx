import type { Metadata } from 'next';
import './globals.css';
import { Providers } from './providers';
import { Sidebar } from '@/components/Sidebar';
import { TopBar } from '@/components/TopBar';

export const metadata: Metadata = {
  title: 'AgroAmigo — Desktop',
  description: 'Precios y abastecimiento agropecuario de Colombia — vista web profesional',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>
        <Providers>
          <div className="app">
            <Sidebar />
            <div className="main">
              <TopBar />
              <div className="content">{children}</div>
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}
