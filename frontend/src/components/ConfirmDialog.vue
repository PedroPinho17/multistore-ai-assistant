<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const { dialog, t } = storeToRefs(ui)
const dlgOk = ref<HTMLButtonElement | null>(null)
const dlgCancel = ref<HTMLButtonElement | null>(null)

watch(dialog, d => {
  if (d) void nextTick(() => dlgCancel.value?.focus())
})

function dialogKey(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.preventDefault()
    ui.closeDialog(false)
  } else if (e.key === 'Tab') {
    e.preventDefault()
    ;(document.activeElement === dlgCancel.value ? dlgOk : dlgCancel).value?.focus()
  }
}
</script>

<template>
  <Transition name="dlg">
    <div
      v-if="dialog"
      class="dlg-backdrop"
      @mousedown.self="ui.closeDialog(false)"
    >
      <div
        class="dlg"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="dlg-title"
        aria-describedby="dlg-text"
        @keydown="dialogKey"
      >
        <div class="dlg-icon" :class="{ danger: dialog.danger }" aria-hidden="true">
          <svg
            v-if="dialog.danger"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M3 6h18" />
            <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
            <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
            <path d="M10 11v6M14 11v6" />
          </svg>
          <svg
            v-else
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <circle cx="12" cy="12" r="10" />
            <path d="M12 16v-4M12 8h.01" />
          </svg>
        </div>
        <h2 id="dlg-title">{{ dialog.title }}</h2>
        <p id="dlg-text">
          <strong v-if="dialog.subject">«{{ dialog.subject }}»</strong>
          <br v-if="dialog.subject" />
          {{ dialog.text }}
        </p>
        <div class="dlg-actions">
          <button ref="dlgCancel" type="button" class="dlg-cancel" @click="ui.closeDialog(false)">
            {{ t.dlg.cancel }}
          </button>
          <button
            ref="dlgOk"
            type="button"
            :class="dialog.danger ? 'dlg-danger' : 'dlg-ok'"
            @click="ui.closeDialog(true)"
          >
            {{ dialog.confirm }}
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>
