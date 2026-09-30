import { useCallback, useEffect, useState } from "react";

import { loginUser, onUnauthorized, registerUser } from "../api";

const TOKEN_KEY = "ev_access_token";

function readToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export default function useAuth() {
  const [token, setToken] = useState(readToken);

  useEffect(() => {
    try {
      if (token) localStorage.setItem(TOKEN_KEY, token);
      else localStorage.removeItem(TOKEN_KEY);
    } catch {
      // Storage can be unavailable (private mode); the session still works in memory.
    }
  }, [token]);

  // An expired or revoked token ends the session. A 401 for an older token, from a
  // request that was already in flight when the user signed in again, is ignored.
  useEffect(() => {
    onUnauthorized((rejected) => setToken((current) => (current === rejected ? "" : current)));
    return () => onUnauthorized(() => {});
  }, []);

  const login = useCallback(async (email, password) => {
    setToken((await loginUser(email, password)).access_token);
  }, []);

  const register = useCallback(async (email, password) => {
    setToken((await registerUser(email, password)).access_token);
  }, []);

  const logout = useCallback(() => setToken(""), []);

  return { token, login, register, logout };
}
