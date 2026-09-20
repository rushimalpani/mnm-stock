import { NavLink, Outlet } from 'react-router-dom';
import { InstallPrompt } from './InstallPrompt';

const desktopLink = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-2 rounded-xl text-sm font-medium whitespace-nowrap transition ${
    isActive
      ? 'bg-[var(--accent)] text-white shadow-sm'
      : 'text-[var(--muted)] hover:bg-white hover:text-[var(--ink)]'
  }`;

const mobileLink = ({ isActive }: { isActive: boolean }) =>
  `flex flex-1 flex-col items-center justify-center gap-0.5 py-2 text-[11px] font-semibold ${
    isActive ? 'text-[var(--accent)]' : 'text-[var(--muted)]'
  }`;

export function Layout() {
  return (
    <div className="min-h-dvh pb-[calc(var(--nav-h)+env(safe-area-inset-bottom))] md:pb-0">
      <header className="safe-top sticky top-0 z-20 border-b border-[var(--line)] bg-white/95 backdrop-blur-md">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-3 px-3 py-3 sm:px-4">
          <div className="flex min-w-0 items-center gap-2.5">
            <img
              src="/logo-512.png"
              alt=""
              width={40}
              height={40}
              className="h-10 w-10 shrink-0 rounded-full bg-white object-contain ring-1 ring-[var(--line)]"
            />
            <div className="min-w-0">
              <p className="font-[family-name:var(--font-display)] text-xl leading-none sm:text-2xl">
                MNM Stock
              </p>
              <p className="mt-1 truncate text-xs text-[var(--muted)] sm:text-sm">Find stock easily</p>
            </div>
          </div>
          <nav className="hidden flex-wrap justify-end gap-1 md:flex">
            <NavLink to="/" end className={desktopLink}>
              Find Stock
            </NavLink>
            <NavLink to="/upload" className={desktopLink}>
              Add PDF
            </NavLink>
            <NavLink to="/dashboard" className={desktopLink}>
              Summary
            </NavLink>
            <NavLink to="/reports" className={desktopLink}>
              Old Reports
            </NavLink>
          </nav>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl px-3 py-4 sm:px-4 sm:py-6">
        <InstallPrompt />
        <Outlet />
      </main>

      <nav className="safe-bottom fixed inset-x-0 bottom-0 z-30 border-t border-[var(--line)] bg-white/95 backdrop-blur-md md:hidden">
        <div className="mx-auto flex h-[var(--nav-h)] max-w-5xl">
          <NavLink to="/" end className={mobileLink}>
            <span className="text-lg leading-none" aria-hidden>
              🔍
            </span>
            Find
          </NavLink>
          <NavLink to="/upload" className={mobileLink}>
            <span className="text-lg leading-none" aria-hidden>
              📄
            </span>
            Add PDF
          </NavLink>
          <NavLink to="/dashboard" className={mobileLink}>
            <span className="text-lg leading-none" aria-hidden>
              📊
            </span>
            Summary
          </NavLink>
          <NavLink to="/reports" className={mobileLink}>
            <span className="text-lg leading-none" aria-hidden>
              📁
            </span>
            Reports
          </NavLink>
        </div>
      </nav>
    </div>
  );
}
