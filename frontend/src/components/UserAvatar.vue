<script setup lang="ts">
import { computed } from 'vue'
import type { User } from '@/api/types'

const props = withDefaults(defineProps<{ user: User | null; size?: number }>(), { size: 32 })

const AVATAR_COLORS = [
  '#B42318',
  '#B54708',
  '#027A48',
  '#0E7090',
  '#175CD3',
  '#5925DC',
  '#C11574',
  '#4E5BA6',
  '#475467',
  '#93370D',
]

function avatarColor(name: string) {
  let h = 0x811c9dc5
  for (const ch of name || '') {
    h ^= ch.codePointAt(0)!
    h = Math.imul(h, 0x01000193)
  }
  return AVATAR_COLORS[(h >>> 0) % AVATAR_COLORS.length]!
}

function avatarInitials(name: string) {
  return (
    (name || '')
      .split(/[.\s_-]+/)
      .filter(Boolean)
      .map(p => p[0])
      .join('')
      .slice(0, 2)
      .toUpperCase() || '?'
  )
}

const initials = computed(() => avatarInitials(props.user?.username || ''))
const color = computed(() => avatarColor(props.user?.username || ''))
const style = computed(() => ({
  width: props.size + 'px',
  height: props.size + 'px',
  fontSize: Math.round(props.size * 0.38) + 'px',
  background: color.value,
}))
</script>

<template>
  <span class="uavatar initials" :style="style" :title="user?.username">{{ initials }}</span>
</template>
