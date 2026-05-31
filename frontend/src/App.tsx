import { useMemo, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import './App.css'

type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
}

type AskResponse = {
  answer?: string
  sources?: unknown[]
}

const SUGGESTIONS = [
  '경복궁 쉽게 설명해줘',
  '석굴암 심화 설명해줘',
  '창덕궁 퀴즈 내줘',
  '경주에서 볼만한 국가유산 추천해줘',
]

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

function createMessage(role: ChatMessage['role'], content: string): ChatMessage {
  return {
    id: `${role}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    content,
  }
}

function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    createMessage(
      'assistant',
      '안녕하세요. 저는 국가유산 AI 해설사입니다. 궁금한 유산 이름이나 지역을 물어보세요.',
    ),
  ])
  const [question, setQuestion] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const canSubmit = useMemo(() => question.trim().length > 0 && !isLoading, [question, isLoading])

  async function ask(nextQuestion: string) {
    const trimmed = nextQuestion.trim()
    if (!trimmed || isLoading) return

    setQuestion('')
    setMessages((prev) => [...prev, createMessage('user', trimmed)])
    setIsLoading(true)

    try {
      const response = await fetch(`${API_BASE_URL}/api/rag/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: trimmed }),
      })

      if (!response.ok) {
        throw new Error(`API request failed: ${response.status}`)
      }

      const data = (await response.json()) as AskResponse
      setMessages((prev) => [
        ...prev,
        createMessage('assistant', data.answer || '답변을 만들지 못했습니다. 다시 질문해 주세요.'),
      ])
    } catch (error) {
      console.error(error)
      setMessages((prev) => [
        ...prev,
        createMessage('assistant', '잠시 오류가 났습니다. 서버 상태를 확인한 뒤 다시 시도해 주세요.'),
      ])
    } finally {
      setIsLoading(false)
      requestAnimationFrame(() => inputRef.current?.focus())
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void ask(question)
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void ask(question)
    }
  }

  return (
    <main className="app-shell">
      <header className="hero-section">
        <p className="eyebrow">HERITAGE RAG CHAT</p>
        <h1>국가유산 AI 해설사</h1>
        <p className="subtitle">궁궐, 유적, 국보, 보물에 대해 물어보세요. 국가유산청 데이터 기반으로 답합니다.</p>
      </header>

      <section className="chat-panel" aria-label="국가유산 AI 채팅">
        <div className="messages" aria-live="polite">
          {messages.map((message) => (
            <article key={message.id} className={`message ${message.role}`}>
              {message.content}
            </article>
          ))}
          {isLoading && <article className="message assistant loading">답변을 찾는 중입니다…</article>}
        </div>

        <div className="suggestions" aria-label="추천 질문">
          {SUGGESTIONS.map((suggestion) => (
            <button key={suggestion} type="button" onClick={() => void ask(suggestion)} disabled={isLoading}>
              {suggestion}
            </button>
          ))}
        </div>

        <form className="composer" onSubmit={handleSubmit}>
          <textarea
            ref={inputRef}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            placeholder="예: 훈민정음에 대해 쉽게 설명해줘"
            disabled={isLoading}
          />
          <button type="submit" disabled={!canSubmit}>
            전송
          </button>
        </form>
      </section>

      <footer className="footer">답변은 실험용입니다. 중요한 내용은 국가유산청 원문과 함께 확인하세요.</footer>
    </main>
  )
}

export default App
