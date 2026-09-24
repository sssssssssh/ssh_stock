<script setup lang="ts">
import { ref } from "vue";
import { login } from "../services/auth";
import type { AuthUser } from "../types";

const emit = defineEmits<{ authenticated: [user: AuthUser] }>();
const username = ref("admin");
const password = ref("");
const submitting = ref(false);
const error = ref("");

async function submit() {
  submitting.value = true;
  error.value = "";
  try {
    emit("authenticated", await login(username.value, password.value));
    password.value = "";
  } catch (reason) {
    error.value = reason instanceof Error && reason.message === "INVALID_CREDENTIALS"
      ? "用户名或密码错误"
      : "登录失败，请稍后重试";
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <main class="auth-shell">
    <form class="auth-panel" @submit.prevent="submit">
      <div class="auth-brand"><span>空</span><div><h1>空间</h1><p>A 股机会研究工作台</p></div></div>
      <label>用户名<input v-model.trim="username" autocomplete="username" required /></label>
      <label>密码<input v-model="password" type="password" autocomplete="current-password" required /></label>
      <p v-if="error" class="auth-error">{{ error }}</p>
      <button type="submit" :disabled="submitting">{{ submitting ? "登录中" : "登录" }}</button>
    </form>
  </main>
</template>
