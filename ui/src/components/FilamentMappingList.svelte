<script lang="ts">
  import * as Select from '$lib/components/ui/select'
  import { UNMAPPED } from '$lib/filament-mapping'
  import type { SendManager } from '$lib/managers/send-manager.svelte'
  import type { PlateInfo, Tray } from '$lib/types'
  import ColorSwatch from './ColorSwatch.svelte'

  let { manager, plate, trays }: { manager: SendManager; plate: PlateInfo; trays: Tray[] | null } = $props()

  const mapping = $derived(manager.mappingFor(plate.plateId))

  function trayFor(slotId: number): Tray | undefined {
    return trays?.find((tray) => tray.globalId === mapping.get(slotId))
  }
</script>

<div class="flex flex-col gap-2">
  {#each plate.filaments as filament (filament.slotId)}
    {@const tray = trayFor(filament.slotId)}
    <div class="flex items-center justify-between gap-3 rounded-md border px-3 py-2">
      <div class="flex items-center gap-2">
        <ColorSwatch color={filament.color} />
        <span class="font-medium">{filament.type}</span>
        <span class="text-xs text-muted-foreground">Slot {filament.slotId} · {filament.usedGrams.toFixed(1)} g</span>
      </div>

      {#if trays}
        <Select.Root
          type="single"
          value={String(mapping.get(filament.slotId) ?? UNMAPPED)}
          onValueChange={(value) => manager.setSlot(plate.plateId, filament.slotId, Number(value))}
        >
          <Select.Trigger size="sm" class="w-44">
            {#if tray}
              <ColorSwatch color={tray.color} />
              {tray.label} · {tray.type}
            {:else}
              Not mapped
            {/if}
          </Select.Trigger>
          <Select.Content>
            {#each trays as option (option.globalId)}
              <Select.Item value={String(option.globalId)}>
                <ColorSwatch color={option.color} />
                {option.label} · {option.subBrand ?? option.type}
              </Select.Item>
            {/each}
          </Select.Content>
        </Select.Root>
      {/if}
    </div>
  {:else}
    <span class="text-xs text-muted-foreground">No filament used on this plate.</span>
  {/each}
</div>
