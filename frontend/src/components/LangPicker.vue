<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { LANGS, type Lang } from '@/i18n/types'

const props = withDefaults(
  defineProps<{ modelValue: Lang; label?: string; compact?: boolean; up?: boolean }>(),
  { label: 'Language', compact: false, up: false },
)
const emit = defineEmits<{ 'update:modelValue': [code: Lang] }>()

const open = ref(false)
const active = ref(0)
const uid = Math.random().toString(36).slice(2, 8)
const btn = ref<HTMLButtonElement | null>(null)
const menu = ref<HTMLUListElement | null>(null)

const current = computed(() => LANGS.find(l => l.code === props.modelValue) || LANGS[0]!)

function toggle() {
  if (open.value) close()
  else openMenu()
}
function openMenu() {
  active.value = Math.max(
    0,
    LANGS.findIndex(l => l.code === props.modelValue),
  )
  open.value = true
  void nextTick(() => menu.value?.focus())
}
function close() {
  open.value = false
}
function pick(code: Lang) {
  emit('update:modelValue', code)
  open.value = false
  void nextTick(() => btn.value?.focus())
}
function onKey(e: KeyboardEvent) {
  const n = LANGS.length
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    active.value = (active.value + 1) % n
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    active.value = (active.value - 1 + n) % n
  } else if (e.key === 'Home') {
    e.preventDefault()
    active.value = 0
  } else if (e.key === 'End') {
    e.preventDefault()
    active.value = n - 1
  } else if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    pick(LANGS[active.value]!.code)
  } else if (e.key === 'Escape' || e.key === 'Tab') {
    open.value = false
    if (e.key === 'Escape') btn.value?.focus()
  }
}
function onDocClick() {
  close()
}

onMounted(() => document.addEventListener('click', onDocClick))
onUnmounted(() => document.removeEventListener('click', onDocClick))
</script>

<template>
  <div class="lang-picker" :class="{ open, up }">
    <button
      ref="btn"
      type="button"
      class="lp-btn"
      aria-haspopup="listbox"
      :aria-expanded="open ? 'true' : 'false'"
      :aria-label="label + ': ' + current.name"
      :title="label"
      @click.stop="toggle"
      @keydown.down.prevent="openMenu"
    >
      <span class="flag" aria-hidden="true"
        ><svg viewBox="0 0 30 20"><use :href="'#flag-' + current.flag" /></svg
      ></span>
      <span class="lp-name">{{ compact ? current.code.toUpperCase() : current.name }}</span>
      <svg class="i lp-chev" aria-hidden="true"><use href="#i-chevron" /></svg>
    </button>
    <ul
      v-if="open"
      ref="menu"
      class="lp-menu"
      role="listbox"
      tabindex="-1"
      :aria-label="label"
      :aria-activedescendant="'lp-' + uid + '-' + active"
      @keydown="onKey"
      @click.stop
    >
      <li
        v-for="(l, i) in LANGS"
        :id="'lp-' + uid + '-' + i"
        :key="l.code"
        role="option"
        :aria-selected="l.code === modelValue ? 'true' : 'false'"
        :class="{ active: i === active }"
        @mousemove="active = i"
        @click="pick(l.code)"
      >
        <span class="flag" aria-hidden="true"
          ><svg viewBox="0 0 30 20"><use :href="'#flag-' + l.flag" /></svg
        ></span>
        <span>{{ compact ? l.code.toUpperCase() : l.name }}</span>
        <svg v-if="l.code === modelValue" class="i lp-check" aria-hidden="true">
          <use href="#i-check" />
        </svg>
      </li>
    </ul>
  </div>
</template>
