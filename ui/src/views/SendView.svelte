<script lang="ts">
  import { untrack } from 'svelte'
  import { onMessage } from '$lib/bridge'
  import * as Accordion from '$lib/components/ui/accordion'
  import { Alert, AlertDescription } from '$lib/components/ui/alert'
  import { Badge } from '$lib/components/ui/badge'
  import { Button } from '$lib/components/ui/button'
  import { Input } from '$lib/components/ui/input'
  import { Label } from '$lib/components/ui/label'
  import { Progress } from '$lib/components/ui/progress'
  import * as RadioGroup from '$lib/components/ui/radio-group'
  import * as Select from '$lib/components/ui/select'
  import { Separator } from '$lib/components/ui/separator'
  import { Skeleton } from '$lib/components/ui/skeleton'
  import { Switch } from '$lib/components/ui/switch'
  import * as ToggleGroup from '$lib/components/ui/toggle-group'
  import { ALL_LOCATIONS, SendManager } from '$lib/managers/send-manager.svelte'
  import {
    EXACT_COLORS_HELP,
    EXACT_COLORS_LABEL,
    GROUP_PLATES_HELP,
    GROUP_PLATES_LABEL,
    PRINT_OPTION_LABELS,
  } from '$lib/print-options'
  import {
    DISPATCH_NOW,
    DISPATCH_QUEUE,
    TARGET_ANY,
    TARGET_PRINTER,
    type Dispatch,
    type PrintOptions,
    type SendBoot,
    type TargetKind,
  } from '$lib/types'
  import PlateList from '../components/PlateList.svelte'

  let { boot }: { boot: SendBoot } = $props()

  const manager = new SendManager(untrack(() => boot))
  onMessage((message) => manager.handle(message))

  const selectedPrinter = $derived(boot.printers.find((p) => p.id === manager.printerId))
</script>

