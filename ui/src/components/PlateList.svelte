<script lang="ts">
  import { Checkbox } from '$lib/components/ui/checkbox'
  import { Label } from '$lib/components/ui/label'
  import type { SendManager } from '$lib/managers/send-manager.svelte'
  import type { PlateInfo, Tray } from '$lib/types'
  import FilamentMappingList from './FilamentMappingList.svelte'

  let { manager, plates, trays }: { manager: SendManager; plates: PlateInfo[]; trays: Tray[] | null } = $props()
</script>

<div class="flex flex-col gap-3">
  {#each plates as plate (plate.plateId)}
    {@const selected = manager.isPlateSelected(plate.plateId)}
    <div class="flex gap-3 rounded-md border p-3">
      <div class="flex min-w-0 flex-1 flex-col gap-2">
        <div class="flex items-center gap-2">
          {#if manager.multiplePlates}
            <Checkbox
              id={`plate-${plate.plateId}`}
              checked={selected}
              onCheckedChange={(value) => manager.togglePlate(plate.plateId, value === true)}
            />
          {/if}
          <Label for={`plate-${plate.plateId}`} class="font-medium">{plate.name}</Label>
          {#if plate.name !== `Plate ${plate.plateId}`}
            <span class="text-xs text-muted-foreground">Plate {plate.plateId}</span>
          {/if}
        </div>
        {#if selected}
          <FilamentMappingList {manager} {plate} {trays} />
        {/if}
      </div>
      {#if plate.preview}
        <img
          src={plate.preview}
          alt={`Preview of ${plate.name}`}
          class="size-24 shrink-0 self-start rounded-md border bg-muted object-contain"
          class:opacity-40={!selected}
        />
      {/if}
    </div>
  {/each}
</div>
