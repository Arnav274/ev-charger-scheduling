import { useCallback, useEffect, useState } from "react";

import { loginUser, registerUser } from "../api";

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

  const login = useCallback(async (email, password) => {
    setToken((await loginUser(email, password)).access_token);
  }, []);

  const register = useCallback(async (email, password) => {
    setToken((await registerUser(email, password)).access_token);
  }, []);

  const logout = useCallback(() => setToken(""), []);

  return { token, login, register, logout };
}
