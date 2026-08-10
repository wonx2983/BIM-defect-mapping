export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background:
          'radial-gradient(ellipse at 20% 50%, hsla(210, 100%, 20%, 0.3) 0%, transparent 50%), radial-gradient(ellipse at 80% 20%, hsla(280, 100%, 20%, 0.2) 0%, transparent 50%), var(--color-bg)',
      }}
    >
      {children}
    </div>
  );
}
