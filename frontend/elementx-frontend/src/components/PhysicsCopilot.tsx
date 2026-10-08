import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  MagnetApiError,
  getCopilotStatus,
  listSamples,
  sendCopilotMessage,
  type CopilotHistoryMessage,
  type CopilotStatus,
  type SampleSummary,
} from '../services/magnetApi'

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

export default function PhysicsCopilot() {
  const [samples, setSamples] = useState<SampleSummary[]>([])
  const [status, setStatus] = useState<CopilotStatus | null>(null)
  const [selectedSampleId, setSelectedSampleId] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const endRef = useRef<HTMLDivElement | null>(null)

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
    endRef.current?.scrollIntoView?.({ block: 'end' })
  }, [messages, busy])

  const selectedSample = samples.find((sample) => sample.id === selectedSampleId) ?? null

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

  return (
    <section className="panel copilot-panel" aria-labelledby="copilot-title">
      <header className="panel-header">
        <h2 id="copilot-title">Physics Copilot</h2>
        <p>
          Ask about your saved research samples. Answers are grounded only in values already
          stored by the analysis pipeline.
        </p>
      </header>

      <div className="status-banner status-banner--info" role="note">
        The Copilot reads your stored results; it does not re-analyse files. The largest measured
        moment is never presented as saturation magnetization, and XRD maxima are candidate
        intensity maxima only — no phase, lattice, or crystallite-size claims are made.
      </div>

      {status && !status.llmAvailable && (
        <div className="status-banner status-banner--conflict" role="status">
          The language model is not configured on this server, so replies show your stored
          records directly.
        </div>
      )}

      {loadError && (
        <div className="status-banner status-banner--error" role="alert">
          {loadError}
        </div>
      )}

      <div className="copilot-controls">
        <label className="field-label" htmlFor="copilot-sample">
          Research sample
        </label>
        <select
          id="copilot-sample"
          className="text-input"
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
        </select>
        {!loading && samples.length === 0 && (
          <p className="empty-state">
            No research samples yet. Create one under Research Samples to ground the Copilot in
            saved experiments.
          </p>
        )}
      </div>

      <div className="copilot-quick">
        {QUICK_PROMPTS.map((item) => (
          <button
            key={item.label}
            type="button"
            className="secondary-btn"
            disabled={busy || (item.needsSample && !selectedSample)}
            onClick={() => void send(item.prompt)}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="copilot-thread" aria-live="polite">
        {messages.length === 0 && (
          <p className="empty-state">
            {selectedSample
              ? `Ask a question about “${selectedSample.name}”.`
              : 'Select a sample, or ask a general question.'}
          </p>
        )}
        {messages.map((entry, index) => (
          <div
            key={index}
            className={`copilot-message copilot-message--${entry.role}${entry.isError ? ' copilot-message--error' : ''}`}
          >
            <div className="copilot-message__who">{entry.role === 'user' ? 'You' : 'Copilot'}</div>
            <pre className="copilot-message__text">{entry.text}</pre>
            {entry.meta && <div className="copilot-message__meta">{entry.meta}</div>}
          </div>
        ))}
        {busy && <div className="copilot-working">Working on it…</div>}
        <div ref={endRef} />
      </div>

      <form className="copilot-input" onSubmit={handleSubmit}>
        <label className="field-label" htmlFor="copilot-message">
          Your question
        </label>
        <div className="copilot-input__row">
          <input
            id="copilot-message"
            className="text-input"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="e.g. What coercivity values are stored for this sample?"
            maxLength={6000}
            disabled={busy}
          />
          <button type="submit" className="primary-btn" disabled={busy || !input.trim()}>
            Send
          </button>
        </div>
      </form>
    </section>
  )
}
