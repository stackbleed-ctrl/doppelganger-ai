/**
 * LAN Discovery Service
 * Finds Doppelganger instances on the local network via:
 * 1. mDNS/Bonjour (_doppelganger._tcp)
 * 2. IP range scan fallback
 * 3. Manual IP entry
 * 
 * NEVER connects to internet — LAN only by design.
 */

import NetInfo from '@react-native-community/netinfo'

export interface DoppelgangerHost {
  name: string
  ip: string
  port: number
  version: string
  reachable: boolean
  latency_ms: number
  last_seen: number
}

const DEFAULT_PORT = 8000
const SCAN_TIMEOUT_MS = 500
const HEALTH_PATH = '/health'
const MDNS_SERVICE = '_doppelganger._tcp'

class LANDiscovery {
  private _hosts: Map<string, DoppelgangerHost> = new Map()
  private _scanning = false
  private _listeners: Set<(hosts: DoppelgangerHost[]) => void> = new Set()

  // ── Public API ─────────────────────────────────────────────────────────────

  onHostsChanged(cb: (hosts: DoppelgangerHost[]) => void): () => void {
    this._listeners.add(cb)
    return () => this._listeners.delete(cb)
  }

  get hosts(): DoppelgangerHost[] {
    return Array.from(this._hosts.values()).sort((a, b) => b.last_seen - a.last_seen)
  }

  async discover(): Promise<DoppelgangerHost[]> {
    if (this._scanning) return this.hosts
    this._scanning = true

    try {
      // Try mDNS first
      const mdnsHosts = await this._mDNSDiscover()
      
      // Fall back to subnet scan
      const subnetHosts = await this._subnetScan()
      
      const allHosts = [...mdnsHosts, ...subnetHosts]
      
      // Deduplicate by IP
      const seen = new Set<string>()
      for (const host of allHosts) {
        if (!seen.has(host.ip)) {
          seen.add(host.ip)
          this._hosts.set(host.ip, host)
        }
      }
      
      this._notify()
      return this.hosts
    } finally {
      this._scanning = false
    }
  }

  async addManual(ip: string, port: number = DEFAULT_PORT): Promise<DoppelgangerHost | null> {
    const host = await this._probe(ip, port)
    if (host) {
      this._hosts.set(ip, host)
      this._notify()
    }
    return host
  }

  async ping(ip: string): Promise<number> {
    const host = this._hosts.get(ip)
    if (!host) return -1
    const updated = await this._probe(ip, host.port)
    if (updated) {
      this._hosts.set(ip, updated)
      this._notify()
      return updated.latency_ms
    }
    return -1
  }

  // ── mDNS discovery ─────────────────────────────────────────────────────────

  private async _mDNSDiscover(): Promise<DoppelgangerHost[]> {
    try {
      // React Native Bonjour library
      const Bonjour = require('react-native-bonjour')
      return new Promise((resolve) => {
        const hosts: DoppelgangerHost[] = []
        const browser = Bonjour.find({ type: 'doppelganger', protocol: 'tcp' })
        
        browser.on('up', async (service: any) => {
          const ip = service.addresses?.[0]
          const port = service.port || DEFAULT_PORT
          if (ip) {
            const host = await this._probe(ip, port)
            if (host) hosts.push(host)
          }
        })
        
        // Stop after 3 seconds
        setTimeout(() => {
          browser.stop()
          resolve(hosts)
        }, 3000)
      })
    } catch {
      return []
    }
  }

  // ── Subnet scan ────────────────────────────────────────────────────────────

  private async _subnetScan(): Promise<DoppelgangerHost[]> {
    const subnet = await this._getLocalSubnet()
    if (!subnet) return []

    const [base] = subnet.split('.')
    const prefix = subnet.split('.').slice(0, 3).join('.')
    
    // Scan .1–.254 in parallel batches
    const hosts: DoppelgangerHost[] = []
    const BATCH = 20
    
    for (let start = 1; start <= 254; start += BATCH) {
      const batch = Array.from(
        { length: Math.min(BATCH, 255 - start) },
        (_, i) => `${prefix}.${start + i}`
      )
      
      const results = await Promise.allSettled(
        batch.map(ip => this._probe(ip, DEFAULT_PORT))
      )
      
      for (const result of results) {
        if (result.status === 'fulfilled' && result.value) {
          hosts.push(result.value)
        }
      }
    }
    
    return hosts
  }

  // ── Probe a single host ────────────────────────────────────────────────────

  private async _probe(ip: string, port: number): Promise<DoppelgangerHost | null> {
    const url = `http://${ip}:${port}${HEALTH_PATH}`
    const start = Date.now()
    
    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), SCAN_TIMEOUT_MS)
      
      const resp = await fetch(url, {
        signal: controller.signal,
        headers: { 'Accept': 'application/json' },
      })
      
      clearTimeout(timeout)
      
      if (!resp.ok) return null
      
      const data = await resp.json()
      const latency = Date.now() - start
      
      return {
        name: `Doppelganger @ ${ip}`,
        ip,
        port,
        version: data.version || 'unknown',
        reachable: true,
        latency_ms: latency,
        last_seen: Date.now(),
      }
    } catch {
      return null
    }
  }

  // ── Helpers ────────────────────────────────────────────────────────────────

  private async _getLocalSubnet(): Promise<string | null> {
    try {
      const info = await NetInfo.fetch()
      const ip = (info as any)?.details?.ipAddress
      if (ip) return ip
    } catch {}
    return null
  }

  private _notify(): void {
    const hosts = this.hosts
    this._listeners.forEach(cb => cb(hosts))
  }
}

export const lanDiscovery = new LANDiscovery()
export default lanDiscovery
