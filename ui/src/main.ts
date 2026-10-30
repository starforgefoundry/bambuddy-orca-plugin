import { mount } from 'svelte'
import './app.css'
import App from './App.svelte'
import { readBoot, removeOrcaDefaultStyles } from '$lib/bridge'

removeOrcaDefaultStyles()

export default mount(App, {
  target: document.getElementById('app')!,
  props: { boot: readBoot() },
})
