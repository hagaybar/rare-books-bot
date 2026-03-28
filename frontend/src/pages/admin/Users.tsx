import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { fetchUsers, createUserApi, updateUserApi } from '../../api/auth';
import type { UserListItem } from '../../api/auth';
import { useAuthStore } from '../../stores/authStore';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ROLES = ['admin', 'full', 'limited', 'guest'] as const;

const ROLE_BADGE: Record<string, string> = {
  admin: 'bg-red-100 text-red-800',
  full: 'bg-blue-100 text-blue-800',
  limited: 'bg-yellow-100 text-yellow-800',
  guest: 'bg-gray-100 text-gray-700',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function RoleBadge({ role }: { role: string }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${ROLE_BADGE[role] ?? 'bg-gray-100 text-gray-700'}`}
    >
      {role}
    </span>
  );
}

function formatDate(iso: string | null): string {
  if (!iso) return 'Never';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

// ---------------------------------------------------------------------------
// Create User Dialog
// ---------------------------------------------------------------------------

function CreateUserDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<string>('limited');
  const [tokenLimit, setTokenLimit] = useState(100);

  const mutation = useMutation({
    mutationFn: createUserApi,
    onSuccess: () => {
      toast.success(`User "${username}" created`);
      onCreated();
      onClose();
    },
    onError: (err: Error) => {
      toast.error(err.message);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const payload: Parameters<typeof createUserApi>[0] = {
      username: username.trim(),
      password,
      role,
    };
    if (role === 'limited') {
      payload.token_limit = tokenLimit;
    }
    mutation.mutate(payload);
  };

  const valid = username.trim().length >= 3 && password.length >= 8;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <form
        onSubmit={handleSubmit}
        className="bg-white rounded-lg shadow-xl w-full max-w-md p-6"
      >
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          Create User
        </h2>

        {/* Username */}
        <div className="mb-3">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Username
          </label>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
            placeholder="min 3 characters"
            minLength={3}
            required
          />
        </div>

        {/* Password */}
        <div className="mb-3">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Password
          </label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
            placeholder="min 8 characters"
            minLength={8}
            required
          />
        </div>

        {/* Role */}
        <div className="mb-3">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Role
          </label>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>

        {/* Token limit (only for limited role) */}
        {role === 'limited' && (
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Token Limit (per month)
            </label>
            <input
              type="number"
              min={0}
              value={tokenLimit}
              onChange={(e) => setTokenLimit(parseInt(e.target.value, 10) || 0)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
            />
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-end gap-2 mt-4">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200 transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!valid || mutation.isPending}
            className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {mutation.isPending ? 'Creating...' : 'Create'}
          </button>
        </div>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------------------
// User Row (view + edit modes)
// ---------------------------------------------------------------------------

function UserRow({
  user,
  currentUserId,
}: {
  user: UserListItem;
  currentUserId: number;
}) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [role, setRole] = useState(user.role);
  const [tokenLimit, setTokenLimit] = useState(user.token_limit);
  const [showPasswordReset, setShowPasswordReset] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [confirmDeactivate, setConfirmDeactivate] = useState(false);

  const isSelf = user.id === currentUserId;

  const updateMutation = useMutation({
    mutationFn: (data: Parameters<typeof updateUserApi>[1]) =>
      updateUserApi(user.id, data),
    onSuccess: () => {
      toast.success(`User "${user.username}" updated`);
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
      setEditing(false);
      setShowPasswordReset(false);
      setNewPassword('');
    },
    onError: (err: Error) => {
      toast.error(err.message);
    },
  });

  const handleSave = () => {
    const data: Parameters<typeof updateUserApi>[1] = {};
    if (role !== user.role) data.role = role;
    if (tokenLimit !== user.token_limit) data.token_limit = tokenLimit;
    if (Object.keys(data).length === 0) {
      setEditing(false);
      return;
    }
    updateMutation.mutate(data);
  };

  const handleCancel = () => {
    setRole(user.role);
    setTokenLimit(user.token_limit);
    setShowPasswordReset(false);
    setNewPassword('');
    setEditing(false);
    setConfirmDeactivate(false);
  };

  const handleToggleActive = () => {
    if (isSelf) {
      toast.error('You cannot deactivate your own account');
      return;
    }
    if (user.is_active && !confirmDeactivate) {
      setConfirmDeactivate(true);
      return;
    }
    updateMutation.mutate({ is_active: !user.is_active });
    setConfirmDeactivate(false);
  };

  const handleResetPassword = () => {
    if (newPassword.length < 8) {
      toast.error('Password must be at least 8 characters');
      return;
    }
    updateMutation.mutate({ new_password: newPassword });
  };

  // --- View mode ---
  if (!editing) {
    return (
      <tr className="border-b border-gray-100 hover:bg-gray-50 transition-colors">
        <td className="px-4 py-3 text-sm font-medium text-gray-900">
          {user.username}
        </td>
        <td className="px-4 py-3">
          <RoleBadge role={user.role} />
        </td>
        <td className="px-4 py-3">
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
              user.is_active
                ? 'bg-green-100 text-green-800'
                : 'bg-gray-100 text-gray-500'
            }`}
          >
            {user.is_active ? 'Active' : 'Inactive'}
          </span>
        </td>
        <td className="px-4 py-3 text-sm text-gray-600 tabular-nums">
          {user.role === 'limited' ? user.token_limit : '--'}
        </td>
        <td className="px-4 py-3 text-sm text-gray-600 tabular-nums">
          {user.tokens_used_this_month}
        </td>
        <td className="px-4 py-3 text-sm text-gray-500">
          {formatDate(user.last_login)}
        </td>
        <td className="px-4 py-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="text-xs font-medium text-indigo-600 hover:text-indigo-800 transition-colors"
            >
              Edit
            </button>
            <button
              type="button"
              onClick={handleToggleActive}
              disabled={isSelf || updateMutation.isPending}
              className={`text-xs font-medium transition-colors disabled:opacity-40 ${
                user.is_active
                  ? 'text-red-600 hover:text-red-800'
                  : 'text-green-600 hover:text-green-800'
              }`}
              title={isSelf ? 'Cannot deactivate yourself' : undefined}
            >
              {confirmDeactivate
                ? 'Confirm?'
                : user.is_active
                  ? 'Deactivate'
                  : 'Activate'}
            </button>
            {confirmDeactivate && (
              <button
                type="button"
                onClick={() => setConfirmDeactivate(false)}
                className="text-xs text-gray-500 hover:text-gray-700 transition-colors"
              >
                Cancel
              </button>
            )}
          </div>
        </td>
      </tr>
    );
  }

  // --- Edit mode ---
  return (
    <>
      <tr className="border-b border-indigo-100 bg-indigo-50/50">
        <td className="px-4 py-3 text-sm font-medium text-gray-900">
          {user.username}
        </td>
        <td className="px-4 py-3">
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="border border-gray-300 rounded-md px-2 py-1 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </td>
        <td className="px-4 py-3">
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
              user.is_active
                ? 'bg-green-100 text-green-800'
                : 'bg-gray-100 text-gray-500'
            }`}
          >
            {user.is_active ? 'Active' : 'Inactive'}
          </span>
        </td>
        <td className="px-4 py-3">
          {role === 'limited' ? (
            <input
              type="number"
              min={0}
              value={tokenLimit}
              onChange={(e) =>
                setTokenLimit(parseInt(e.target.value, 10) || 0)
              }
              className="w-24 border border-gray-300 rounded-md px-2 py-1 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
            />
          ) : (
            <span className="text-sm text-gray-400">--</span>
          )}
        </td>
        <td className="px-4 py-3 text-sm text-gray-600 tabular-nums">
          {user.tokens_used_this_month}
        </td>
        <td className="px-4 py-3 text-sm text-gray-500">
          {formatDate(user.last_login)}
        </td>
        <td className="px-4 py-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleSave}
              disabled={updateMutation.isPending}
              className="text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-700 px-3 py-1 rounded-md disabled:opacity-50 transition-colors"
            >
              {updateMutation.isPending ? 'Saving...' : 'Save'}
            </button>
            <button
              type="button"
              onClick={handleCancel}
              className="text-xs font-medium text-gray-600 hover:text-gray-800 transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => setShowPasswordReset(!showPasswordReset)}
              className="text-xs font-medium text-amber-600 hover:text-amber-800 transition-colors"
            >
              {showPasswordReset ? 'Hide' : 'Reset Pwd'}
            </button>
          </div>
        </td>
      </tr>
      {/* Password reset row */}
      {showPasswordReset && (
        <tr className="border-b border-indigo-100 bg-indigo-50/30">
          <td colSpan={7} className="px-4 py-3">
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-gray-700">
                New password for {user.username}:
              </label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="min 8 characters"
                className="border border-gray-300 rounded-md px-3 py-1.5 text-sm w-56 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              />
              <button
                type="button"
                onClick={handleResetPassword}
                disabled={
                  newPassword.length < 8 || updateMutation.isPending
                }
                className="text-xs font-medium text-white bg-amber-600 hover:bg-amber-700 px-3 py-1.5 rounded-md disabled:opacity-50 transition-colors"
              >
                {updateMutation.isPending ? 'Resetting...' : 'Reset'}
              </button>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export default function Users() {
  const [showCreate, setShowCreate] = useState(false);
  const queryClient = useQueryClient();
  const currentUser = useAuthStore((s) => s.user);

  const {
    data: users,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['admin-users'],
    queryFn: fetchUsers,
  });

  // Fetch chat status (kill switch)
  const chatStatus = useQuery({
    queryKey: ['chat-status'],
    queryFn: async () => {
      const res = await fetch('/auth/settings/chat-status', { credentials: 'include' });
      return res.json();
    },
  });

  const toggleChat = useMutation({
    mutationFn: async () => {
      const res = await fetch('/auth/settings/chat-toggle', { method: 'POST', credentials: 'include' });
      return res.json();
    },
    onSuccess: () => {
      chatStatus.refetch();
      toast.success('Chat status toggled');
    },
  });

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">
            User Management
          </h1>
          <p className="text-gray-500 mt-1">
            Create, edit, and manage user accounts and permissions.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowCreate(true)}
          className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 transition-colors shadow-sm"
        >
          Create User
        </button>
      </div>

      {/* Chat Kill Switch */}
      <div className="flex items-center justify-between p-4 bg-white rounded-lg border mb-6">
        <div>
          <h3 className="font-medium text-gray-900">Chat Service</h3>
          <p className="text-sm text-gray-500">
            {chatStatus.data?.chat_enabled ? 'Chat is enabled for all users' : 'Chat is disabled (emergency mode)'}
          </p>
        </div>
        <button
          onClick={() => toggleChat.mutate()}
          className={`px-4 py-2 rounded-lg text-sm font-medium ${
            chatStatus.data?.chat_enabled
              ? 'bg-red-50 text-red-700 hover:bg-red-100'
              : 'bg-green-50 text-green-700 hover:bg-green-100'
          }`}
        >
          {chatStatus.data?.chat_enabled ? 'Disable Chat' : 'Enable Chat'}
        </button>
      </div>

      {/* Create dialog */}
      {showCreate && (
        <CreateUserDialog
          onClose={() => setShowCreate(false)}
          onCreated={() =>
            queryClient.invalidateQueries({ queryKey: ['admin-users'] })
          }
        />
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="flex items-center justify-center h-64 text-gray-400">
          <svg
            className="animate-spin -ml-1 mr-3 h-5 w-5 text-indigo-500"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
          Loading users...
        </div>
      )}

      {/* Error state */}
      {error && !isLoading && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-red-700">
          <h2 className="font-semibold mb-1">Failed to Load Users</h2>
          <p className="text-sm">
            {error instanceof Error ? error.message : 'Unknown error'}
          </p>
        </div>
      )}

      {/* Users table */}
      {users && !isLoading && (
        <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50">
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Username
                </th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Role
                </th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Token Limit
                </th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Tokens Used
                </th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Last Login
                </th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <UserRow
                  key={u.id}
                  user={u}
                  currentUserId={currentUser?.user_id ?? -1}
                />
              ))}
              {users.length === 0 && (
                <tr>
                  <td
                    colSpan={7}
                    className="px-4 py-12 text-center text-gray-400"
                  >
                    No users found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
