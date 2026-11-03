export const VIEW_CONNECT = 'connect'
export const VIEW_SEND = 'send'
export const VIEW_SETTINGS = 'settings'

export interface PlannedPreset {
  name: string
  inherits: string
}

export interface SkippedModel {
  model: string
  reason: string
}

export interface ProfilePlan {
  presets: PlannedPreset[]
  skipped: SkippedModel[]
  filaments: string[]
  bundleName: string
}

export interface Session {
  instanceUrl: string
  username: string | null
  hasApiKey: boolean
}

export interface ConnectBoot {
  view: typeof VIEW_CONNECT
  session: Session | null
}

export interface Printer {
  id: number
  name: string
  model: string
  location: string | null
}

export interface FileFilament {
  slotId: number
  type: string
  color: string
  usedGrams: number
  trayInfoIdx: string | null
}

export interface Tray {
  globalId: number
  label: string
  type: string
  color: string
  subBrand: string | null
  trayInfoIdx: string | null
}

export interface PrintOptions {
  bedLevelling: boolean
  flowCali: boolean
  vibrationCali: boolean
  timelapse: boolean
}

export interface SendBoot {
  view: typeof VIEW_SEND
  instanceUrl: string
  printName: string
  nameSuffix: string
  model: string
  printers: Printer[]
  options: PrintOptions
  requireExactColors: boolean
  groupPlates: boolean
}

export interface Settings extends PrintOptions {
  requireExactColors: boolean
  groupPlates: boolean
}

export interface SettingsBoot {
  view: typeof VIEW_SETTINGS
}

export type Boot = ConnectBoot | SendBoot | SettingsBoot

export const TARGET_ANY = 'any'
export const TARGET_PRINTER = 'printer'
export type TargetKind = typeof TARGET_ANY | typeof TARGET_PRINTER

export const DISPATCH_NOW = 'now'
export const DISPATCH_QUEUE = 'queue'
export type Dispatch = typeof DISPATCH_NOW | typeof DISPATCH_QUEUE

export interface PlateInfo {
  plateId: number
  name: string
  filaments: FileFilament[]
  preview: string | null
}

export interface PlateRequest {
  plateId: number
  amsMapping: number[] | null
}

export interface SendRequest {
  targetKind: TargetKind
  printerId: number | null
  location: string | null
  dispatch: Dispatch
  plates: PlateRequest[]
  printName: string
  forceColorMatch: boolean
  groupPlates: boolean
  options: PrintOptions
}

export type OutgoingMessage =
  | { type: 'sign-in'; url: string }
  | { type: 'sign-in-with-api-key'; url: string; apiKey: string }
  | { type: 'cancel-sign-in' }
  | { type: 'plan-profiles' }
  | { type: 'save-profiles'; bundleName: string; presets: PlannedPreset[] }
  | { type: 'disconnect' }
  | { type: 'load-trays'; printerId: number }
  | { type: 'send'; request: SendRequest }

export type IncomingMessage =
  | { type: 'sign-in-started'; userCode: string; verificationUrl: string }
  | { type: 'signed-in'; session: Session }
  | { type: 'api-key-required' }
  | { type: 'sign-in-failed'; error: string }
  | { type: 'profiles-planned'; plan: ProfilePlan | null; error: string | null }
  | { type: 'profiles-saved'; error: string | null; restartRequired: boolean }
  | { type: 'disconnected'; error: string | null }
  | { type: 'file-ready'; plates: PlateInfo[] }
  | { type: 'upload-progress'; percent: number }
  | { type: 'upload-failed'; error: string }
  | { type: 'trays-loaded'; printerId: number; trays: Tray[]; error: string | null }
  | { type: 'send-result'; error: string | null }
