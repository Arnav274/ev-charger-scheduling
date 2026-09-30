import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import useAuth from "./useAuth";

describe("useAuth", () => {
  let reportUnauthorized;

  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    vi.spyOn(api, "onUnauthorized").mockImplementation((handler) => {
      reportUnauthorized = handler;
    });
  });

  it("ends the session when its own token is rejected", () => {
    localStorage.setItem("ev_access_token", "current");
    const { result } = renderHook(() => useAuth());
    act(() => reportUnauthorized("current"));
    expect(result.current.token).toBe("");
  });

  it("ignores a rejection of a token it has already replaced", async () => {
    localStorage.setItem("ev_access_token", "old");
    vi.spyOn(api, "loginUser").mockResolvedValue({ access_token: "new" });
    const { result } = renderHook(() => useAuth());

    await act(() => result.current.login("a@b.com", "pw"));
    act(() => reportUnauthorized("old"));

    expect(result.current.token).toBe("new");
    expect(localStorage.getItem("ev_access_token")).toBe("new");
  });
});
