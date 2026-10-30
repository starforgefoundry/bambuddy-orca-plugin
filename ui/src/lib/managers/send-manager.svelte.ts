import { closeWindow, send } from '$lib/bridge'
import { autoMap, toAmsMapping, type FilamentMapping } from '$lib/filament-mapping'
import {
  DISPATCH_NOW,
  TARGET_ANY,
  TARGET_PRINTER,
  type Dispatch,
  type IncomingMessage,
  type PlateInfo,
  type PrintOptions,
  type Printer,
  type SendBoot,
  type TargetKind,
  type Tray,
} from '$lib/types'

export const ALL_LOCATIONS = ''

export class SendManager {
  readonly boot: SendBoot
  targetKind = $state<TargetKind>(TARGET_ANY)
  printerId = $state<number | null>(null)
  location = $state(ALL_LOCATIONS)
  dispatch = $state<Dispatch>(DISPATCH_NOW)
  options = $state<PrintOptions>({ bedLevelling: true, flowCali: false, vibrationCali: false, timelapse: false })
  forceColorMatch = $state(false)
  groupPlates = $state(false)
  plates = $state<PlateInfo[] | null>(null)
  selectedPlateIds = $state<number[]>([])
  uploadError = $state<string | null>(null)
  uploadPercent = $state(0)
  trays = $state<Record<number, Tray[]>>({})
  trayErrors = $state<Record<number, string>>({})
  mappings = $state<Record<number, FilamentMapping>>({})
  submitting = $state(false)
  error = $state<string | null>(null)

  constructor(boot: SendBoot) {
    this.boot = boot
    this.options = { ...boot.options }
    this.forceColorMatch = boot.requireExactColors
    this.groupPlates = boot.groupPlates
  }

  get locations(): string[] {
    const named = this.boot.printers.map((p) => p.location).filter((l): l is string => !!l)
    return [...new Set(named)].sort()
  }

  get visiblePrinters(): Printer[] {
    if (this.location === ALL_LOCATIONS) return this.boot.printers
    return this.boot.printers.filter((p) => p.location === this.location)
  }

  get selectedTrays(): Tray[] | null {
    return this.printerId === null ? null : (this.trays[this.printerId] ?? null)
  }

  get multiplePlates(): boolean {
    return (this.plates?.length ?? 0) > 1
  }

  get canSubmit(): boolean {
    if (this.submitting || this.plates === null || this.selectedPlateIds.length === 0) return false
    return this.targetKind === TARGET_ANY || this.selectedTrays !== null
  }

  get submitLabel(): string {
    if (this.submitting) return 'Sending…'
    const count = this.multiplePlates ? ` ${this.selectedPlateIds.length} plates` : ''
    return this.dispatch === DISPATCH_NOW ? `Send${count}` : `Add${count} to queue`
  }

  isPlateSelected(plateId: number): boolean {
    return this.selectedPlateIds.includes(plateId)
  }

  togglePlate(plateId: number, selected: boolean): void {
    const others = this.selectedPlateIds.filter((id) => id !== plateId)
    this.selectedPlateIds = selected ? [...others, plateId].sort((a, b) => a - b) : others
  }

  selectTarget(kind: TargetKind): void {
    this.targetKind = kind
    if (kind === TARGET_PRINTER && this.printerId === null && this.visiblePrinters.length > 0) {
      this.selectPrinter(this.visiblePrinters[0].id)
    }
  }

  selectLocation(location: string): void {
    this.location = location
    if (this.printerId !== null && !this.visiblePrinters.some((p) => p.id === this.printerId)) {
      this.printerId = null
    }
  }

  selectPrinter(printerId: number): void {
    this.printerId = printerId
    if (this.trays[printerId]) {
      this.#remap()
      return
    }
    send({ type: 'load-trays', printerId })
  }

  mappingFor(plateId: number): FilamentMapping {
    return this.mappings[plateId] ?? new Map()
  }

  setSlot(plateId: number, slotId: number, globalId: number): void {
    this.mappings = { ...this.mappings, [plateId]: new Map(this.mappingFor(plateId)).set(slotId, globalId) }
  }

  submit(): void {
    if (!this.canSubmit || this.plates === null) return
    this.submitting = true
    this.error = null
    const toPrinter = this.targetKind === TARGET_PRINTER
    const selected = this.plates.filter((plate) => this.isPlateSelected(plate.plateId))
    send({
      type: 'send',
      request: {
        targetKind: this.targetKind,
        printerId: toPrinter ? this.printerId : null,
        location: !toPrinter && this.location !== ALL_LOCATIONS ? this.location : null,
        dispatch: this.dispatch,
        plates: selected.map((plate) => ({
          plateId: plate.plateId,
          amsMapping: toPrinter ? toAmsMapping(plate.filaments, this.mappingFor(plate.plateId)) : null,
        })),
        forceColorMatch: !toPrinter && this.forceColorMatch,
        groupPlates: selected.length > 1 && this.groupPlates,
        options: { ...this.options },
      },
    })
  }

  cancel(): void {
    closeWindow()
  }

  handle(message: IncomingMessage): void {
    switch (message.type) {
      case 'file-ready':
        this.plates = message.plates
        this.selectedPlateIds = message.plates.map((plate) => plate.plateId)
        this.#remap()
        return
      case 'upload-progress':
        this.uploadPercent = message.percent
        return
      case 'upload-failed':
        this.uploadError = message.error
        return
      case 'trays-loaded':
        if (message.error) {
          this.trayErrors = { ...this.trayErrors, [message.printerId]: message.error }
          return
        }
        this.trays = { ...this.trays, [message.printerId]: message.trays }
        if (message.printerId === this.printerId) this.#remap()
        return
      case 'send-result':
        this.submitting = false
        if (message.error) {
          this.error = message.error
          return
        }
        closeWindow()
        return
    }
  }

  // Each plate prints on its own, so each is matched against the printer's trays independently.
  #remap(): void {
    const trays = this.selectedTrays
    if (this.plates === null || trays === null) return
    this.mappings = Object.fromEntries(this.plates.map((plate) => [plate.plateId, autoMap(plate.filaments, trays)]))
  }
}
