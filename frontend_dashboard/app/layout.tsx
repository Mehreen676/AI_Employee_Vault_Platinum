import type { Metadata } from 'next';
import './globals.css';
import { Sidebar } from '@/components/Sidebar';

export const metadata: Metadata = {
  title: 'AI Vault – Platinum Dashboard',
  description: 'AI Employee Vault Platinum Tier — Distributed AI Task Management System',
  icons: { icon: '/favicon.ico' },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="bg-vault-bg text-vault-text min-h-screen grid-bg">
        <div className="flex min-h-screen">
          <Sidebar />
          {/* Main content offset by sidebar width */}
          <div className="flex-1 ml-60 min-h-screen flex flex-col">
            {children}
          </div>
        </div>
      </body>
    </html>
  );
}
