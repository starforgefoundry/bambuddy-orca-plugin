import type { Boot, IncomingMessage, OutgoingMessage } from './types'

interface OrcaBridge {
  postMessage(data: unknown): void
  submit(data: unknown): void
  close(): void
  onMessage(cb: (data: unknown) => void): void
}

export interface ConfigContext {
  scope: 'global' | 'preset'
  readOnly: boolean
  hasPresetOverride: boolean
}

// The bridge OrcaSlicer gives a capability's settings page instead of the window bridge.
interface OrcaConfigBridge {
  getConfig(): unknown
  saveConfig(config: unknown): void
  restoreDefaults(): void
  getContext(): ConfigContext
  onConfig(cb: (config: unknown) => void): void
}

declare global {
  interface Window {
    orca?: OrcaBridge & Partial<OrcaConfigBridge>
  }
}

const BOOT_ELEMENT_ID = 'bambuddy-boot'
const ORCA_DEFAULTS_STYLE_ID = 'orca-plugin-defaults'

export function readBoot(): Boot {
  const el = document.getElementById(BOOT_ELEMENT_ID)
  if (!el?.textContent) throw new Error('missing boot data')
  return JSON.parse(el.textContent) as Boot
}

export function send(message: OutgoingMessage): void {
  window.orca?.postMessage(message)
}

export function onMessage(handler: (message: IncomingMessage) => void): void {
  window.orca?.onMessage((data) => handler(data as IncomingMessage))
}

export function closeWindow(): void {
  window.orca?.close()
}

export function onConfig(handler: (config: unknown) => void): void {
  window.orca?.onConfig?.(handler)
}

export function saveConfig(config: unknown): void {
  window.orca?.saveConfig?.(config)
}

export function restoreDefaultConfig(): void {
  window.orca?.restoreDefaults?.()
}

export function configContext(): ConfigContext | null {
  return window.orca?.getContext?.() ?? null
}

// Orca injects unlayered element styles that beat Tailwind's layered utilities.
export function removeOrcaDefaultStyles(): void {
  const remove = () => document.getElementById(ORCA_DEFAULTS_STYLE_ID)?.remove()
  remove()
  new MutationObserver(remove).observe(document.documentElement, { childList: true, subtree: true })
}
