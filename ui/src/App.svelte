<script lang="ts">
  import { VIEW_CONNECT, VIEW_SEND, type Boot } from '$lib/types'
  import ConnectView from './views/ConnectView.svelte'
  import SendView from './views/SendView.svelte'
  import SettingsView from './views/SettingsView.svelte'

  let { boot }: { boot: Boot } = $props()
</script>

<main class="min-h-screen bg-background p-4 text-[13px] text-foreground">
  {#if boot.view === VIEW_CONNECT}
    <ConnectView {boot} />
  {:else if boot.view === VIEW_SEND}
    <SendView {boot} />
  {:else}
    <SettingsView />
  {/if}
</main>
