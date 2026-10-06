"""
Camada de persistência — SQLAlchemy (SQLite) + JSON.
Armazena apólices extraídas e relatórios comparativos.
"""
from __future__ import annotations
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Column, DateTime, Integer, String, Text, create_engine, select
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from models.schemas import ApoliceExtraida, RelatorioComparativo

logger = logging.getLogger(__name__)

STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "storage"))
STORAGE_DIR.mkdir(exist_ok=True)
DB_PATH = STORAGE_DIR / "doshield.db"

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)


# ─── ORM Models ──────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class PolicyRecord(Base):
    __tablename__ = "policies"
    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=False)
    seguradora = Column(String(255))
    numero_apolice = Column(String(100))
    segurado = Column(String(255))
    vigencia_inicio = Column(String(50))
    vigencia_fim = Column(String(50))
    premio = Column(String(100))
    limite_global = Column(String(100))
    json_data = Column(Text, nullable=False)  # ApoliceExtraida serializada
    created_at = Column(DateTime, default=datetime.utcnow)


class ComparisonRecord(Base):
    __tablename__ = "comparisons"
    id = Column(Integer, primary_key=True, autoincrement=True)
    policy_a_id = Column(Integer)
    policy_b_id = Column(Integer)
    apolice_a = Column(String(255))
    apolice_b = Column(String(255))
    json_data = Column(Text, nullable=False)  # RelatorioComparativo serializado
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(engine)


# ─── Operações de Apólice ────────────────────────────────────────────────────

def save_policy(apolice: ApoliceExtraida) -> int:
    """Persiste uma apólice extraída. Retorna o ID gerado."""
    with SessionLocal() as session:
        record = PolicyRecord(
            filename=apolice.nome_arquivo or "desconhecido",
            seguradora=apolice.dados_apolice.seguradora,
            numero_apolice=apolice.dados_apolice.numero_apolice,
            segurado=apolice.segurado.nome_segurado,
            vigencia_inicio=apolice.dados_apolice.vigencia_inicio,
            vigencia_fim=apolice.dados_apolice.vigencia_fim,
            premio=apolice.dados_apolice.premio,
            limite_global=apolice.dados_apolice.limite_global,
            json_data=apolice.model_dump_json(exclude={"texto_bruto"}),
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        logger.info(f"Apólice salva: ID={record.id}, arquivo='{apolice.nome_arquivo}'")
        return record.id


def load_policy(policy_id: int) -> Optional[ApoliceExtraida]:
    """Carrega uma apólice pelo ID."""
    with SessionLocal() as session:
        record = session.get(PolicyRecord, policy_id)
        if not record:
            return None
        return ApoliceExtraida.model_validate_json(record.json_data)


def list_policies() -> list[dict]:
    """Retorna lista resumida de todas as apólices salvas."""
    with SessionLocal() as session:
        records = session.execute(select(PolicyRecord).order_by(PolicyRecord.created_at.desc())).scalars().all()
        return [
            {
                "id": r.id,
                "filename": r.filename,
                "seguradora": r.seguradora or "N/D",
                "numero_apolice": r.numero_apolice or "N/D",
                "segurado": r.segurado or "N/D",
                "vigencia": f"{r.vigencia_inicio or '?'} - {r.vigencia_fim or '?'}",
                "limite_global": r.limite_global or "N/D",
                "created_at": r.created_at.strftime("%d/%m/%Y %H:%M") if r.created_at else "",
            }
            for r in records
        ]


def delete_policy(policy_id: int) -> bool:
    """Remove uma apólice pelo ID."""
    with SessionLocal() as session:
        record = session.get(PolicyRecord, policy_id)
        if not record:
            return False
        session.delete(record)
        session.commit()
        return True


# ─── Operações de Comparação ─────────────────────────────────────────────────

def save_comparison(
    relatorio: RelatorioComparativo,
    policy_a_id: Optional[int] = None,
    policy_b_id: Optional[int] = None,
) -> int:
    """Persiste um relatório comparativo."""
    with SessionLocal() as session:
        record = ComparisonRecord(
            policy_a_id=policy_a_id,
            policy_b_id=policy_b_id,
            apolice_a=relatorio.apolice_a,
            apolice_b=relatorio.apolice_b,
            json_data=relatorio.model_dump_json(),
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        logger.info(f"Comparação salva: ID={record.id}")
        return record.id


def load_comparison(comparison_id: int) -> Optional[RelatorioComparativo]:
    """Carrega um relatório comparativo pelo ID."""
    with SessionLocal() as session:
        record = session.get(ComparisonRecord, comparison_id)
        if not record:
            return None
        return RelatorioComparativo.model_validate_json(record.json_data)


def list_comparisons() -> list[dict]:
    """Retorna lista de comparações salvas."""
    with SessionLocal() as session:
        records = session.execute(
            select(ComparisonRecord).order_by(ComparisonRecord.created_at.desc())
        ).scalars().all()
        return [
            {
                "id": r.id,
                "apolice_a": r.apolice_a,
                "apolice_b": r.apolice_b,
                "created_at": r.created_at.strftime("%d/%m/%Y %H:%M") if r.created_at else "",
            }
            for r in records
        ]
