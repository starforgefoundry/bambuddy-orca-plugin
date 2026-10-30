import { describe, expect, it } from 'vitest'
import { autoMap, toAmsMapping, UNMAPPED } from './filament-mapping'
import type { FileFilament, Tray } from './types'

const filament = (slotId: number, type: string, color: string, trayInfoIdx: string | null = null): FileFilament => ({
  slotId,
  type,
  color,
  usedGrams: 1,
  trayInfoIdx,
})

const tray = (globalId: number, type: string, color: string, trayInfoIdx: string | null = null): Tray => ({
  globalId,
  label: `T${globalId}`,
  type,
  color,
  subBrand: null,
  trayInfoIdx,
})

describe('autoMap', () => {
  it('prefers the closest color of the same type', () => {
    const mapping = autoMap(
      [filament(1, 'PLA', '#FF0000')],
      [tray(0, 'PLA', '#0000FF'), tray(1, 'PLA', '#EE1111'), tray(2, 'PETG', '#FF0000')],
    )
    expect(mapping.get(1)).toBe(1)
  })

  it('prefers an exact preset and color match', () => {
    const mapping = autoMap(
      [filament(1, 'PLA', '#000000', 'GFA01')],
      [tray(0, 'PLA', '#000000', 'GFL99'), tray(1, 'PLA', '#000000', 'GFA01')],
    )
    expect(mapping.get(1)).toBe(1)
  })

  it('uses each tray once', () => {
    const mapping = autoMap([filament(1, 'PLA', '#FFFFFF'), filament(2, 'PLA', '#FFFFFF')], [tray(4, 'PLA', '#FFFFFF')])
    expect(mapping.get(1)).toBe(4)
    expect(mapping.get(2)).toBe(UNMAPPED)
  })

  it('matches type case-insensitively', () => {
    expect(autoMap([filament(1, 'petg', '#FFFFFF')], [tray(2, 'PETG', '#000000')]).get(1)).toBe(2)
  })
})

describe('toAmsMapping', () => {
  it('indexes by slot and fills gaps as unmapped', () => {
    const filaments = [filament(1, 'PLA', '#FFF'), filament(3, 'PLA', '#FFF')]
    expect(toAmsMapping(filaments, new Map([[1, 5], [3, 254]]))).toEqual([5, UNMAPPED, 254])
  })
})
