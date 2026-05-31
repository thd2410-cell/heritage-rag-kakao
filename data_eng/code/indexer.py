"""
indexer.py — 국가유산 데이터를 ChromaDB에 인덱싱
한 번만 실행하면 됨. 데이터 추가 시 다시 실행.

실행: python rag/indexer.py
"""
import json
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from sentence_transformers import SentenceTransformer


# ─────────────────────────────────────────────────────────
# 1. 임베딩 모델 래퍼
#    LangChain이 요구하는 인터페이스에 맞춰 KoSimCSE 감싸기
# ─────────────────────────────────────────────────────────
class KoSimCSEEmbeddings(Embeddings):
    def __init__(self):
        print("임베딩 모델 로딩 중... (처음 한 번만 다운로드)")
        self.model = SentenceTransformer("BM-K/KoSimCSE-roberta")

    def embed_documents(self, texts):
        # 진행률 표시 + 배치 크기 (CPU 적정)
        return self.model.encode(
            texts,
            show_progress_bar=True,
            batch_size=64,
        ).tolist()

    def embed_query(self, text):
        return self.model.encode([text])[0].tolist()


def main():
    base = Path(__file__).parent.parent

    # ─────────────────────────────────────────────────────
    # 2. 데이터 로드
    # ─────────────────────────────────────────────────────
    with open(base / "data" / "heritages.json", "r", encoding="utf-8") as f:
        heritages = json.load(f)

    print(f"데이터 {len(heritages)}개 로드됨")

    # ─────────────────────────────────────────────────────
    # 3. 텍스트 + 메타데이터 준비
    #    LLM이 답할 때 활용할 수 있는 정보를 한 문서에 다 모음
    # ─────────────────────────────────────────────────────
    documents = []
    for h in heritages:
        # 새 스키마: parent_name, category 추가, location은 옛 데이터에만 있음
        parent_line = f"소속: {h['parent_name']}\n" if h.get("parent_name") else ""
        category_line = f"분류: {h['category']}\n" if h.get("category") else ""
        location_line = f"위치: {h['location']}\n" if h.get("location") else ""

        full_text = (
            f"유산명: {h['name']}\n"
            f"{parent_line}"
            f"지역: {h['region']}\n"
            f"시대: {h['era']}\n"
            f"{category_line}"
            f"{location_line}"
            f"설명: {h['description']}"
        )
        documents.append(
            Document(
                page_content=full_text,
                metadata={
                    "heritage_id": h["id"],
                    "name": h["name"],
                    "region": h["region"],
                    "era": h.get("era", ""),
                    "category": h.get("category", ""),
                    "parent_name": h.get("parent_name", ""),
                },
            )
        )

    # ─────────────────────────────────────────────────────
    # 4. Chunk 분할
    #    chunk_size: 한 조각의 최대 글자 수
    #    chunk_overlap: 앞뒤 겹치는 글자 수 (문맥 유지용)
    # ─────────────────────────────────────────────────────
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=400,
        chunk_overlap=50,
        separators=["\n\n", "\n", ".", " "],
    )
    chunks = splitter.split_documents(documents)
    print(f"chunk {len(chunks)}개 생성됨")

    # ─────────────────────────────────────────────────────
    # 5. ChromaDB 저장
    #    persist_directory: 디스크에 저장될 경로
    # ─────────────────────────────────────────────────────
    persist_dir = str(base / "chroma_db")
    Chroma.from_documents(
        documents=chunks,
        embedding=KoSimCSEEmbeddings(),
        persist_directory=persist_dir,
        collection_name="heritages",
    )

    print(f"ChromaDB 저장 완료! → {persist_dir}")


if __name__ == "__main__":
    main()