<div class="mx-auto flex max-w-xl flex-col gap-4">
  <header class="flex flex-col gap-1">
    <h1 class="text-base font-semibold">Send to Bambuddy</h1>
    <div class="flex items-center gap-2 text-muted-foreground">
      <Badge variant="secondary">{boot.model}</Badge>
      <span class="truncate">{boot.instanceUrl}</span>
    </div>
  </header>

  <section class="flex flex-col gap-2">
    <Label for="print-name">Name</Label>
    <div class="flex items-center gap-2">
      <Input id="print-name" class="flex-1" bind:value={manager.printName} disabled={manager.submitting} />
      {#if boot.nameSuffix}
        <span class="shrink-0 text-muted-foreground">{boot.nameSuffix}</span>
      {/if}
    </div>
  </section>

  {#if manager.uploadError}
    <Alert variant="destructive"><AlertDescription>Upload failed: {manager.uploadError}</AlertDescription></Alert>
  {/if}
  {#if manager.error}
    <Alert variant="destructive"><AlertDescription>{manager.error}</AlertDescription></Alert>
  {/if}

  <section class="flex flex-col gap-2">
    <Label>Printer</Label>
    <ToggleGroup.Root
      type="single"
      variant="outline"
      value={manager.targetKind}
      onValueChange={(value) => value && manager.selectTarget(value as TargetKind)}
    >
      <ToggleGroup.Item value={TARGET_ANY}>Any {boot.model}</ToggleGroup.Item>
      <ToggleGroup.Item value={TARGET_PRINTER} disabled={boot.printers.length === 0}>Specific printer</ToggleGroup.Item>
    </ToggleGroup.Root>

    <div class="flex gap-2">
      {#if manager.locations.length > 0}
        <Select.Root type="single" value={manager.location} onValueChange={(value) => manager.selectLocation(value)}>
          <Select.Trigger class="w-44">{manager.location || 'All groups'}</Select.Trigger>
          <Select.Content>
            <Select.Item value={ALL_LOCATIONS}>All groups</Select.Item>
            {#each manager.locations as location (location)}
              <Select.Item value={location}>{location}</Select.Item>
            {/each}
          </Select.Content>
        </Select.Root>
      {/if}

      {#if manager.targetKind === TARGET_PRINTER}
        <Select.Root
          type="single"
          value={manager.printerId === null ? undefined : String(manager.printerId)}
          onValueChange={(value) => manager.selectPrinter(Number(value))}
        >
          <Select.Trigger class="flex-1">{selectedPrinter?.name ?? 'Choose a printer'}</Select.Trigger>
          <Select.Content>
            {#each manager.visiblePrinters as printer (printer.id)}
              <Select.Item value={String(printer.id)}>{printer.name}</Select.Item>
            {/each}
          </Select.Content>
        </Select.Root>
      {/if}
    </div>
  </section>

  <Separator />

  <section class="flex flex-col gap-2">
    <Label>{manager.multiplePlates ? 'Plates' : 'Filament'}</Label>
    {#if manager.plates === null}
      {#if !manager.uploadError}
        <Progress value={manager.uploadPercent} />
        <span class="text-xs text-muted-foreground">
          {manager.uploadPercent < 100
            ? `Uploading to Bambuddy… ${manager.uploadPercent}%`
            : 'Reading the filaments in this plate…'}
        </span>
      {/if}
    {:else if manager.targetKind === TARGET_PRINTER}
      {#if manager.printerId !== null && manager.trayErrors[manager.printerId]}
        <Alert variant="destructive">
          <AlertDescription>Could not read AMS: {manager.trayErrors[manager.printerId]}</AlertDescription>
        </Alert>
      {:else if manager.selectedTrays === null}
        <Skeleton class="h-10 w-full" />
      {:else}
        <PlateList {manager} plates={manager.plates} trays={manager.selectedTrays} />
      {/if}
    {:else}
      <PlateList {manager} plates={manager.plates} trays={null} />
    {/if}
  </section>

  <Separator />

  <section class="flex flex-col gap-2">
    <Label>When</Label>
    <RadioGroup.Root
      value={manager.dispatch}
      onValueChange={(value) => (manager.dispatch = value as Dispatch)}
      class="grid grid-cols-2 gap-2"
    >
      <Label class="flex items-start gap-2 rounded-md border p-3 font-normal">
        <RadioGroup.Item value={DISPATCH_NOW} />
        <span class="flex flex-col gap-1">
          <span class="font-medium">Send now</span>
          <span class="text-xs text-muted-foreground">Starts as soon as the printer is free.</span>
        </span>
      </Label>
      <Label class="flex items-start gap-2 rounded-md border p-3 font-normal">
        <RadioGroup.Item value={DISPATCH_QUEUE} />
        <span class="flex flex-col gap-1">
          <span class="font-medium">Add to queue</span>
          <span class="text-xs text-muted-foreground">Waits until started in Bambuddy.</span>
        </span>
      </Label>
    </RadioGroup.Root>
  </section>

  <Accordion.Root type="single">
    <Accordion.Item value="advanced">
      <Accordion.Trigger>Advanced</Accordion.Trigger>
      <Accordion.Content class="flex flex-col gap-3">
        <span class="text-xs text-muted-foreground">
          These apply to this print only. Change the defaults in the Bambuddy plugin settings.
        </span>
        {#if manager.targetKind === TARGET_ANY}
          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <Label for="force-color">{EXACT_COLORS_LABEL}</Label>
              <span class="text-xs text-muted-foreground">{EXACT_COLORS_HELP}</span>
            </div>
            <Switch id="force-color" bind:checked={manager.forceColorMatch} />
          </div>
        {/if}
        {#if manager.multiplePlates}
          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <Label for="group-plates">{GROUP_PLATES_LABEL}</Label>
              <span class="text-xs text-muted-foreground">{GROUP_PLATES_HELP}</span>
            </div>
            <Switch id="group-plates" bind:checked={manager.groupPlates} />
          </div>
        {/if}
        <div class="grid grid-cols-2 gap-x-6 gap-y-3">
          {#each Object.entries(PRINT_OPTION_LABELS) as [key, label] (key)}
            <div class="flex items-center justify-between gap-2">
              <Label for={key}>{label}</Label>
              <Switch id={key} bind:checked={manager.options[key as keyof PrintOptions]} />
            </div>
          {/each}
        </div>
      </Accordion.Content>
    </Accordion.Item>
  </Accordion.Root>

  <footer class="flex justify-end gap-2">
    <Button variant="outline" onclick={() => manager.cancel()} disabled={manager.submitting}>Cancel</Button>
    <Button onclick={() => manager.submit()} disabled={!manager.canSubmit}>
      {manager.submitLabel}
    </Button>
  </footer>
</div>
