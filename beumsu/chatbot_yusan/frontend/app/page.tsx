"use client";

import { FormEvent, useState } from "react";
import { BookOpen, Loader2, MapPinned, Send, ShieldCheck } from "lucide-react";
import { Audience, ChatResponse, sendChat } from "../lib/api";

const audiences: Array<{ value: Audience; label: string }> = [
  { value: "general", label: "일반" },
  { value: "child", label: "어린이" },
  { value: "expert", label: "전문가" },
  { value: "elderly", label: "고령자" },
  { value: "visually_impaired", label: "시각장애인" },
  { value: "hearing_impaired", label: "청각장애인" }
];

export default function Home() {
  const [query, setQuery] = useState("경북궁 설명해줘");
  const [audience, setAudience] = useState<Audience>("general");
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      setResponse(await sendChat(query, audience));
    } catch (err) {
      setError(err instanceof Error ? err.message : "요청에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="shell">
      <section className="workspace">
        <aside className="sidebar">
          <div>
            <h1>국가유산 AI 해설</h1>
            <p>공식 근거 기반으로 답변하고, 엔티티 정규화와 검증 단계를 거칩니다.</p>
          </div>
          <div className="status">
            <ShieldCheck size={18} />
            <span>Guardrail + Claim Verification</span>
          </div>
          <div className="status">
            <BookOpen size={18} />
            <span>Hybrid RAG + pgvector-ready</span>
          </div>
        </aside>

        <section className="panel">
          <form onSubmit={submit} className="composer">
            <label htmlFor="query">질문</label>
            <textarea id="query" value={query} onChange={(event) => setQuery(event.target.value)} />
            <div className="controls">
              <select value={audience} onChange={(event) => setAudience(event.target.value as Audience)}>
                {audiences.map((item) => (
                  <option key={item.value} value={item.value}>{item.label}</option>
                ))}
              </select>
              <button disabled={loading || !query.trim()} type="submit">
                {loading ? <Loader2 className="spin" size={18} /> : <Send size={18} />}
                <span>질문</span>
              </button>
            </div>
          </form>

          {error ? <div className="error">{error}</div> : null}

          {response ? (
            <article className="answer">
              <div className="meta">
                <span>{response.intent}</span>
                <span>{response.detected_language}</span>
                <span>{response.latency_ms}ms</span>
              </div>
              <p>{response.answer}</p>

              {response.route ? (
                <section className="route">
                  <h2><MapPinned size={18} /> {response.route.route_title}</h2>
                  <ol>
                    {response.route.stops.map((stop) => (
                      <li key={`${stop.order}-${stop.name}`}>
                        <strong>{stop.name}</strong>
                        <span>{stop.description}</span>
                        {stop.accessibility_note ? <em>{stop.accessibility_note}</em> : null}
                      </li>
                    ))}
                  </ol>
                </section>
              ) : null}

              {response.images.length ? (
                <section className="imageStrip" aria-label="heritage images">
                  {response.images.map((image) => (
                    <figure key={image.image_id}>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={image.thumbnail_url ?? image.image_url}
                        alt={image.caption || image.title || image.heritage_id}
                        loading="lazy"
                      />
                      <figcaption>
                        <strong>{image.title || image.heritage_id}</strong>
                        {image.caption ? <span>{image.caption}</span> : null}
                        {image.license_type ? <em>{image.license_type}</em> : null}
                      </figcaption>
                    </figure>
                  ))}
                </section>
              ) : null}

              <section className="evidence">
                <h2>근거</h2>
                {response.citations.map((citation) => (
                  <div className="citation" key={`${citation.document_id}-${citation.chunk_id}`}>
                    <strong>{citation.title}</strong>
                    <span>{citation.source_type} · {citation.source_trust_level}</span>
                  </div>
                ))}
              </section>
            </article>
          ) : null}
        </section>
      </section>
    </main>
  );
}
