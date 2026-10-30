import { configContext, onConfig, restoreDefaultConfig, saveConfig, type ConfigContext } from '$lib/bridge'
import type { Settings } from '$lib/types'

export const DEFAULT_SETTINGS: Settings = {
  requireExactColors: false,
  groupPlates: false,
  bedLevelling: true,
  flowCali: false,
  vibrationCali: false,
  timelapse: false,
}

function withDefaults(config: unknown): Settings {
  const stored = (config && typeof config === 'object' ? config : {}) as Partial<Record<keyof Settings, unknown>>
  const settings = { ...DEFAULT_SETTINGS }
  for (const key of Object.keys(DEFAULT_SETTINGS) as (keyof Settings)[]) {
    if (typeof stored[key] === 'boolean') settings[key] = stored[key]
  }
  return settings
}

export class SettingsManager {
  settings = $state<Settings>({ ...DEFAULT_SETTINGS })
  context = $state<ConfigContext | null>(null)

  constructor() {
    this.context = configContext()
    onConfig((config) => {
      this.settings = withDefaults(config)
      this.context = configContext()
    })
  }

  get readOnly(): boolean {
    return this.context?.readOnly ?? false
  }

  get restoreLabel(): string {
    return this.context?.scope === 'preset' ? 'Use plugin defaults' : 'Restore defaults'
  }

  set(key: keyof Settings, value: boolean): void {
    this.settings = { ...this.settings, [key]: value }
    saveConfig($state.snapshot(this.settings))
  }

  restore(): void {
    restoreDefaultConfig()
  }
}
