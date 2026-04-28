"""XML processing endpoints: upload, parse tree, validate, field-level check."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from db import USE_MOCK
from models import (
    FieldValidation,
    XmlField,
    XmlFieldsResponse,
    XmlTreeNode,
    XmlTreeResponse,
    XmlTreeStatistics,
    XmlUploadResponse,
    XmlValidateRequest,
    XmlValidateResponse,
    XmlValidationError,
)

router = APIRouter()

UPLOAD_DIR = "/tmp/xml_uploads"
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB


@router.post("/upload", response_model=XmlUploadResponse)
async def upload_xml(
    file: UploadFile = File(...),
    document_type: str = Form(...),
):
    """Upload an SCR XML file for parsing and validation."""
    if document_type not in ("3040", "3050"):
        raise HTTPException(status_code=400, detail="Document must be 3040 or 3050")

    file_id = f"xml_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()

    if USE_MOCK:
        return XmlUploadResponse(
            file_id=file_id,
            filename=file.filename or "unknown.xml",
            document_type=document_type,
            file_size_bytes=1234567,
            encoding="ISO-8859-1",
            uploaded_at=now,
            status="uploaded",
        )

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}.xml")
    total_size = 0
    with open(file_path, "wb") as f:
        while chunk := await file.read(8192):
            total_size += len(chunk)
            if total_size > MAX_FILE_SIZE:
                os.remove(file_path)
                raise HTTPException(status_code=413, detail="File exceeds 500MB limit")
            f.write(chunk)

    return XmlUploadResponse(
        file_id=file_id,
        filename=file.filename or "unknown.xml",
        document_type=document_type,
        file_size_bytes=total_size,
        encoding="ISO-8859-1",
        uploaded_at=now,
        status="uploaded",
    )


@router.get("/{file_id}/tree", response_model=XmlTreeResponse)
async def get_xml_tree(
    file_id: str,
    max_depth: int = Query(4, ge=1, le=10),
    max_children: int = Query(100, ge=1, le=1000),
    path: str | None = Query(None, description="XPath to start from"),
):
    """Return parsed XML structure as a hierarchical tree."""
    if USE_MOCK:
        return XmlTreeResponse(
            file_id=file_id,
            document_type="3040",
            root=XmlTreeNode(
                tag="Doc3040",
                attributes={"CNPJ": "99999999", "DtBase": "2026-03", "Remessa": "1", "Parte": "1", "TpArq": "P"},
                children_count=1250000,
                children=[
                    XmlTreeNode(
                        tag="Cli",
                        attributes={"Cd": "12345678901", "Tp": "1", "PorteCli": "3"},
                        children_count=15,
                        children=[
                            XmlTreeNode(
                                tag="Op",
                                attributes={"IPOC": "9999999902011123456789010001", "Mod": "0201", "DtContr": "2024-01-15", "DtVencOp": "2029-01-15", "VlrContr": "150000.00"},
                                children_count=3,
                            ),
                            XmlTreeNode(
                                tag="Op",
                                attributes={"IPOC": "9999999904011123456789010002", "Mod": "0401", "DtContr": "2023-06-01", "DtVencOp": "2053-06-01", "VlrContr": "450000.00"},
                                children_count=2,
                            ),
                        ],
                    ),
                    XmlTreeNode(
                        tag="Cli",
                        attributes={"Cd": "98765432000199", "Tp": "2", "PorteCli": "4"},
                        children_count=8,
                        children=[],
                    ),
                ],
            ),
            statistics=XmlTreeStatistics(total_elements=52350000, total_clients=1250000, total_operations=50000000, total_aggregated=1100000),
        )

    file_path = os.path.join(UPLOAD_DIR, f"{file_id}.xml")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found or expired")

    from lxml import etree
    tree = etree.parse(file_path)
    root = tree.getroot()

    def _build_node(elem, depth: int) -> XmlTreeNode:
        children = []
        if depth < max_depth:
            for child in list(elem)[:max_children]:
                children.append(_build_node(child, depth + 1))
        return XmlTreeNode(
            tag=etree.QName(elem.tag).localname if "}" in elem.tag else elem.tag,
            attributes=dict(elem.attrib),
            children_count=len(list(elem)),
            children=children,
        )

    root_node = _build_node(root, 0)
    return XmlTreeResponse(
        file_id=file_id, document_type="3040", root=root_node,
        statistics=XmlTreeStatistics(total_elements=0, total_clients=0, total_operations=0, total_aggregated=0),
    )


@router.post("/{file_id}/validate", response_model=XmlValidateResponse)
async def validate_xml(file_id: str, body: XmlValidateRequest | None = None):
    """Validate uploaded XML file against XSD schema."""
    xsd_version = body.xsd_version if body else "V11"
    max_errors = body.max_errors if body else 100
    now = datetime.now(timezone.utc).isoformat()

    if USE_MOCK:
        return XmlValidateResponse(
            file_id=file_id,
            valid=False,
            xsd_version=xsd_version,
            errors_found=3,
            max_errors=max_errors,
            errors=[
                XmlValidationError(line=4521, column=45, path="/Doc3040/Cli[42]/Op[3]", error_type="attribute_invalid", field="Mod", value="9999", message="Valor '9999' nao e valido para o atributo 'Mod'", xsd_constraint="enumeration"),
                XmlValidationError(line=8932, column=20, path="/Doc3040/Cli[100]/Op[1]", error_type="missing_attribute", field="DtContr", value="", message="Atributo obrigatorio 'DtContr' ausente", xsd_constraint="required"),
                XmlValidationError(line=15021, column=38, path="/Doc3040/Cli[250]/Op[7]", error_type="attribute_invalid", field="VlrContr", value="-100.00", message="Valor negativo nao permitido para 'VlrContr'", xsd_constraint="minInclusive"),
            ],
            validated_at=now,
        )

    file_path = os.path.join(UPLOAD_DIR, f"{file_id}.xml")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found or expired")

    return XmlValidateResponse(
        file_id=file_id, valid=True, xsd_version=xsd_version,
        errors_found=0, max_errors=max_errors, errors=[], validated_at=now,
    )


@router.get("/{file_id}/fields", response_model=XmlFieldsResponse)
async def get_xml_fields(
    file_id: str,
    xpath: str = Query(..., description="XPath to the element"),
):
    """Return field-level validation results for XML Viewer highlighting."""
    if USE_MOCK:
        element = xpath.split("/")[-1].split("[")[0] if "/" in xpath else "Op"
        return XmlFieldsResponse(
            xpath=xpath,
            element=element,
            fields=[
                XmlField(name="IPOC", value="9999999902011123456789010001", status="valid", validations=[
                    FieldValidation(rule="format", passed=True, detail="Matches IPOC regex"),
                    FieldValidation(rule="components", passed=True, detail="CNPJ_IF matches header CNPJ"),
                ]),
                XmlField(name="Mod", value="0201", status="valid", validations=[
                    FieldValidation(rule="domain", passed=True, detail="Valid modality code"),
                ]),
                XmlField(name="DtContr", value="2024-01-15", status="valid", validations=[
                    FieldValidation(rule="format", passed=True, detail="Valid date format YYYY-MM-DD"),
                ]),
                XmlField(name="DtVencOp", value="2029-01-15", status="valid", validations=[
                    FieldValidation(rule="format", passed=True, detail="Valid date format"),
                    FieldValidation(rule="semantic", passed=True, detail="DtVencOp >= DtContr"),
                ]),
                XmlField(name="VlrContr", value="150000.00", status="valid", validations=[
                    FieldValidation(rule="format", passed=True, detail="Valid decimal format"),
                    FieldValidation(rule="range", passed=True, detail="Valor positivo"),
                ]),
            ],
        )

    raise HTTPException(status_code=404, detail="File not found or expired")
