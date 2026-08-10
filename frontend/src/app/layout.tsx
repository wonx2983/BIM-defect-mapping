import type { Metadata } from 'next';
import '@/styles/globals.css';

export const metadata: Metadata = {
  title: 'DefectSync — Construction Defect Detection & BIM Mapping',
  description:
    'AI-powered construction defect detection with severity grading and automated BIM mapping for quality management professionals.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
