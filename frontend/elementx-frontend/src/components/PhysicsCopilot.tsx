import { useEffect, useId, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import {
  MagnetApiError,
  getCopilotStatus,
  listSamples,
  sendCopilotMessage,
  type CopilotHistoryMessage,
  type CopilotStatus,
  type SampleSummary,
} from '../services/magnetApi'
import Button from './ui/Button'
import Notice from './ui/Notice'
import SelectField from './ui/SelectField'
import TextAreaField from './ui/TextAreaField'

interface ChatMessage {
  role: 'user' | 'assistant'
  text: string
  meta?: string
  isError?: boolean
}

const QUICK_PROMPTS: { label: string; prompt: string; needsSample: boolean }[] = [
  {
    label: 'Summarize saved experiments',
    prompt: 'Summarize the saved experiments for this sample using only the stored values.',
    needsSample: true,
  },
  {
    label: 'What coercivity is stored?',
    prompt: 'What coercivity (Hc) values are stored for this sample, and at which temperatures?',
    needsSample: true,
  },
  {
    label: 'What is missing?',
    prompt: 'What data is missing or unavailable for this sample, and what should I measure next?',
    needsSample: true,
  },
]

function errorMessage(err: unknown): string {
  if (err instanceof MagnetApiError) return err.detail
  if (err instanceof Error) return err.message
  return 'The Copilot request failed.'
}

function modelStatus(
  status: CopilotStatus | null,
  loading: boolean,
  failed: boolean,
): { text: string; tone: 'ok' | 'limited' | 'unknown' } {
  if (status) {
    return status.llmAvailable
      ? { text: `Language model available${status.model ? ` (${status.model})` : ''}`, tone: 'ok' }
      : {
          text: 'Language model not configured: replies quote your stored records',
          tone: 'limited',
        }
  }
  return {
    text: loading ? 'Checking Copilot status…' : failed ? 'Copilot status unavailable' : '',
    tone: 'unknown',
  }
}

export default function PhysicsCopilot() {
  const [samples, setSamples] = useState<SampleSummary[]>([])
  const [status, setStatus] = useState<CopilotStatus | null>(null)
  const [selectedSampleId, setSelectedSampleId] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const threadRef = useRef<HTMLDivElement | null>(null)
  const composerRef = useRef<HTMLTextAreaElement | null>(null)
  const wasBusy = useRef(false)
  const scopeId = useId()

  useEffect(() => {
    let cancelled = false
    Promise.all([getCopilotStatus(), listSamples()])
      .then(([copilotStatus, listed]) => {
        if (cancelled) return
        setStatus(copilotStatus)
        setSamples(listed)
      })
      .catch((err) => {
        if (!cancelled) setLoadError(errorMessage(err))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    const thread = threadRef.current
    if (thread) thread.scrollTop = thread.scrollHeight
  }, [messages, busy])

  useEffect(() => {
    // The question box is disabled while a reply is pending; put the cursor back afterwards.
    if (wasBusy.current && !busy) composerRef.current?.focus()
    wasBusy.current = busy
  }, [busy])

  const selectedSample = samples.find((sample) => sample.id === selectedSampleId) ?? null
  const model = modelStatus(status, loading, loadError !== null)

  const send = async (text: string) => {
    const message = text.trim()
    if (!message || busy) return

    const history: CopilotHistoryMessage[] = messages
      .filter((entry) => !entry.isError)
      .map((entry) => ({ role: entry.role, content: entry.text }))

    setMessages((current) => [...current, { role: 'user', text: message }])
    setInput('')
    setBusy(true)
    try {
      const reply = await sendCopilotMessage(message, selectedSampleId || null, history)
      const grounding = reply.sampleName
        ? `Based on saved records for “${reply.sampleName}”`
        : 'No sample selected'
      const origin =
        reply.source === 'stored-records' ? 'stored values (language model offline)' : reply.source
      setMessages((current) => [
        ...current,
        { role: 'assistant', text: reply.answer, meta: `${grounding} · ${origin}` },
      ])
    } catch (err) {
      setMessages((current) => [
        ...current,
        { role: 'assistant', text: errorMessage(err), isError: true },
      ])
    } finally {
      setBusy(false)
    }
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    void send(input)
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      void send(input)
    }
  }

  return (
    <div className={`copilot${messages.length === 0 && !busy ? ' copilot--empty' : ''}`}>
      <div className="copilot__context">
        <SelectField
          label="Research sample"
          value={selectedSampleId}
          onChange={(event) => setSelectedSampleId(event.target.value)}
          disabled={busy || loading}
        >
          <option value="">No sample (general question)</option>
          {samples.map((sample) => (
            <option key={sample.id} value={sample.id}>
              {sample.name}
              {sample.formula ? ` — ${sample.formula}` : ''}
            </option>
          ))}
        </SelectField>
        {model.text && (
          <p
            className={`status-chip${model.tone === 'ok' ? ' status-chip--ok' : model.tone === 'limited' ? ' status-chip--limited' : ''}`}
            role="status"
          >
            {model.text}
          </p>
        )}
      </div>

      {loadError && <Notice kind="error">{loadError}</Notice>}
      {!loading && !loadError && samples.length === 0 && (
        <p className="note">
          No research samples yet. Add one under Samples to ground the Copilot in saved
          experiments.
        </p>
      )}

      <div
        className="copilot__thread"
        ref={threadRef}
        role="log"
        aria-live="polite"
        aria-label="Conversation"
        tabIndex={0}
      >
        {messages.length === 0 && (
          <div className="copilot__empty">
            {selectedSample ? (
              <p>
                Ask about “{selectedSample.name}”. Answers use only the values stored for this
                sample.
              </p>
            ) : (
              <p>
                No sample selected. Choose a sample above to ground answers in its saved
                experiments, or ask a general question.
              </p>
            )}
          </div>
        )}
        {messages.map((entry, index) => (
          <article
            key={index}
            className={`msg msg--${entry.role}${entry.isError ? ' msg--error' : ''}`}
          >
            <div className="msg__who">{entry.role === 'user' ? 'You' : 'Copilot'}</div>
            <p className="msg__text">{entry.text}</p>
            {entry.meta && <div className="msg__meta">{entry.meta}</div>}
          </article>
        ))}
        {busy && <p className="copilot__empty">Working on it…</p>}
      </div>

      <div className="copilot__composer">
        {selectedSample && (
          <div className="copilot__quick">
            {QUICK_PROMPTS.map((item) => (
              <Button key={item.label} disabled={busy} onClick={() => void send(item.prompt)}>
                {item.label}
              </Button>
            ))}
          </div>
        )}

        <form className="composer" onSubmit={handleSubmit}>
          <TextAreaField
            label="Your question"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            ref={composerRef}
            onKeyDown={handleKeyDown}
            placeholder="e.g. What coercivity values are stored for this sample?"
            maxLength={6000}
            rows={2}
            disabled={busy}
            aria-describedby={scopeId}
          />
          <Button type="submit" variant="primary" disabled={busy || !input.trim()}>
            Send
          </Button>
        </form>

        <p className="copilot__scope" id={scopeId}>
          Enter sends; Shift+Enter adds a line. The Copilot reads your stored results and does
          not re-analyse files. The largest measured moment is never presented as saturation
          magnetization, and XRD maxima are candidate intensity maxima only — no phase, lattice,
          or crystallite-size claims are made.
        </p>
      </div>
    </div>
  )
}
