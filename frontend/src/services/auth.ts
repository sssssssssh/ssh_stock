import { request } from "./api";
import type { AuthUser } from "../types";

export function fetchCurrentUser(): Promise<AuthUser> {
  return request<AuthUser>("/auth/me");
}

export function login(username: string, password: string): Promise<AuthUser> {
  return request<AuthUser>("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password })
  });
}

export function changePassword(currentPassword: string, newPassword: string): Promise<unknown> {
  return request("/auth/change-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword })
  });
}

export function logout(): Promise<unknown> {
  return request("/auth/logout", { method: "POST" });
}
