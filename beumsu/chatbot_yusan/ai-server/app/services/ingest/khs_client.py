from __future__ import annotations

import time
from typing import Any
from xml.etree import ElementTree

import httpx


class KhsOpenApiClient:
    """Small adapter for KHS public heritage OpenAPI endpoints.

    The KHS image API is used as a source of image metadata. Retrieved content is
    treated as data for ingestion, never as prompt instructions.
    """

    LIST_URL = "https://www.khs.go.kr/cha/SearchKindOpenapiList.do"
    DETAIL_URL = "https://www.khs.go.kr/cha/SearchKindOpenapiDt.do"
    IMAGE_URL = "https://www.khs.go.kr/cha/SearchImageOpenapi.do"

    def __init__(self, timeout: float = 20.0):
        self.timeout = timeout

    def search_list(
        self,
        *,
        ccba_ctcd: str,
        page_unit: int = 100,
        page_index: int = 1,
        ccba_kdcd: str | None = None,
        ccba_cncl: str = "N",
    ) -> dict[str, Any]:
        params = {
            "ccbaCtcd": ccba_ctcd,
            "pageUnit": str(page_unit),
            "pageIndex": str(page_index),
            "ccbaCncl": ccba_cncl,
        }
        if ccba_kdcd:
            params["ccbaKdcd"] = ccba_kdcd
        xml_text = self._get_text(self.LIST_URL, params)
        return self.parse_list_xml(xml_text)

    def get_detail(self, ccba_kdcd: str, ccba_asno: str, ccba_ctcd: str) -> dict[str, Any]:
        params = {
            "ccbaKdcd": ccba_kdcd,
            "ccbaAsno": ccba_asno,
            "ccbaCtcd": ccba_ctcd,
        }
        xml_text = self._get_text(self.DETAIL_URL, params)
        return self.parse_detail_xml(xml_text)

    def search_images(self, ccba_kdcd: str, ccba_asno: str, ccba_ctcd: str) -> list[dict[str, Any]]:
        params = {
            "ccbaKdcd": ccba_kdcd,
            "ccbaAsno": ccba_asno,
            "ccbaCtcd": ccba_ctcd,
        }
        return self.parse_image_xml(self._get_text(self.IMAGE_URL, params))

    def build_dataset_from_khs(
        self,
        *,
        ccba_ctcds: list[str],
        page_unit: int = 100,
        max_pages: int = 1,
        limit: int | None = None,
        ccba_kdcd: str | None = None,
        include_images: bool = True,
    ) -> dict[str, list[dict[str, Any]]]:
        entities: list[dict[str, Any]] = []
        aliases: list[dict[str, Any]] = []
        documents: list[dict[str, Any]] = []
        images: list[dict[str, Any]] = []
        fetched = 0

        for ctcd in ccba_ctcds:
            for page_index in range(1, max_pages + 1):
                listed = self.search_list(
                    ccba_ctcd=ctcd,
                    page_unit=page_unit,
                    page_index=page_index,
                    ccba_kdcd=ccba_kdcd,
                )
                items = listed["items"]
                if not items:
                    break
                for item in items:
                    if limit is not None and fetched >= limit:
                        return {
                            "entities": entities,
                            "aliases": aliases,
                            "documents": documents,
                            "relations": [],
                            "images": images,
                        }
                    kdcd = item.get("ccbaKdcd", "")
                    asno = item.get("ccbaAsno", "")
                    item_ctcd = item.get("ccbaCtcd", ctcd)
                    if not kdcd or not asno or not item_ctcd:
                        continue

                    detail = self.get_detail(kdcd, asno, item_ctcd)
                    row = {**item, **detail}
                    entity_id = self.entity_id(row)
                    name_ko = self._first(row, "ccbaMnm1")
                    hanja = self._first(row, "ccbaMnm2")
                    location = self._first(row, "ccbaLcad", "ccbaCtcdNm", "ccsiName")
                    description = self._first(row, "content", "ccceName")

                    entities.append(
                        {
                            "id": entity_id,
                            "official_name_ko": name_ko,
                            "official_name_en": "",
                            "official_name_zh": hanja,
                            "official_name_ja": hanja,
                            "hanja_name": hanja,
                            "category": self._first(row, "ccmaName", "gcodeName"),
                            "period": self._first(row, "ccceName", "ccbaPcd1"),
                            "location_name": location,
                            "latitude": self._zero_to_empty(self._first(row, "latitude")),
                            "longitude": self._zero_to_empty(self._first(row, "longitude")),
                            "description": description,
                            "source_trust_level": "S1",
                        }
                    )
                    aliases.extend(self._aliases(entity_id, name_ko, hanja))
                    documents.append(
                        {
                            "id": f"khs-doc-{entity_id}",
                            "heritage_entity_id": entity_id,
                            "title": f"{name_ko} 국가유산청 공식 상세",
                            "source_type": "official_db",
                            "source_trust_level": "S1",
                            "language": "ko",
                            "original_uri": self.DETAIL_URL,
                            "content": self._document_content(row),
                            "metadata": row,
                        }
                    )
                    if include_images:
                        for image in self.search_images(kdcd, asno, item_ctcd):
                            images.append({**image, "heritage_entity_id": entity_id})
                    fetched += 1
        return {
            "entities": entities,
            "aliases": aliases,
            "documents": documents,
            "relations": [],
            "images": images,
        }

    def build_dataset_from_list_items(
        self,
        items: list[dict[str, str]],
        *,
        default_ctcd: str,
        include_images: bool = False,
        detail_delay_seconds: float = 0.0,
    ) -> dict[str, list[dict[str, Any]]]:
        entities: list[dict[str, Any]] = []
        aliases: list[dict[str, Any]] = []
        documents: list[dict[str, Any]] = []
        images: list[dict[str, Any]] = []

        for item in items:
            kdcd = item.get("ccbaKdcd", "")
            asno = item.get("ccbaAsno", "")
            item_ctcd = item.get("ccbaCtcd", default_ctcd)
            if not kdcd or not asno or not item_ctcd:
                continue
            detail = self.get_detail(kdcd, asno, item_ctcd)
            if detail_delay_seconds > 0:
                time.sleep(detail_delay_seconds)
            row = {**item, **detail}
            entity_id = self.entity_id(row)
            name_ko = self._first(row, "ccbaMnm1")
            hanja = self._first(row, "ccbaMnm2")
            location = self._first(row, "ccbaLcad", "ccbaCtcdNm", "ccsiName")
            description = self._first(row, "content", "ccceName")

            entities.append(
                {
                    "id": entity_id,
                    "official_name_ko": name_ko,
                    "official_name_en": "",
                    "official_name_zh": hanja,
                    "official_name_ja": hanja,
                    "hanja_name": hanja,
                    "category": self._first(row, "ccmaName", "gcodeName"),
                    "period": self._first(row, "ccceName", "ccbaPcd1"),
                    "location_name": location,
                    "latitude": self._zero_to_empty(self._first(row, "latitude")),
                    "longitude": self._zero_to_empty(self._first(row, "longitude")),
                    "description": description,
                    "source_trust_level": "S1",
                }
            )
            aliases.extend(self._aliases(entity_id, name_ko, hanja))
            documents.append(
                {
                    "id": f"khs-doc-{entity_id}",
                    "heritage_entity_id": entity_id,
                    "title": f"{name_ko} 국가유산청 공식 상세",
                    "source_type": "official_db",
                    "source_trust_level": "S1",
                    "language": "ko",
                    "original_uri": self.DETAIL_URL,
                    "content": self._document_content(row),
                    "metadata": row,
                }
            )
            if include_images:
                for image in self.search_images(kdcd, asno, item_ctcd):
                    images.append({**image, "heritage_entity_id": entity_id})

        return {
            "entities": entities,
            "aliases": aliases,
            "documents": documents,
            "relations": [],
            "images": images,
        }

    def parse_list_xml(self, xml_text: str) -> dict[str, Any]:
        root = ElementTree.fromstring(xml_text)
        items = [self._element_dict(item) for item in root.findall(".//item")]
        return {
            "total_count": self._int_text(root, "totalCnt"),
            "page_unit": self._int_text(root, "pageUnit"),
            "page_index": self._int_text(root, "pageIndex"),
            "items": items,
        }

    def parse_detail_xml(self, xml_text: str) -> dict[str, Any]:
        root = ElementTree.fromstring(xml_text)
        item = root.find(".//item")
        if item is not None:
            return self._element_dict(item)
        return self._element_dict(root)

    def parse_image_xml(self, xml_text: str) -> list[dict[str, Any]]:
        root = ElementTree.fromstring(xml_text)
        items = root.findall(".//item")
        if not items and root.tag.lower() == "item":
            items = [root]

        rows: list[dict[str, Any]] = []
        for item in items:
            raw = self._element_dict(item)
            image_url = self._first(raw, "imageUrl", "image_url", "ccimUrl", "snpImageUrl", "imageNuri")
            if not image_url or not image_url.startswith(("http://", "https://")):
                continue
            rows.append(
                {
                    "title": self._first(raw, "ccimNm", "ccbaMnm1", "title", "imageTitle"),
                    "image_url": image_url,
                    "thumbnail_url": self._first(raw, "thumbUrl", "thumbnailUrl", "imageThumbUrl"),
                    "caption": self._first(raw, "ccimDesc", "content", "caption", "imageDesc"),
                    "license_type": self._first(raw, "license", "licenseType", "imageNuri"),
                    "source_uri": self.IMAGE_URL,
                    "source_type": "official_image",
                    "source_trust_level": "S1",
                    "metadata": raw,
                }
            )
        return rows

    def _first(self, row: dict[str, str], *keys: str) -> str:
        for key in keys:
            value = row.get(key)
            if value:
                return value
        return ""

    def _get_text(self, url: str, params: dict[str, str]) -> str:
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            if not response.encoding:
                response.encoding = "utf-8"
            return response.text

    def _element_dict(self, element: ElementTree.Element) -> dict[str, str]:
        return {child.tag: (child.text or "").strip() for child in list(element)}

    def _int_text(self, root: ElementTree.Element, tag: str) -> int:
        found = root.find(f".//{tag}")
        if found is None or not found.text:
            return 0
        try:
            return int(found.text.strip())
        except ValueError:
            return 0

    def _zero_to_empty(self, value: str) -> str:
        return "" if value in {"", "0", "0.0", "0.00"} else value

    def entity_id(self, row: dict[str, str]) -> str:
        kdcd = self._first(row, "ccbaKdcd")
        ctcd = self._first(row, "ccbaCtcd")
        asno = self._first(row, "ccbaAsno")
        return f"khs-{kdcd}-{ctcd}-{asno}"

    def _aliases(self, entity_id: str, name_ko: str, hanja: str) -> list[dict[str, Any]]:
        rows = []
        if name_ko:
            rows.append(
                {
                    "heritage_entity_id": entity_id,
                    "alias": name_ko,
                    "language": "ko",
                    "alias_type": "official",
                    "confidence_prior": 1.0,
                }
            )
            short_name = self._short_korean_name(name_ko)
            if short_name and short_name != name_ko:
                rows.append(
                    {
                        "heritage_entity_id": entity_id,
                        "alias": short_name,
                        "language": "ko",
                        "alias_type": "local",
                        "confidence_prior": 0.98,
                    }
                )
        if hanja and hanja != name_ko:
            rows.append(
                {
                    "heritage_entity_id": entity_id,
                    "alias": hanja,
                    "language": "zh",
                    "alias_type": "hanja",
                    "confidence_prior": 1.0,
                }
            )
        return rows

    def _document_content(self, row: dict[str, str]) -> str:
        fields = [
            ("국가유산명", self._first(row, "ccbaMnm1")),
            ("한자명", self._first(row, "ccbaMnm2")),
            ("종목", self._first(row, "ccmaName", "gcodeName")),
            ("시대", self._first(row, "ccceName", "ccbaPcd1")),
            ("소재지", self._first(row, "ccbaLcad", "ccbaCtcdNm", "ccsiName")),
            ("지정일", self._first(row, "ccbaAsdt")),
            ("관리자", self._first(row, "ccbaAdmin")),
            ("수량/면적", self._first(row, "ccbaQuan")),
            ("설명", self._first(row, "content")),
        ]
        return "\n".join(f"{label}: {value}" for label, value in fields if value)

    def _short_korean_name(self, name: str) -> str:
        prefixes = (
            "서울 ",
            "부산 ",
            "대구 ",
            "인천 ",
            "광주 ",
            "대전 ",
            "울산 ",
            "세종 ",
            "경기 ",
            "강원 ",
            "충북 ",
            "충남 ",
            "전북 ",
            "전남 ",
            "경북 ",
            "경남 ",
            "제주 ",
        )
        for prefix in prefixes:
            if name.startswith(prefix):
                return name[len(prefix) :].strip()
        return ""
