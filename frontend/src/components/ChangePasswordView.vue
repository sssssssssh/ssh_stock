<script setup lang="ts">
import { ref } from "vue";
import { changePassword } from "../services/auth";

defineProps<{ username: string; required?: boolean }>();
const emit = defineEmits<{ changed: []; cancel: [] }>();
const currentPassword = ref("");
const newPassword = ref("");
const confirmPassword = ref("");
const submitting = ref(false);
const error = ref("");

async function submit() {
  error.value = "";
  if (newPassword.value.length < 8) {
    error.value = "新密码至少需要 8 个字符";
    return;
  }
  if (newPassword.value !== confirmPassword.value) {
    error.value = "两次输入的新密码不一致";
    return;
  }
  submitting.value = true;
  try {
    await changePassword(currentPassword.value, newPassword.value);
    emit("changed");
  } catch (reason) {
    error.value = reason instanceof Error && reason.message === "INVALID_CURRENT_PASSWORD"
      ? "当前密码错误"
      : "密码修改失败";
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <main class="auth-shell">
    <form class="auth-panel" @submit.prevent="submit">
      <div class="auth-brand"><span>空</span><div><h1>修改密码</h1><p>{{ username }}</p></div></div>
      <p v-if="required" class="auth-notice">首次登录必须修改初始密码。</p>
      <label>当前密码<input v-model="currentPassword" type="password" autocomplete="current-password" required /></label>
      <label>新密码<input v-model="newPassword" type="password" autocomplete="new-password" required /></label>
      <label>确认新密码<input v-model="confirmPassword" type="password" autocomplete="new-password" required /></label>
      <p v-if="error" class="auth-error">{{ error }}</p>
      <div class="auth-actions">
        <button v-if="!required" type="button" class="secondary-button" @click="emit('cancel')">取消</button>
        <button type="submit" :disabled="submitting">{{ submitting ? "提交中" : "修改密码" }}</button>
      </div>
    </form>
  </main>
</template>
