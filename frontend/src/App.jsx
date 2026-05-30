import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// FastAPI 백엔드 주소 (.env 의 VITE_API_BASE 로 덮어쓸 수 있음)
const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

// 익명 사용자 ID (개인화용) — localStorage에 1회 생성 후 유지
function getUserId() {
  let id = localStorage.getItem("heritage_uid");
  if (!id) {
    id =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : "u-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem("heritage_uid", id);
  }
  return id;
}

const LANGS = [
  { code: "ko", label: "한" },
  { code: "en", label: "EN" },
  { code: "zh", label: "中" },
  { code: "ja", label: "日" },
];

const SUGGESTIONS = [
  "숭례문은 폭설로 무너진 적 있어?",
  "숭례문이랑 원각사지 십층석탑 비교해줘",
  "홍예문이 뭐야?",
  "원각사는 왜 없어졌어?",
];

const WELCOME = {
  role: "bot",
  text:
    "안녕하세요! 국가유산 AI 해설사예요. 🏛️\n" +
    "국가유산청 자료에 근거해 답해 드려요. 무엇이 궁금하신가요?",
  showSuggestions: true,
};

// 응답 메트릭 배지 텍스트 (토큰·지연·모델)
function shortModel(m) {
  return (m || "").replace("gemini-2.5-", "").replace("gemini-", "") || "—";
}
function formatMeta(meta) {
  if (!meta) return "";
  if (meta.cached) return "⚡ 캐시 적중 · 0 토큰 · 즉시";
  const tok = (meta.total_tokens || 0).toLocaleString();
  const ms = meta.latency_ms || 0;
  const dur = ms >= 1000 ? (ms / 1000).toFixed(1) + "s" : ms + "ms";
  return `⚡ ${dur} · ${tok} 토큰 · ${shortModel(meta.answer_model)}`;
}

function nowLabel() {
  const d = new Date();
  const h = d.getHours();
  const m = d.getMinutes().toString().padStart(2, "0");
  const ampm = h < 12 ? "오전" : "오후";
  const hh = h % 12 === 0 ? 12 : h % 12;
  return `${ampm} ${hh}:${m}`;
}

