import type { FileFilament, Tray } from './types'

export const UNMAPPED = -1

export type FilamentMapping = Map<number, number>

function hexToRgb(hex: string): [number, number, number] {
  const value = hex.replace('#', '').slice(0, 6).padEnd(6, '0')
  return [0, 2, 4].map((i) => parseInt(value.slice(i, i + 2), 16)) as [number, number, number]
}

function colorDistance(a: string, b: string): number {
  const [r1, g1, b1] = hexToRgb(a)
  const [r2, g2, b2] = hexToRgb(b)
  return Math.hypot(r1 - r2, g1 - g2, b1 - b2)
}

function sameType(filament: FileFilament, tray: Tray): boolean {
  return filament.type.toUpperCase() === tray.type.toUpperCase()
}

function pickTray(filament: FileFilament, free: Tray[]): Tray | undefined {
  const typed = free.filter((tray) => sameType(filament, tray))
  const exactPreset = typed.find(
    (tray) => filament.trayInfoIdx !== null && tray.trayInfoIdx === filament.trayInfoIdx,
  )
  if (exactPreset && colorDistance(exactPreset.color, filament.color) === 0) return exactPreset
  return typed.sort((a, b) => colorDistance(a.color, filament.color) - colorDistance(b.color, filament.color))[0]
}

export function autoMap(filaments: FileFilament[], trays: Tray[]): FilamentMapping {
  const free = [...trays]
  const mapping: FilamentMapping = new Map()
  for (const filament of filaments) {
    const tray = pickTray(filament, free)
    mapping.set(filament.slotId, tray?.globalId ?? UNMAPPED)
    if (tray) free.splice(free.indexOf(tray), 1)
  }
  return mapping
}

export function toAmsMapping(filaments: FileFilament[], mapping: FilamentMapping): number[] {
  const length = Math.max(0, ...filaments.map((f) => f.slotId))
  return Array.from({ length }, (_, i) => mapping.get(i + 1) ?? UNMAPPED)
}
