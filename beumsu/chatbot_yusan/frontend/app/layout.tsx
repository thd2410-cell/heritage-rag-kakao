import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "국가유산 AI 해설 챗봇",
  description: "공식 근거 기반 국가유산 AI 해설 챗봇"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
