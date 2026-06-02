import { useEffect, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

export function MobileSheet({
  open,
  variant = 'fullscreen',
  hiddenAt = 'md',
  onClose,
  children,
}: {
  open: boolean;
  variant?: 'drawer' | 'fullscreen';
  hiddenAt?: 'md' | 'xl';
  onClose: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!open) return undefined;

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
    }

    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [onClose, open]);

  if (!open) return null;

  return (
    <div
      className={cn(
        'fixed inset-0 z-50 flex bg-slate-950/70 backdrop-blur-sm',
        hiddenAt === 'md' ? 'md:hidden' : 'xl:hidden',
      )}
      role="dialog"
      aria-modal="true"
    >
      <div
        className={cn(
          'min-h-0 overflow-hidden bg-slate-900 shadow-2xl',
          variant === 'drawer'
            ? 'h-full w-[min(22rem,calc(100vw-3rem))] border-r border-slate-800'
            : 'h-full w-full',
        )}
      >
        {children}
      </div>
      {variant === 'drawer' && (
        <button
          type="button"
          onClick={onClose}
          className="min-w-0 flex-1"
          aria-label="关闭浮层"
        />
      )}
    </div>
  );
}