export default function App() {
  const [messages, setMessages] = useState([WELCOME]);
  const [input, setInput] = useState("");
  const [lang, setLang] = useState("ko");
  const [loading, setLoading] = useState(false);
  const [openSrc, setOpenSrc] = useState(() => new Set()); // 근거 원문 펼친 메시지 index
  const [interests, setInterests] = useState([]); // 학습된 관심 분야
  const [recommend, setRecommend] = useState({ category: "", items: [] });
  const [userId] = useState(getUserId);
  const scrollRef = useRef(null);

  async function refreshInterests() {
    try {
      const [meRes, recRes] = await Promise.all([
        fetch(`${API_BASE}/api/me?user_id=${encodeURIComponent(userId)}`),
        fetch(`${API_BASE}/api/recommend?user_id=${encodeURIComponent(userId)}&n=3`),
      ]);
      if (meRes.ok) {
        const j = await meRes.json();
        setInterests((j.interests || []).map((i) => i.category));
      }
      if (recRes.ok) setRecommend(await recRes.json());
    } catch {
      /* 무시 */
    }
  }

  useEffect(() => {
    refreshInterests();
  }, []);

  function toggleSrc(i) {
    setOpenSrc((prev) => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });
  }

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, loading]);

  const send = useCallback(
    async (textArg) => {
      const text = (textArg ?? input).trim();
      if (!text || loading) return;
      // 직전 대화 이력 수집 (환영 메시지 제외, 최근 6턴 — 서버가 추가로 더 줄임)
      const history = messages
        .filter((mm) => mm.text && !mm.showSuggestions)
        .slice(-6)
        .map((mm) => ({ role: mm.role, text: mm.text }));
      setInput("");
      setMessages((prev) => [...prev, { role: "user", text, time: nowLabel() }]);
      setLoading(true);
      try {
        const res = await fetch(`${API_BASE}/api/rag`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question: text,
            lang,
            top_k: 6,
            history,
            user_id: userId,
          }),
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || `요청 실패 (HTTP ${res.status})`);
        }
        const json = await res.json();
        setMessages((prev) => [
          ...prev,
          {
            role: "bot",
            text: json.answer,
            sources: json.sources || [],
            meta: json.meta || null,
            images:
              json.images && json.images.length
                ? json.images
                : json.imageUrl
                ? [{ url: json.imageUrl, name: json.imageName }]
                : [],
            time: nowLabel(),
          },
        ]);
        refreshInterests(); // 관심사 학습 갱신
      } catch (e) {
        setMessages((prev) => [
          ...prev,
          {
            role: "bot",
            text: "⚠️ " + (e.message || "오류가 발생했습니다."),
            time: nowLabel(),
          },
        ]);
      } finally {
        setLoading(false);
      }
    },
    [input, lang, loading, messages, userId]
  );

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  // 소스 라벨 중복 제거 (유산명/용어명)
  function uniqueSources(sources) {
    const seen = new Set();
    const out = [];
    for (const s of sources) {
      if (seen.has(s.label)) continue;
      seen.add(s.label);
      out.push(s);
    }
    return out.slice(0, 5);
  }

  return (
    <div className="phone">
      <header className="header">
        <div className="avatar">🏛️</div>
        <div>
          <div className="title">국가유산 AI 해설사</div>
          <div className="status">
            {interests.length > 0
              ? `🎯 관심 분야: ${interests.slice(0, 3).join(", ")}`
              : "● 국가유산청 자료 기반 · 항상 응답"}
          </div>
        </div>
        <div className="spacer" />
        <div className="lang-pills">
          {LANGS.map((l) => (
            <button
              key={l.code}
              className={lang === l.code ? "active" : ""}
              onClick={() => setLang(l.code)}
              title={l.code}
            >
              {l.label}
            </button>
          ))}
        </div>
      </header>

      <div className="messages" ref={scrollRef}>
        <div className="date-divider">오늘</div>

        {messages.map((m, i) =>
          m.role === "user" ? (
            <div className="row user" key={i}>
              <span className="bubble-time">{m.time}</span>
              <div className="msg-col">
                <div className="bubble user">{m.text}</div>
              </div>
            </div>
          ) : (
            <div className="row bot" key={i}>
              <div className="bot-avatar">🏛️</div>
              <div className="msg-col">
                <div className="sender">해설사</div>
                <div className="bubble bot">
                  {m.images && m.images.length > 0 && (
                    <div
                      className={
                        "heritage-imgs" + (m.images.length > 1 ? " multi" : "")
                      }
                    >
                      {m.images.map((img, k) => (
                        <figure className="heritage-fig" key={k}>
                          <img
                            src={img.url}
                            alt={img.name}
                            onError={(e) =>
                              (e.target.closest("figure").style.display = "none")
                            }
                          />
                          {m.images.length > 1 && (
                            <figcaption>{img.name}</figcaption>
                          )}
                        </figure>
                      ))}
                    </div>
                  )}
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {m.text}
                  </ReactMarkdown>
                  {m.sources && m.sources.length > 0 && (
                    <div className="src-area">
                      <div className="sources">
                        <span className="label">📚 참고</span>
                        {uniqueSources(m.sources).map((s, k) => (
                          <span className="source-chip" key={k}>
                            {s.label}
                          </span>
                        ))}
                      </div>
                      <button
                        className="src-toggle"
                        onClick={() => toggleSrc(i)}
                      >
                        {openSrc.has(i)
                          ? "근거 원문 접기 ▲"
                          : `🔎 근거 원문 보기 (${m.sources.length})`}
                      </button>
                      {openSrc.has(i) && (
                        <div className="src-list">
                          {m.sources.map((s, k) => (
                            <div className="src-item" key={k}>
                              <div className="src-item-head">
                                [{s.label}]{" "}
                                {s.similarity > 0
                                  ? `유사도 ${Math.round(s.similarity * 100)}%`
                                  : "키워드 매칭"}
                              </div>
                              <div className="src-item-body">{s.content}</div>
                              {s.refs && s.refs.length > 0 && (
                                <div className="src-refs">
                                  {s.refs.map((rf, ri) => (
                                    <a
                                      key={ri}
                                      className="src-ref"
                                      href={rf.url}
                                      target="_blank"
                                      rel="noreferrer"
                                    >
                                      🔗 {rf.label}
                                    </a>
                                  ))}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
                {m.meta && (
                  <div className="msg-meta">{formatMeta(m.meta)}</div>
                )}
                {m.showSuggestions && (
                  <div className="suggestions">
                    {SUGGESTIONS.map((q) => (
                      <button key={q} onClick={() => send(q)}>
                        {q}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <span className="bubble-time">{m.time}</span>
            </div>
          )
        )}

        {loading && (
          <div className="row bot">
            <div className="bot-avatar">🏛️</div>
            <div className="msg-col">
              <div className="sender">해설사</div>
              <div className="bubble bot" style={{ padding: 0 }}>
                <div className="typing">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {recommend.items && recommend.items.length > 0 && (
        <div className="recommend-strip">
          <span className="rec-label">🎯 {recommend.category} 추천</span>
          {recommend.items.map((it) => (
            <button
              key={it.name}
              className="rec-chip"
              onClick={() => send(`${it.name}에 대해 알려줘`)}
              disabled={loading}
            >
              {it.name}
            </button>
          ))}
        </div>
      )}

      <div className="input-bar">
        <textarea
          rows={1}
          placeholder="궁금한 국가유산을 물어보세요"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
        />
        <button onClick={() => send()} disabled={loading || !input.trim()}>
          전송
        </button>
      </div>
    </div>
  );
}
