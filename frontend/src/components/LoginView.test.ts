import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";

import * as auth from "../services/auth";
import LoginView from "./LoginView.vue";

beforeEach(() => vi.restoreAllMocks());

it("emits authenticated user and clears the password", async () => {
  const user = { id: "u1", username: "admin", must_change_password: false };
  vi.spyOn(auth, "login").mockResolvedValue(user);
  const wrapper = mount(LoginView);
  await wrapper.get('input[type="password"]').setValue("secret-password");
  await wrapper.get("form").trigger("submit");
  await flushPromises();

  expect(auth.login).toHaveBeenCalledWith("admin", "secret-password");
  expect(wrapper.emitted("authenticated")?.[0]).toEqual([user]);
  expect((wrapper.get('input[type="password"]').element as HTMLInputElement).value).toBe("");
});

it("shows the unified credential error without leaking details", async () => {
  vi.spyOn(auth, "login").mockRejectedValue(new Error("INVALID_CREDENTIALS"));
  const wrapper = mount(LoginView);
  await wrapper.get('input[type="password"]').setValue("wrong");
  await wrapper.get("form").trigger("submit");
  await flushPromises();

  expect(wrapper.get(".auth-error").text()).toBe("用户名或密码错误");
});
