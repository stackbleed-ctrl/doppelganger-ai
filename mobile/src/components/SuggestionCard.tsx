import React from 'react'
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { colors, fonts, spacing } from '../theme'

const TYPE_COLORS: Record<string, string> = {
  morning_brief:   colors.amber,
  evening_summary: colors.purple,
  pattern_insight: colors.green,
  task_reminder:   colors.red,
  goal_nudge:      colors.amber,
  context_tip:     colors.cyan,
  weekly_review:   colors.cyan,
}

interface Props {
  suggestion: { id: string; type: string; text: string; confidence: number }
  onDismiss: () => void
  onTap: () => void
}

export function SuggestionCard({ suggestion, onDismiss, onTap }: Props) {
  const color = TYPE_COLORS[suggestion.type] || colors.subtle
  const label = suggestion.type.replace(/_/g, ' ')

  return (
    <TouchableOpacity style={[styles.card, { borderColor: color + '44' }]} onPress={onTap}>
      <View style={styles.row}>
        <Ionicons name="sparkles" size={14} color={color} />
        <Text style={[styles.type, { color }]}>{label}</Text>
        <TouchableOpacity onPress={onDismiss} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
          <Ionicons name="close" size={14} color={colors.muted} />
        </TouchableOpacity>
      </View>
      <Text style={styles.text} numberOfLines={3}>{suggestion.text}</Text>
    </TouchableOpacity>
  )
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.panel, borderRadius: 12,
    borderWidth: 1, padding: spacing.md, marginBottom: spacing.sm,
  },
  row: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 },
  type: { fontFamily: fonts.mono, fontSize: 11, fontWeight: '600', flex: 1, textTransform: 'capitalize' },
  text: { fontFamily: fonts.body, fontSize: 14, color: colors.text, lineHeight: 20 },
})
