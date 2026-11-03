import { closeWindow, send } from '$lib/bridge'
import type { ConnectBoot, IncomingMessage, PlannedPreset, Session, SkippedModel } from '$lib/types'

export const CONNECT_IDLE = 'idle'
export const CONNECT_SIGNING_IN = 'signing-in'
export const CONNECT_PLANNING = 'planning'
export const CONNECT_SAVING = 'saving'
type ConnectPhase = typeof CONNECT_IDLE | typeof CONNECT_SIGNING_IN | typeof CONNECT_PLANNING | typeof CONNECT_SAVING

export const SAVE_RESTART_REQUIRED = 'restart-required'
export const SAVE_LOADED = 'loaded'
type SaveOutcome = typeof SAVE_RESTART_REQUIRED | typeof SAVE_LOADED

export class ConnectManager {
  url = $state('')
  phase = $state<ConnectPhase>(CONNECT_IDLE)
  error = $state<string | null>(null)
  session = $state<Session | null>(null)
  presets = $state<PlannedPreset[] | null>(null)
  skipped = $state<SkippedModel[]>([])
  filaments = $state<string[]>([])
  bundleName = $state('')
  planProblem = $state<string | null>(null)
  saved = $state<SaveOutcome | null>(null)
  pending = $state<{ userCode: string; verificationUrl: string } | null>(null)
  apiKey = $state('')
  apiKeyUrl = $state<string | null>(null)

  constructor(boot: ConnectBoot) {
    this.session = boot.session
    this.url = boot.session?.instanceUrl ?? ''
    if (this.session) this.planProfiles()
  }

  get busy(): boolean {
    return this.phase !== CONNECT_IDLE
  }

  get canSave(): boolean {
    return !this.busy && !this.planProblem && !!this.presets?.length && !!this.bundleName.trim()
  }

  // Asked for only after this instance turned out not to support browser sign-in.
  get needsApiKey(): boolean {
    return this.apiKeyUrl !== null && this.apiKeyUrl === this.url.trim()
  }

  get canSignIn(): boolean {
    return !this.busy && !!this.url.trim() && (!this.needsApiKey || !!this.apiKey.trim())
  }

  get waitingForBrowser(): boolean {
    return this.phase === CONNECT_SIGNING_IN && !this.needsApiKey
  }

  get sessionLabel(): string {
    if (this.session?.username) return `Signed in as ${this.session.username}`
    return this.session?.hasApiKey ? 'Signed in with an API key' : 'Authentication disabled'
  }

  signIn(): void {
    if (!this.canSignIn) return
    this.error = null
    this.phase = CONNECT_SIGNING_IN
    const url = this.url.trim()
    if (this.needsApiKey) {
      send({ type: 'sign-in-with-api-key', url, apiKey: this.apiKey.trim() })
      return
    }
    send({ type: 'sign-in', url })
  }

  cancelSignIn(): void {
    this.phase = CONNECT_IDLE
    this.pending = null
    send({ type: 'cancel-sign-in' })
  }

  planProfiles(): void {
    this.error = null
    this.saved = null
    this.phase = CONNECT_PLANNING
    send({ type: 'plan-profiles' })
  }

  rename(inherits: string, name: string): void {
    this.presets = (this.presets ?? []).map((p) => (p.inherits === inherits ? { ...p, name } : p))
    this.saved = null
  }

  renameBundle(name: string): void {
    this.bundleName = name
    this.saved = null
  }

  saveProfiles(): void {
    if (!this.presets) return
    this.error = null
    this.phase = CONNECT_SAVING
    send({ type: 'save-profiles', bundleName: this.bundleName.trim(), presets: $state.snapshot(this.presets) })
  }

  disconnect(): void {
    send({ type: 'disconnect' })
  }

  close(): void {
    closeWindow()
  }

  handle(message: IncomingMessage): void {
    switch (message.type) {
      case 'sign-in-started':
        this.pending = { userCode: message.userCode, verificationUrl: message.verificationUrl }
        return
      case 'api-key-required':
        this.phase = CONNECT_IDLE
        this.apiKeyUrl = this.url.trim()
        return
      case 'signed-in':
        this.pending = null
        this.apiKey = ''
        this.apiKeyUrl = null
        this.session = message.session
        this.planProfiles()
        return
      case 'sign-in-failed':
        this.phase = CONNECT_IDLE
        this.pending = null
        this.error = message.error
        return
      case 'profiles-planned':
        this.phase = CONNECT_IDLE
        this.planProblem = message.error
        this.presets = message.plan?.presets ?? null
        this.skipped = message.plan?.skipped ?? []
        this.filaments = message.plan?.filaments ?? []
        this.bundleName = message.plan?.bundleName ?? this.bundleName
        return
      case 'profiles-saved':
        this.phase = CONNECT_IDLE
        this.error = message.error
        if (!message.error) this.saved = message.restartRequired ? SAVE_RESTART_REQUIRED : SAVE_LOADED
        return
      case 'disconnected':
        this.phase = CONNECT_IDLE
        this.error = message.error
        this.session = null
        this.presets = null
        this.skipped = []
        this.filaments = []
        this.planProblem = null
        this.saved = null
        return
    }
  }
}
