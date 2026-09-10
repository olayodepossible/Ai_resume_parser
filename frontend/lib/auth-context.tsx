"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { ApiError, api, readStoredToken, storeToken } from "./api";
import { applyTheme } from "./theme";
import type { User, UserSettings } from "./types";

interface AuthState {
  user: User | null;
  token: string | null;
  /** True until the stored token has been checked against `/auth/me`. */
  loading: boolean;
  signup: (input: {
    email: string;
    password: string;
    fullName: string;
  }) => Promise<void>;
  login: (input: { email: string; password: string }) => Promise<void>;
  logout: () => void;
  updateProfile: (input: {
    fullName?: string;
    settings?: UserSettings;
  }) => Promise<User>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Resolve the token left in localStorage by a previous visit. A 401 here is
  // the expected path for an expired token, not an error worth surfacing.
  useEffect(() => {
    const stored = readStoredToken();

    if (!stored) {
      setLoading(false);
      return;
    }

    let active = true;

    api
      .me(stored)
      .then((fetched) => {
        if (!active) return;

        setUser(fetched);
        setToken(stored);
        applyTheme(fetched.settings.theme);
      })
      .catch((error: unknown) => {
        if (!active) return;

        if (error instanceof ApiError && error.isUnauthenticated) {
          storeToken(null);
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  const adopt = useCallback((accessToken: string, nextUser: User) => {
    storeToken(accessToken);
    setToken(accessToken);
    setUser(nextUser);
    applyTheme(nextUser.settings.theme);
  }, []);

  const signup = useCallback<AuthState["signup"]>(
    async (input) => {
      const result = await api.signup(input);
      adopt(result.accessToken, result.user);
    },
    [adopt],
  );

  const login = useCallback<AuthState["login"]>(
    async (input) => {
      const result = await api.login(input);
      adopt(result.accessToken, result.user);
    },
    [adopt],
  );

  const logout = useCallback(() => {
    // Tokens carry their own expiry and there is no server-side session to
    // end, so signing out is a local discard. See app/auth.py.
    storeToken(null);
    setToken(null);
    setUser(null);
  }, []);

  const updateProfile = useCallback<AuthState["updateProfile"]>(
    async (input) => {
      if (!token) throw new Error("Not signed in.");

      const updated = await api.updateMe(token, input);
      setUser(updated);
      applyTheme(updated.settings.theme);

      return updated;
    },
    [token],
  );

  const value = useMemo<AuthState>(
    () => ({ user, token, loading, signup, login, logout, updateProfile }),
    [user, token, loading, signup, login, logout, updateProfile],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("useAuth must be used inside <AuthProvider>.");
  }

  return context;
}
