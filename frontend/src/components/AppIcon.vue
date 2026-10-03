<script setup>
const props = defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 18 }
})

const PATHS = {
  home: 'M3 10.5 12 3l9 7.5M5.25 9.75V21h13.5V9.75',
  list: 'M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01',
  history: 'M12 7v5l3.5 2M3.5 12a8.5 8.5 0 1 0 2.6-6.1M3.5 4v4h4',
  user: 'M12 12.5a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM4.5 20.5a7.5 7.5 0 0 1 15 0',
  cog: 'M12 15.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4ZM19.4 12c0-.5 0-1-.1-1.5l1.7-1.3-1.7-3-2 .8c-.8-.6-1.6-1-2.5-1.3L14.4 4H9.6l-.4 2.7c-.9.3-1.7.7-2.5 1.3l-2-.8-1.7 3L4.7 11c0 .5-.1 1-.1 1.5s0 1 .1 1.5l-1.7 1.3 1.7 3 2-.8c.8.6 1.6 1 2.5 1.3l.4 2.7h4.8l.4-2.7c.9-.3 1.7-.7 2.5-1.3l2 .8 1.7-3-1.7-1.3c.1-.5.1-1 .1-1.5Z',
  plus: 'M12 5v14M5 12h14',
  play: 'M7 4.5v15l13-7.5-13-7.5Z',
  refresh: 'M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6',
  logout: 'M15 4h3.5A1.5 1.5 0 0 1 20 5.5v13A1.5 1.5 0 0 1 18.5 20H15M11 16l4-4-4-4M15 12H4',
  trash: 'M4 7h16M9.5 7V5.5A1.5 1.5 0 0 1 11 4h2a1.5 1.5 0 0 1 1.5 1.5V7M6.5 7l.8 12.1A1.5 1.5 0 0 0 8.8 20.5h6.4a1.5 1.5 0 0 0 1.5-1.4L17.5 7',
  edit: 'M4 20h4l10-10-4-4L4 16v4ZM14.5 5.5 18.5 9.5',
  send: 'M21 3 10.5 13.5M21 3l-6.5 18-4-8-8-4L21 3Z',
  bell: 'M18 15V10a6 6 0 1 0-12 0v5l-1.5 3h15L18 15ZM10 21h4',
  check: 'M5 13l4.5 4.5L19 7',
  close: 'M6 6l12 12M18 6 6 18',
  bolt: 'M13 3 5 14h6l-1 7 8-11h-6l1-7Z',
  key: 'M14.5 3a6.5 6.5 0 1 0-5.9 9.2L3 18v3h3v-3h3v-3h2.8A6.5 6.5 0 0 0 14.5 3Z'
}
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.8"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path :d="PATHS[props.name] || PATHS.home" />
  </svg>
</template>
