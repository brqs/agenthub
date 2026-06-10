import { useState } from 'react';
import { Link2, Plus, Server, Trash2 } from 'lucide-react';
import { useDesktopEnvironment } from '@/hooks/useDesktopEnvironment';

export function DesktopBackendProfilesPanel({ compact = false }: { compact?: boolean }) {
  const desktop = useDesktopEnvironment();
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [busyId, setBusyId] = useState<string | null>(null);

  async function connect(profileId: string) {
    setBusyId(profileId);
    try {
      await desktop.activateBackendProfile(profileId);
    } finally {
      setBusyId(null);
    }
  }

  async function testActiveProfile(url: string, profileId: string) {
    setBusyId(profileId);
    try {
      await desktop.checkBackend(url);
    } finally {
      setBusyId(null);
    }
  }

  async function saveProfile() {
    setBusyId('new');
    try {
      const profile = await desktop.saveBackendProfile({ name, url });
      if (!profile) return;
      setName('');
      setUrl('');
      setAdding(false);
      await connect(profile.id);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section
      className={
        compact
          ? 'mt-5 border-t border-slate-200 pt-4 dark:border-slate-800'
          : 'rounded-md border border-slate-200 bg-white/80 p-3 dark:border-slate-700 dark:bg-slate-950/35'
      }
    >
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            后端连接
          </h3>
          <p className="mt-1 text-xs leading-5 text-slate-500">
            同一账号连接同一服务器，即可在不同设备查看相同会话。
          </p>
        </div>
        <button
          type="button"
          onClick={() => setAdding((value) => !value)}
          className="inline-flex shrink-0 items-center gap-1 rounded-md border border-slate-300 px-2.5 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          <Plus className="h-3.5 w-3.5" />
          添加
        </button>
      </div>

      <div className="mt-3 space-y-2">
        {desktop.backendProfiles.map((profile) => {
          const active = profile.id === desktop.activeBackendProfileId;
          const profileHealthError =
            desktop.health &&
            sameBackendUrl(desktop.health.url, profile.url) &&
            desktop.health.status !== 'ready'
              ? desktop.health.error
              : null;
          return (
            <div
              key={profile.id}
              className={`flex items-center gap-3 rounded-md border px-3 py-2 ${
                active
                  ? 'border-indigo-300 bg-indigo-50 dark:border-indigo-500/50 dark:bg-indigo-500/10'
                  : 'border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900'
              }`}
            >
              <Server className="h-4 w-4 shrink-0 text-indigo-500" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm font-medium text-slate-900 dark:text-slate-100">
                    {profile.name}
                  </span>
                  {active && (
                    <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-[11px] text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-200">
                      当前
                    </span>
                  )}
                </div>
                <p className="truncate text-xs text-slate-500" title={profile.url}>
                  {profile.url}
                </p>
                {isPlainHttpRemote(profile.url) && (
                  <p className="mt-0.5 text-[11px] text-amber-600 dark:text-amber-300">
                    HTTP 明文连接，仅建议内网或临时测试使用
                  </p>
                )}
                {profile.lastHealth === 'unreachable' && !profileHealthError && (
                  <p className="mt-0.5 text-[11px] text-rose-600 dark:text-rose-300">
                    暂时无法连接
                  </p>
                )}
                {profileHealthError && (
                  <p className="mt-0.5 text-[11px] leading-4 text-rose-600 dark:text-rose-300">
                    {profileHealthError}
                  </p>
                )}
                {profile.lastHealth === 'incompatible' && (
                  <p className="mt-0.5 text-[11px] text-rose-600 dark:text-rose-300">
                    服务器身份已变化
                  </p>
                )}
              </div>
              {active ? (
                <button
                  type="button"
                  onClick={() => testActiveProfile(profile.url, profile.id)}
                  disabled={busyId !== null}
                  className="inline-flex items-center gap-1 rounded-md border border-indigo-300 px-2 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-50 disabled:opacity-50 dark:border-indigo-500/50 dark:text-indigo-200 dark:hover:bg-indigo-500/10"
                >
                  <Link2 className="h-3.5 w-3.5" />
                  {busyId === profile.id ? '测试中' : '测试'}
                </button>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => connect(profile.id)}
                    disabled={busyId !== null}
                    className="inline-flex items-center gap-1 rounded-md border border-indigo-300 px-2 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-50 disabled:opacity-50 dark:border-indigo-500/50 dark:text-indigo-200 dark:hover:bg-indigo-500/10"
                  >
                    <Link2 className="h-3.5 w-3.5" />
                    {busyId === profile.id ? '连接中' : '连接'}
                  </button>
                  <button
                    type="button"
                    onClick={() => desktop.deleteBackendProfile(profile.id)}
                    disabled={busyId !== null}
                    className="rounded-md p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600 disabled:opacity-50 dark:hover:bg-rose-500/10"
                    title="删除连接"
                    aria-label={`删除连接 ${profile.name}`}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </>
              )}
            </div>
          );
        })}
      </div>

      {adding && (
        <div className="mt-3 grid gap-2 rounded-md border border-dashed border-slate-300 p-3 dark:border-slate-700">
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="连接名称，例如：我的公网 AgentHub"
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500 dark:border-slate-700 dark:bg-slate-950"
          />
          <input
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="http://111.229.151.159:8000 或 https://agenthub.example.com"
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500 dark:border-slate-700 dark:bg-slate-950"
          />
          {isPlainHttpRemote(url) && (
            <p className="text-xs leading-5 text-amber-600 dark:text-amber-300">
              当前地址使用 HTTP 明文连接，登录态和请求内容不会被传输层加密。建议仅用于内网、测试机或临时部署。
            </p>
          )}
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setAdding(false)}
              className="rounded-md px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              取消
            </button>
            <button
              type="button"
              onClick={saveProfile}
              disabled={!name.trim() || !url.trim() || busyId !== null}
              className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
            >
              保存并连接
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function isPlainHttpRemote(value: string): boolean {
  try {
    const url = new URL(value.trim());
    if (url.protocol !== 'http:') return false;
    const host = url.hostname.toLowerCase();
    return host !== 'localhost' && host !== '127.0.0.1' && host !== '::1';
  } catch {
    return false;
  }
}

function sameBackendUrl(a: string, b: string): boolean {
  return a.trim().replace(/\/+$/, '') === b.trim().replace(/\/+$/, '');
}
