<script lang="ts">
  import { untrack } from 'svelte'
  import { onMessage } from '$lib/bridge'
  import { Alert, AlertDescription } from '$lib/components/ui/alert'
  import { Badge } from '$lib/components/ui/badge'
  import { Button } from '$lib/components/ui/button'
  import { Input } from '$lib/components/ui/input'
  import { Label } from '$lib/components/ui/label'
  import { Skeleton } from '$lib/components/ui/skeleton'
  import {
    CONNECT_PLANNING,
    CONNECT_SAVING,
    CONNECT_SIGNING_IN,
    ConnectManager,
    SAVE_LOADED,
    SAVE_RESTART_REQUIRED,
  } from '$lib/managers/connect-manager.svelte'
  import type { ConnectBoot } from '$lib/types'

  let { boot }: { boot: ConnectBoot } = $props()

  const manager = new ConnectManager(untrack(() => boot))
  onMessage((message) => manager.handle(message))
</script>

<div class="mx-auto flex max-w-lg flex-col gap-4">
  <header class="flex flex-col gap-1">
    <h1 class="text-base font-semibold">Bambuddy</h1>
    <p class="text-muted-foreground">
      Sign in with your Bambuddy instance to import printer profiles and send prints through it.
    </p>
  </header>

  <div class="flex flex-col gap-4">
    {#if manager.error}
      <Alert variant="destructive"><AlertDescription>{manager.error}</AlertDescription></Alert>
    {/if}

    {#if manager.session}
      <div class="flex items-center justify-between gap-2 rounded-md border p-3">
        <div class="flex min-w-0 flex-col">
          <span class="truncate font-medium">{manager.session.instanceUrl}</span>
          <span class="text-muted-foreground">
            {manager.session.username ? `Signed in as ${manager.session.username}` : 'Authentication disabled'}
          </span>
        </div>
        <div class="flex items-center gap-2">
          <Badge variant="secondary">Connected</Badge>
          <Button variant="outline" size="sm" onclick={() => manager.disconnect()} disabled={manager.busy}>
            Sign out
          </Button>
        </div>
      </div>
      <span class="text-xs text-muted-foreground">
        Signing out also removes the Bambuddy printer and filament profiles from OrcaSlicer.
      </span>

      {#if manager.presets}
        <div class="flex flex-col gap-1">
          <Label for="bundle-name">Bundle name</Label>
          <Input
            id="bundle-name"
            value={manager.bundleName}
            oninput={(event) => manager.renameBundle(event.currentTarget.value)}
            disabled={manager.busy}
          />
          <span class="text-xs text-muted-foreground">How OrcaSlicer labels this group of profiles.</span>
        </div>
      {/if}

      <div class="flex flex-col gap-2">
        <span class="font-medium">Printer profiles</span>
        {#if manager.phase === CONNECT_PLANNING}
          <Skeleton class="h-14 w-full" />
        {:else if manager.presets}
          {#each manager.presets as preset (preset.inherits)}
            <div class="flex flex-col gap-1">
              <Label for={preset.inherits} class="text-xs text-muted-foreground">Based on {preset.inherits}</Label>
              <Input
                id={preset.inherits}
                value={preset.name}
                oninput={(event) => manager.rename(preset.inherits, event.currentTarget.value)}
                disabled={manager.busy}
              />
            </div>
          {:else}
            <span class="text-muted-foreground">No supported printers found on this instance.</span>
          {/each}
          {#each manager.skipped as skipped (skipped.model)}
            <span class="text-xs text-muted-foreground">Skipped {skipped.model}: {skipped.reason}</span>
          {/each}

          <span class="mt-2 font-medium">Filament presets</span>
          <span class="text-xs text-muted-foreground">Built-in presets for the spools in your Bambuddy inventory.</span>
          {#if manager.planProblem}
            <Alert variant="destructive"><AlertDescription>{manager.planProblem}</AlertDescription></Alert>
          {:else}
            <div class="flex flex-wrap gap-1">
              {#each manager.filaments as filament (filament)}
                <Badge variant="outline">{filament}</Badge>
              {:else}
                <span class="text-muted-foreground">No spools in inventory.</span>
              {/each}
            </div>
          {/if}
        {/if}
        {#if manager.saved === SAVE_RESTART_REQUIRED}
          <Alert><AlertDescription>Saved. Restart OrcaSlicer to load the printer profiles.</AlertDescription></Alert>
        {:else if manager.saved === SAVE_LOADED}
          <Alert><AlertDescription>Saved. The printer profiles are ready to use.</AlertDescription></Alert>
        {/if}
      </div>
    {:else if manager.phase === CONNECT_SIGNING_IN}
      <div class="flex flex-col gap-2 rounded-md border p-3">
        <span class="font-medium">Finish signing in in your browser</span>
        {#if manager.pending}
          <span class="text-muted-foreground">Enter this code in Bambuddy, then click Allow:</span>
          <span class="font-mono text-2xl tracking-widest">{manager.pending.userCode}</span>
          <span class="text-xs break-all text-muted-foreground">
            Browser didn't open? Go to {manager.pending.verificationUrl}
          </span>
        {:else}
          <Skeleton class="h-8 w-40" />
        {/if}
      </div>
    {:else}
      <form
        class="flex flex-col gap-2"
        onsubmit={(event) => {
          event.preventDefault()
          manager.signIn()
        }}
      >
        <Label for="instance-url">Instance URL</Label>
        <Input
          id="instance-url"
          type="url"
          placeholder="https://bambuddy.example.com"
          required
          bind:value={manager.url}
        />
      </form>
    {/if}
  </div>

  <footer class="flex justify-end gap-2">
    {#if manager.session}
      <Button variant="outline" onclick={() => manager.planProfiles()} disabled={manager.busy}>Refresh</Button>
      <Button onclick={() => manager.saveProfiles()} disabled={!manager.canSave}>
        {manager.phase === CONNECT_SAVING ? 'Saving…' : 'Save profiles'}
      </Button>
    {:else if manager.phase === CONNECT_SIGNING_IN}
      <Button variant="outline" onclick={() => manager.cancelSignIn()}>Cancel</Button>
    {:else}
      <Button onclick={() => manager.signIn()} disabled={!manager.url.trim()}>Sign in</Button>
    {/if}
  </footer>
</div>
