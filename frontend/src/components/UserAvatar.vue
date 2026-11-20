<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { User } from '@/api/types'
import { avatarColor, avatarInitials, loadAvatar } from '@/lib/avatar'
import { useAuthStore } from '@/stores/auth'

const props = withDefaults(defineProps<{ user: User | null; size?: number }>(), { size: 32 })

const src = ref<string | null>(null)
const auth = useAuthStore()

const initials = computed(() => avatarInitials(props.user?.username || ''))
const color = computed(() => avatarColor(props.user?.username || ''))
const style = computed(() => ({
  width: props.size + 'px',
  height: props.size + 'px',
  fontSize: Math.round(props.size * 0.38) + 'px',
  background: src.value ? undefined : color.value,
}))

watch(
  () => props.user?.avatar_url,
  async url => {
    const token = auth.token
    if (!url || !token) {
      src.value = null
      return
    }
    try {
      const data = await loadAvatar(url, token)
      if (props.user?.avatar_url === url) src.value = data
    } catch {
      if (props.user?.avatar_url === url) src.value = null
    }
  },
  { immediate: true },
)
</script>

<template>
  <span class="uavatar" :class="{ initials: !src }" :style="style" :title="user?.username">
    <img v-if="src" :src="src" alt="" />
    <template v-else>{{ initials }}</template>
  </span>
</template>
