/**
 * Memory Screen — mobile
 */

import React, { useState, useEffect } from 'react'
import {
  View, Text, TextInput, FlatList, TouchableOpacity,
  StyleSheet, ActivityIndicator,
} from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { Ionicons } from '@expo/vector-icons'
import { searchMemory, getTimeline, storeMemory } from '../services/api'
import { colors, fonts, spacing } from '../theme'
import { format } from 'date-fns'

export default function MemoryScreen() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<any[]>([])
  const [timeline, setTimeline] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [newMemory, setNewMemory] = useState('')
  const [storing, setStoring] = useState(false)
  const [tab, setTab] = useState<'timeline' | 'search'>('timeline')

  useEffect(() => { load() }, [])

  const load = async () => {
    setLoading(true)
    try {
      const data = await getTimeline(48)
      setTimeline(data.nodes || [])
    } catch {} finally { setLoading(false) }
  }

  const search = async () => {
    if (!query.trim()) return
    setLoading(true)
    try {
      const data = await searchMemory(query)
      setResults(data.results || [])
      setTab('search')
    } catch {} finally { setLoading(false) }
  }

  const store = async () => {
    if (!newMemory.trim()) return
    setStoring(true)
    try {
      await storeMemory(newMemory, ['mobile', 'manual'])
      setNewMemory('')
      await load()
    } catch {} finally { setStoring(false) }
  }

  const nodes = tab === 'search' ? results : timeline

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.searchBar}>
        <Ionicons name="search" size={16} color={colors.muted} style={styles.searchIcon} />
        <TextInput
          style={styles.searchInput}
          value={query}
          onChangeText={setQuery}
          onSubmitEditing={search}
          placeholder="Search memories…"
          placeholderTextColor={colors.muted}
          returnKeyType="search"
        />
        {query ? (
          <TouchableOpacity onPress={() => { setQuery(''); setTab('timeline') }}>
            <Ionicons name="close-circle" size={18} color={colors.muted} />
          </TouchableOpacity>
        ) : null}
      </View>

      <View style={styles.storeBar}>
        <TextInput
          style={styles.storeInput}
          value={newMemory}
          onChangeText={setNewMemory}
          placeholder="Store a new memory…"
          placeholderTextColor={colors.muted}
        />
        <TouchableOpacity
          style={[styles.storeBtn, !newMemory.trim() && styles.storeBtnDisabled]}
          onPress={store}
          disabled={!newMemory.trim() || storing}
        >
          {storing
            ? <ActivityIndicator size="small" color={colors.green} />
            : <Ionicons name="add" size={20} color={colors.green} />
          }
        </TouchableOpacity>
      </View>

      <View style={styles.tabs}>
        {(['timeline', 'search'] as const).map(t => (
          <TouchableOpacity key={t} onPress={() => setTab(t)}
            style={[styles.tab, tab === t && styles.tabActive]}>
            <Text style={[styles.tabText, tab === t && styles.tabTextActive]}>
              {t === 'timeline' ? `Timeline (${timeline.length})` : `Search (${results.length})`}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {loading
        ? <ActivityIndicator style={styles.loader} color={colors.purple} />
        : <FlatList
            data={nodes}
            keyExtractor={(n, i) => n.id || String(i)}
            renderItem={({ item: n }) => (
              <View style={styles.card}>
                <Text style={styles.cardText}>{n.content}</Text>
                <View style={styles.cardMeta}>
                  {(n.tags || []).slice(0, 3).map((t: string) => (
                    <View key={t} style={styles.tag}>
                      <Text style={styles.tagText}>{t}</Text>
                    </View>
                  ))}
                  {n.created_at && (
                    <Text style={styles.timestamp}>
                      {format(new Date(n.created_at * 1000), 'MMM d HH:mm')}
                    </Text>
                  )}
                </View>
              </View>
            )}
            contentContainerStyle={styles.list}
            ListEmptyComponent={
              <View style={styles.empty}>
                <Text style={styles.emptyText}>No memories yet</Text>
              </View>
            }
          />
      }
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.void },
  searchBar: {
    flexDirection: 'row', alignItems: 'center',
    margin: spacing.md, backgroundColor: colors.panel,
    borderRadius: 12, borderWidth: 1, borderColor: colors.border,
    paddingHorizontal: 12, paddingVertical: 8,
  },
  searchIcon: { marginRight: 8 },
  searchInput: { flex: 1, fontFamily: fonts.body, fontSize: 15, color: colors.text },
  storeBar: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.sm,
    marginHorizontal: spacing.md, marginBottom: spacing.sm,
  },
  storeInput: {
    flex: 1, backgroundColor: colors.panel, borderRadius: 10,
    paddingHorizontal: 12, paddingVertical: 8,
    fontFamily: fonts.body, fontSize: 14, color: colors.text,
    borderWidth: 1, borderColor: colors.border,
  },
  storeBtn: {
    width: 40, height: 40, borderRadius: 10, alignItems: 'center', justifyContent: 'center',
    borderWidth: 1, borderColor: colors.green + '44', backgroundColor: colors.green + '18',
  },
  storeBtnDisabled: { opacity: 0.4 },
  tabs: { flexDirection: 'row', marginHorizontal: spacing.md, marginBottom: spacing.sm, gap: spacing.sm },
  tab: { flex: 1, padding: spacing.sm, borderRadius: 8, borderWidth: 1, borderColor: 'transparent', alignItems: 'center' },
  tabActive: { backgroundColor: colors.panel, borderColor: colors.border },
  tabText: { fontFamily: fonts.mono, fontSize: 12, color: colors.muted },
  tabTextActive: { color: colors.bright },
  loader: { marginTop: 40 },
  list: { padding: spacing.md },
  card: {
    backgroundColor: colors.panel, borderRadius: 12,
    borderWidth: 1, borderColor: colors.border,
    padding: spacing.md, marginBottom: spacing.sm,
  },
  cardText: { fontFamily: fonts.body, fontSize: 14, color: colors.text, lineHeight: 20 },
  cardMeta: { flexDirection: 'row', flexWrap: 'wrap', marginTop: 8, gap: 4, alignItems: 'center' },
  tag: { backgroundColor: colors.border, borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 },
  tagText: { fontFamily: fonts.mono, fontSize: 10, color: colors.subtle },
  timestamp: { fontFamily: fonts.mono, fontSize: 10, color: colors.muted, marginLeft: 'auto' },
  empty: { alignItems: 'center', paddingTop: 60 },
  emptyText: { fontFamily: fonts.mono, fontSize: 14, color: colors.muted },
})
