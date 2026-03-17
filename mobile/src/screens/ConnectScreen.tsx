/**
 * Connect Screen
 * Discovers and pairs with a Doppelganger instance on the LAN.
 * Never connects to the internet.
 */

import React, { useState, useEffect } from 'react'
import {
  View, Text, TextInput, TouchableOpacity, FlatList,
  ActivityIndicator, StyleSheet, Alert,
} from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { Ionicons } from '@expo/vector-icons'
import { useRouter } from 'expo-router'
import { lanDiscovery, DoppelgangerHost } from '../services/lanDiscovery'
import { useApiConfig } from '../services/api'
import { colors, fonts, spacing } from '../theme'

export default function ConnectScreen() {
  const [hosts, setHosts] = useState<DoppelgangerHost[]>([])
  const [scanning, setScanning] = useState(false)
  const [manualIp, setManualIp] = useState('')
  const [connecting, setConnecting] = useState<string | null>(null)
  const { setConfig } = useApiConfig()
  const router = useRouter()

  useEffect(() => {
    const unsub = lanDiscovery.onHostsChanged(setHosts)
    scan()
    return unsub
  }, [])

  const scan = async () => {
    setScanning(true)
    try {
      await lanDiscovery.discover()
    } finally {
      setScanning(false)
    }
  }

  const connect = async (host: DoppelgangerHost) => {
    setConnecting(host.ip)
    try {
      setConfig(host.ip, host.port)
      router.replace('/(tabs)')
    } catch (e: any) {
      Alert.alert('Connection failed', e.message)
    } finally {
      setConnecting(null)
    }
  }

  const connectManual = async () => {
    if (!manualIp.trim()) return
    setConnecting(manualIp)
    try {
      const host = await lanDiscovery.addManual(manualIp.trim())
      if (host) {
        await connect(host)
      } else {
        Alert.alert('Not found', `No Doppelganger found at ${manualIp}:${8000}`)
      }
    } finally {
      setConnecting(null)
    }
  }

  const renderHost = ({ item }: { item: DoppelgangerHost }) => (
    <TouchableOpacity
      style={styles.hostCard}
      onPress={() => connect(item)}
      disabled={!!connecting}
    >
      <View style={styles.hostIcon}>
        <Ionicons name="desktop-outline" size={24} color={colors.cyan} />
      </View>
      <View style={styles.hostInfo}>
        <Text style={styles.hostName}>{item.name}</Text>
        <Text style={styles.hostMeta}>
          {item.ip}:{item.port} · v{item.version} · {item.latency_ms}ms
        </Text>
      </View>
      {connecting === item.ip
        ? <ActivityIndicator size="small" color={colors.cyan} />
        : <Ionicons name="chevron-forward" size={20} color={colors.muted} />
      }
    </TouchableOpacity>
  )

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.dna}>🧬</Text>
        <Text style={styles.title}>Connect to Doppelganger</Text>
        <Text style={styles.subtitle}>LAN only — your data never leaves your network</Text>
      </View>

      {/* Scan button */}
      <TouchableOpacity
        style={[styles.scanBtn, scanning && styles.scanBtnActive]}
        onPress={scan}
        disabled={scanning}
      >
        {scanning
          ? <><ActivityIndicator size="small" color={colors.cyan} style={{ marginRight: 8 }} />
             <Text style={styles.scanBtnText}>Scanning local network…</Text></>
          : <><Ionicons name="wifi" size={18} color={colors.cyan} style={{ marginRight: 8 }} />
             <Text style={styles.scanBtnText}>Scan for Doppelganger</Text></>
        }
      </TouchableOpacity>

      {/* Host list */}
      <FlatList
        data={hosts}
        keyExtractor={h => h.ip}
        renderItem={renderHost}
        style={styles.hostList}
        ListEmptyComponent={
          !scanning ? (
            <View style={styles.emptyState}>
              <Ionicons name="search-outline" size={40} color={colors.muted} />
              <Text style={styles.emptyText}>No instances found</Text>
              <Text style={styles.emptyHint}>
                Make sure Doppelganger is running on your{'\n'}computer and both devices are on the same WiFi
              </Text>
            </View>
          ) : null
        }
      />

      {/* Manual entry */}
      <View style={styles.manualSection}>
        <Text style={styles.manualLabel}>Enter IP manually</Text>
        <View style={styles.manualRow}>
          <TextInput
            style={styles.manualInput}
            value={manualIp}
            onChangeText={setManualIp}
            placeholder="192.168.1.xxx"
            placeholderTextColor={colors.muted}
            keyboardType="numbers-and-punctuation"
            autoCapitalize="none"
            autoCorrect={false}
          />
          <TouchableOpacity
            style={[styles.connectBtn, !manualIp.trim() && styles.connectBtnDisabled]}
            onPress={connectManual}
            disabled={!manualIp.trim() || !!connecting}
          >
            {connecting === manualIp
              ? <ActivityIndicator size="small" color={colors.cyan} />
              : <Text style={styles.connectBtnText}>Connect</Text>
            }
          </TouchableOpacity>
        </View>
      </View>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.void },
  header: { alignItems: 'center', padding: spacing.xl, paddingBottom: spacing.lg },
  dna: { fontSize: 48, marginBottom: 12 },
  title: { fontFamily: fonts.display, fontSize: 22, color: colors.bright, fontWeight: '700', marginBottom: 6 },
  subtitle: { fontFamily: fonts.body, fontSize: 13, color: colors.subtle, textAlign: 'center' },
  scanBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    marginHorizontal: spacing.md, marginBottom: spacing.md,
    padding: spacing.md, borderRadius: 12,
    borderWidth: 1, borderColor: colors.cyan + '44', backgroundColor: colors.cyan + '0f',
  },
  scanBtnActive: { opacity: 0.7 },
  scanBtnText: { fontFamily: fonts.mono, fontSize: 14, color: colors.cyan },
  hostList: { flex: 1, paddingHorizontal: spacing.md },
  hostCard: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: colors.panel, borderRadius: 12,
    borderWidth: 1, borderColor: colors.border,
    padding: spacing.md, marginBottom: spacing.sm, gap: spacing.md,
  },
  hostIcon: {
    width: 44, height: 44, borderRadius: 22,
    backgroundColor: colors.cyan + '18', borderWidth: 1, borderColor: colors.cyan + '33',
    alignItems: 'center', justifyContent: 'center',
  },
  hostInfo: { flex: 1 },
  hostName: { fontFamily: fonts.mono, fontSize: 14, color: colors.bright, marginBottom: 2 },
  hostMeta: { fontFamily: fonts.mono, fontSize: 11, color: colors.muted },
  emptyState: { alignItems: 'center', paddingTop: 40, gap: 12 },
  emptyText: { fontFamily: fonts.display, fontSize: 16, color: colors.subtle },
  emptyHint: { fontFamily: fonts.body, fontSize: 13, color: colors.muted, textAlign: 'center', lineHeight: 20 },
  manualSection: { padding: spacing.md, borderTopWidth: 1, borderTopColor: colors.border },
  manualLabel: { fontFamily: fonts.mono, fontSize: 11, color: colors.muted, marginBottom: spacing.sm },
  manualRow: { flexDirection: 'row', gap: spacing.sm },
  manualInput: {
    flex: 1, backgroundColor: colors.panel, borderRadius: 10,
    paddingHorizontal: 14, paddingVertical: 10,
    fontFamily: fonts.mono, fontSize: 14, color: colors.text,
    borderWidth: 1, borderColor: colors.border,
  },
  connectBtn: {
    backgroundColor: colors.cyan + '18', borderRadius: 10,
    paddingHorizontal: 18, paddingVertical: 10,
    borderWidth: 1, borderColor: colors.cyan + '44', justifyContent: 'center',
  },
  connectBtnDisabled: { opacity: 0.4 },
  connectBtnText: { fontFamily: fonts.mono, fontSize: 14, color: colors.cyan },
})
