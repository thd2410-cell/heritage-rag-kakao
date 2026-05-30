export type Audience =
  | "general"
  | "child"
  | "expert"
  | "elderly"
  | "visually_impaired"
  | "hearing_impaired";

export type ChatResponse = {
  answer: string;
  normalized_query: string;
  detected_language: string;
  intent: string;
  entities: Array<{
    heritage_id: string;
    official_name_ko: string;
    matched_alias: string;
    match_type: string;
    confidence: number;
    confirmation_required: boolean;
  }>;
  citations: Array<{
    document_id: string;
    chunk_id: string;
    title: string;
    source_type: string;
    source_trust_level: string;
  }>;
  images: Array<{
    image_id: string;
    heritage_id: string;
    title: string;
    image_url: string;
    thumbnail_url: string | null;
    caption: string;
    license_type: string;
    source_uri: string | null;
    source_trust_level: string;
  }>;
  confidence: number;
  follow_up_questions: string[];
  route: null | {
    route_title: string;
    estimated_duration_minutes: number;
    stops: Array<{
      order: number;
      heritage_id: string | null;
      name: string;
      description: string;
      estimated_stay_minutes: number;
      accessibility_note: string;
    }>;
    warnings: string[];
  };
  safety_flags: string[];
  latency_ms: number;
};

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8080";

export async function sendChat(query: string, audience: Audience): Promise<ChatResponse> {
  const response = await fetch(`${backendUrl}/api/chat`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      query,
      language: "auto",
      audience,
      options: {include_citations: true, stream: false, tts_ready: false}
    })
  });
  if (!response.ok) {
    throw new Error(`Backend request failed: ${response.status}`);
  }
  return response.json();
}
