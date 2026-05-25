"use client";

import { useState } from "react";

const STORAGE_KEY = "email-agent-user-id";

export function useUserId() {
  const [userId, setUserId] = useState(() => {
    if (typeof window === "undefined") {
      return "";
    }
    return window.localStorage.getItem(STORAGE_KEY) ?? "";
  });

  function updateUserId(next: string) {
    setUserId(next);
    if (next.trim()) {
      window.localStorage.setItem(STORAGE_KEY, next.trim());
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  }

  return { userId, setUserId: updateUserId };
}
