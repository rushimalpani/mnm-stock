import { useEffect, useState } from 'react';

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
};

function isIos() {
  if (typeof navigator === 'undefined') return false;
  return /iphone|ipad|ipod/i.test(navigator.userAgent);
}

function isStandalone() {
  if (typeof window === 'undefined') return true;
  const nav = window.navigator as Navigator & { standalone?: boolean };
  return window.matchMedia('(display-mode: standalone)').matches || nav.standalone === true;
}

/**
 * Shows how to install the PWA on Android (native prompt) or iOS (Share → Add to Home Screen).
 */
export function InstallPrompt() {
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null);
  const [showIosHelp, setShowIosHelp] = useState(false);
  const [dismissed, setDismissed] = useState(() => {
    try {
      return localStorage.getItem('mnm-pwa-dismissed') === '1';
    } catch {
      return false;
    }
  });

  useEffect(() => {
    if (isStandalone() || dismissed) return;

    const onBip = (e: Event) => {
      e.preventDefault();
      setDeferred(e as BeforeInstallPromptEvent);
    };
    window.addEventListener('beforeinstallprompt', onBip);

    if (isIos()) {
      setShowIosHelp(true);
    }

    return () => window.removeEventListener('beforeinstallprompt', onBip);
  }, [dismissed]);

  if (dismissed || isStandalone()) return null;
  if (!deferred && !showIosHelp) return null;

  function dismiss() {
    setDismissed(true);
    setDeferred(null);
    setShowIosHelp(false);
    try {
      localStorage.setItem('mnm-pwa-dismissed', '1');
    } catch {
      /* ignore */
    }
  }

  async function install() {
    if (!deferred) return;
    await deferred.prompt();
    await deferred.userChoice;
    setDeferred(null);
    dismiss();
  }

  return (
    <div className="mb-4 rounded-2xl border border-[var(--accent)]/25 bg-teal-50 px-4 py-3 text-sm sm:text-base">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold text-[var(--accent-2)]">Install MNM Stock on your phone</p>
          {deferred ? (
            <p className="mt-1 text-[var(--muted)]">
              Add to your home screen for quick search — works like an app.
            </p>
          ) : (
            <p className="mt-1 text-[var(--muted)]">
              On iPhone/iPad: tap <strong>Share</strong> → <strong>Add to Home Screen</strong>.
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={dismiss}
          className="shrink-0 rounded-lg px-2 py-1 text-[var(--muted)]"
          aria-label="Dismiss"
        >
          ✕
        </button>
      </div>
      {deferred ? (
        <button
          type="button"
          onClick={() => void install()}
          className="mt-3 min-h-11 w-full rounded-xl bg-[var(--accent)] px-4 py-2.5 font-semibold text-white sm:w-auto"
        >
          Install app
        </button>
      ) : null}
    </div>
  );
}
