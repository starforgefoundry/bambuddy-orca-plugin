import type { PrintOptions } from './types'

export const PRINT_OPTION_LABELS: Record<keyof PrintOptions, string> = {
  bedLevelling: 'Bed leveling',
  flowCali: 'Flow calibration',
  vibrationCali: 'Vibration calibration',
  timelapse: 'Timelapse',
}

export const EXACT_COLORS_LABEL = 'Require exact filament colors'
export const EXACT_COLORS_HELP =
  'Bambuddy always picks a printer with the filament types loaded and prefers matching colors. Turn this on to wait for a printer with the exact colors.'

export const GROUP_PLATES_LABEL = 'Group plates as a batch'
export const GROUP_PLATES_HELP = 'When sending more than one plate, keep them together as one batch in the Bambuddy queue.'
