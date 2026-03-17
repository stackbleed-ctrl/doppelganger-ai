/**
 * Home Screen
 * Main chat interface + proactive suggestions feed
 */

import React, { useState, useRef, useEffect, useCallback } from 'react'
import {
  View, Text, TextInput, TouchableOpacity, FlatList,
  KeyboardAvoidingView, Platform, ActivityIndicator,
  StyleSheet, Animated, Vibration,
} from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { Ionicons } from '@expo/vector-icons'
import { useChatStore } from '../hooks/useChatStore'
import { SuggestionCard } from '../components/SuggestionCard'
import { streamChat, getSuggestions } from '../services/api'
import { colors, fonts, spacing } from '../theme'

interface Message {
  id: string
  role: 'user' | 'assistant'
  text: string
  ts: number
  streaming?: boolean
}

export default function HomeScreen() {
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [suggestions, setSuggestions] = useState<any[]>([])
  const listRef = useRef<FlatList>(null)
  const inputRef = useRef<TextInput>(null)
  const typingOpacity = useRef(new Animated.Value(0)).current

  useEffect(() => {
    loadSuggestions()
  }, [])

  const loadSuggestions = async () => {
    try {
      const data = await getSuggestions(3)
      setSuggestions(data.suggestions || [])
    } catch {}
  }

  const handleSend = useCallback(async () => {
    const text = input.trim()
    if (!text || loading) return

    setInput('')
    setLoading(true)
    Vibration.vibrate(10)

    const userMsg: Message = { id: Date.now().toString(), role: 'user', text, ts: Date.now() }
    const assistantId = (Date.now() + 1).toString()
    const assistantMsg: Message = { id: assistantId, role: 'assistant', text: '', ts: Date.now(), streaming: true }

    setMessages(prev => [...prev, userMsg, assistantMsg])

    // Animate typing indicator
    Animated.loop(
      Animated.sequence([
        Animated.timing(typingOpacity, { toValue: 1, duration: 400, useNativeDriver: true }),
        Animated.timing(typingOpacity, { toValue: 0.3, duration: 400, useNativeDriver: true }),
      ])
    ).start()

    try {
      let fullText = ''
      for await (const chunk of streamChat(text)) {
        fullText += chunk
        setMessages(prev => prev.map(m =>
          m.id === assistantId ? { ...m, text: fullText } : m
        ))
      }
      setMessages(prev => prev.map(m =>
        m.id === assistantId ? { ...m, streaming: false } : m
      ))
    } catch (e: any) {
      setMessages(prev => prev.map(m =>
        m.id === assistantId ? { ...m, text: `Error: ${e.message}`, streaming: false } : m
      ))
    } finally {
      setLoading(false)
      typingOpacity.stopAnimation()
    }

    setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 100)
  }, [input, loading])

  const renderMessage = ({ item }: { item: Message }) => {
    const isUser = item.role === 'user'
    return (
      <View style={[styles.messageRow, isUser && styles.messageRowUser]}>
        <View style={[styles.avatar, isUser ? styles.avatarUser : styles.avatarBot]}>
          <Text style={styles.avatarText}>{isUser ? 'U' : 'D'}</Text>
        </View>
        <View style={[styles.bubble, isUser ? styles.bubbleUser : styles.bubbleBot]}>
          <Text style={[styles.messageText, isUser && styles.messageTextUser]}>
            {item.text}
            {item.streaming && <Animated.Text style={[styles.cursor, { opacity: typingOpacity }]}>█</Animated.Text>}
          </Text>
        </View>
      </View>
    )
  }

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={90}
      >
        {/* Suggestions strip */}
        {suggestions.length > 0 && messages.length === 0 && (
          <View style={styles.suggestionsStrip}>
            {suggestions.map(s => (
              <SuggestionCard
                key={s.id}
                suggestion={s}
                onDismiss={() => setSuggestions(prev => prev.filter(x => x.id !== s.id))}
                onTap={() => setInput(s.text.slice(0, 80))}
              />
            ))}
          </View>
        )}

        {/* Message list */}
        <FlatList
          ref={listRef}
          data={messages}
          keyExtractor={m => m.id}
          renderItem={renderMessage}
          contentContainerStyle={styles.messageList}
          ListEmptyComponent={
            <View style={styles.emptyState}>
              <Text style={styles.emptyEmoji}>🧬</Text>
              <Text style={styles.emptyTitle}>Your twin is listening</Text>
              <Text style={styles.emptySubtitle}>Type or speak to begin</Text>
            </View>
          }
        />

        {/* Input bar */}
        <View style={styles.inputBar}>
          <TextInput
            ref={inputRef}
            style={styles.input}
            value={input}
            onChangeText={setInput}
            placeholder="Ask your twin anything…"
            placeholderTextColor={colors.muted}
            multiline
            maxLength={2000}
            onSubmitEditing={handleSend}
            returnKeyType="send"
            blurOnSubmit
          />
          <TouchableOpacity
            style={[styles.sendBtn, (!input.trim() || loading) && styles.sendBtnDisabled]}
            onPress={handleSend}
            disabled={!input.trim() || loading}
          >
            {loading
              ? <ActivityIndicator size="small" color={colors.cyan} />
              : <Ionicons name="arrow-up" size={20} color={input.trim() ? colors.cyan : colors.muted} />
            }
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.void },
  flex: { flex: 1 },
  suggestionsStrip: { padding: spacing.md, gap: spacing.sm },
  messageList: { padding: spacing.md, paddingBottom: spacing.lg },
  messageRow: { flexDirection: 'row', marginBottom: spacing.md, gap: spacing.sm },
  messageRowUser: { flexDirection: 'row-reverse' },
  avatar: {
    width: 32, height: 32, borderRadius: 16,
    alignItems: 'center', justifyContent: 'center',
    flexShrink: 0,
  },
  avatarBot: { backgroundColor: colors.cyanDim, borderWidth: 1, borderColor: colors.cyan + '44' },
  avatarUser: { backgroundColor: colors.purpleDim, borderWidth: 1, borderColor: colors.purple + '44' },
  avatarText: { fontFamily: fonts.mono, fontSize: 12, color: colors.bright, fontWeight: '700' },
  bubble: {
    maxWidth: '75%', borderRadius: 18, paddingHorizontal: 14, paddingVertical: 10,
    borderWidth: 1,
  },
  bubbleBot: { backgroundColor: colors.panel, borderColor: colors.border },
  bubbleUser: { backgroundColor: colors.purple + '18', borderColor: colors.purple + '33' },
  messageText: { fontFamily: fonts.body, fontSize: 15, color: colors.text, lineHeight: 22 },
  messageTextUser: {},
  cursor: { color: colors.cyan },
  inputBar: {
    flexDirection: 'row', alignItems: 'flex-end',
    padding: spacing.md, gap: spacing.sm,
    borderTopWidth: 1, borderTopColor: colors.border,
    backgroundColor: colors.surface,
  },
  input: {
    flex: 1, backgroundColor: colors.panel, borderRadius: 20,
    paddingHorizontal: 16, paddingVertical: 10,
    fontFamily: fonts.body, fontSize: 15, color: colors.text,
    borderWidth: 1, borderColor: colors.border,
    maxHeight: 120, minHeight: 44,
  },
  sendBtn: {
    width: 44, height: 44, borderRadius: 22,
    backgroundColor: colors.panel, borderWidth: 1, borderColor: colors.border,
    alignItems: 'center', justifyContent: 'center',
  },
  sendBtnDisabled: { opacity: 0.4 },
  emptyState: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingTop: 120 },
  emptyEmoji: { fontSize: 48, marginBottom: 16 },
  emptyTitle: { fontFamily: fonts.display, fontSize: 18, color: colors.subtle, marginBottom: 8 },
  emptySubtitle: { fontFamily: fonts.mono, fontSize: 12, color: colors.muted },
})
