<script lang="ts">
  import { Button } from '$lib/components/ui/button'
  import { Label } from '$lib/components/ui/label'
  import { Separator } from '$lib/components/ui/separator'
  import { Switch } from '$lib/components/ui/switch'
  import { SettingsManager } from '$lib/managers/settings-manager.svelte'
  import {
    EXACT_COLORS_HELP,
    EXACT_COLORS_LABEL,
    GROUP_PLATES_HELP,
    GROUP_PLATES_LABEL,
    PRINT_OPTION_LABELS,
  } from '$lib/print-options'
  import type { PrintOptions } from '$lib/types'

  const manager = new SettingsManager()
</script>

<div class="flex flex-col gap-4">
  <p class="text-muted-foreground">
    Defaults for every send. The send window can change them for one print under Advanced.
  </p>

  <section class="flex items-center justify-between gap-4">
    <div class="flex flex-col gap-1">
      <Label for="require-exact-colors">{EXACT_COLORS_LABEL}</Label>
      <span class="text-xs text-muted-foreground">{EXACT_COLORS_HELP}</span>
    </div>
    <Switch
      id="require-exact-colors"
      checked={manager.settings.requireExactColors}
      onCheckedChange={(value) => manager.set('requireExactColors', value)}
      disabled={manager.readOnly}
    />
  </section>

  <section class="flex items-center justify-between gap-4">
    <div class="flex flex-col gap-1">
      <Label for="group-plates">{GROUP_PLATES_LABEL}</Label>
      <span class="text-xs text-muted-foreground">{GROUP_PLATES_HELP}</span>
    </div>
    <Switch
      id="group-plates"
      checked={manager.settings.groupPlates}
      onCheckedChange={(value) => manager.set('groupPlates', value)}
      disabled={manager.readOnly}
    />
  </section>

  <Separator />

  <section class="flex flex-col gap-3">
    <span class="font-medium">Print options</span>
    {#each Object.entries(PRINT_OPTION_LABELS) as [key, label] (key)}
      <div class="flex items-center justify-between gap-2">
        <Label for={key}>{label}</Label>
        <Switch
          id={key}
          checked={manager.settings[key as keyof PrintOptions]}
          onCheckedChange={(value) => manager.set(key as keyof PrintOptions, value)}
          disabled={manager.readOnly}
        />
      </div>
    {/each}
  </section>

  <div class="flex justify-end">
    <Button variant="outline" size="sm" onclick={() => manager.restore()} disabled={manager.readOnly}>
      {manager.restoreLabel}
    </Button>
  </div>
</div>
