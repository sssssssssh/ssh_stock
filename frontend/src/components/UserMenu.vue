<script setup lang="ts">
import { ref } from "vue";

defineProps<{ username: string }>();
const emit = defineEmits<{ changePassword: []; logout: [] }>();
const open = ref(false);
</script>

<template>
  <div class="user-menu">
    <button type="button" class="user-menu-trigger" @click="open = !open">{{ username }}</button>
    <div v-if="open" class="user-menu-popover">
      <button type="button" @click="emit('changePassword'); open = false">修改密码</button>
      <button type="button" @click="emit('logout'); open = false">退出登录</button>
    </div>
  </div>
</template>
