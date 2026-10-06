"""
Camada de persistência — SQLAlchemy sobre SQLite.

Guarda três coisas: a apólice estruturada (JSON), o texto de cada página (usado pela
consulta e para conferir as fontes) e os relatórios comparativos. A conexão é criada
sob demanda, o que permite apontar o banco para outro diretório (testes, deploy).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from models.schemas import ApoliceExtraida, RelatorioComparativo

logger = logging.getLogger(__name__)

# O schema mudou em relação à primeira versão (novas colunas e a tabela de páginas).
# Um nome de arquivo novo evita que um doshield.db antigo derrube o app com "no such column".
DB_FILENAME = "doshield_v2.db"


class Base(DeclarativeBase):
    pass


class PolicyRecord(Base):
    __tablename__ = "policies"
    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=False)
    tipo_documento = Column(String(40))
    seguradora = Column(String(255))
    numero_apolice = Column(String(100))
    segurado = Column(String(255))
    vigencia_inicio = Column(String(50))
    vigencia_fim = Column(String(50))
    premio = Column(String(100))
    limite_global = Column(String(100))
    total_paginas = Column(Integer)
    json_data = Column(Text, nullable=False)  # ApoliceExtraida sem o texto
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PolicyPage(Base):
    __tablename__ = "policy_pages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    policy_id = Column(Integer, ForeignKey("policies.id", ondelete="CASCADE"), index=True, nullable=False)
    page_number = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)


class ComparisonRecord(Base):
    __tablename__ = "comparisons"
    id = Column(Integer, primary_key=True, autoincrement=True)
    policy_ids = Column(String(255))  # lista JSON de IDs comparados
    titulo = Column(String(500))
    json_data = Column(Text, nullable=False)  # RelatorioComparativo
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


_engine = None
_session_factory = None


def configure_storage(directory: Optional[os.PathLike | str] = None) -> Path:
    """
    (Re)configura o banco. Sem argumento usa STORAGE_DIR ou ./storage.
    Retorna o caminho do arquivo SQLite.
    """
    global _engine, _session_factory
    base = Path(directory or os.getenv("STORAGE_DIR", "storage"))
    base.mkdir(parents=True, exist_ok=True)
    path = base / DB_FILENAME

    if _engine is not None:
        _engine.dispose()
    _engine = create_engine(f"sqlite:///{path}", echo=False)
    Base.metadata.create_all(_engine)
    _session_factory = sessionmaker(bind=_engine)
    return path


def _session():
    if _session_factory is None:
        configure_storage()
    return _session_factory()


# ─── Apólices ────────────────────────────────────────────────────────────────

def save_policy(apolice: ApoliceExtraida) -> int:
    """Persiste a apólice e o texto de cada página. Retorna o ID gerado."""
    with _session() as session:
        record = PolicyRecord(
            filename=apolice.nome_arquivo or "desconhecido",
            tipo_documento=apolice.tipo_documento,
            seguradora=apolice.dados_apolice.seguradora,
            numero_apolice=apolice.dados_apolice.numero_apolice,
            segurado=apolice.segurado.nome_segurado,
            vigencia_inicio=apolice.dados_apolice.vigencia_inicio,
            vigencia_fim=apolice.dados_apolice.vigencia_fim,
            premio=apolice.dados_apolice.premio,
            limite_global=apolice.dados_apolice.limite_global,
            total_paginas=apolice.total_paginas or len(apolice.paginas) or None,
            json_data=apolice.model_dump_json(exclude={"texto_bruto", "paginas"}),
        )
        session.add(record)
        session.flush()
        session.add_all(
            PolicyPage(policy_id=record.id, page_number=n, text=texto)
            for n, texto in enumerate(apolice.paginas, start=1)
        )
        session.commit()
        logger.info("Apólice salva: ID=%s, arquivo='%s'", record.id, apolice.nome_arquivo)
        return record.id


def load_policy(policy_id: int, with_pages: bool = False) -> Optional[ApoliceExtraida]:
    """Carrega uma apólice; com `with_pages=True` inclui o texto de cada página."""
    with _session() as session:
        record = session.get(PolicyRecord, policy_id)
        if not record:
            return None
        apolice = ApoliceExtraida.model_validate_json(record.json_data)
        if with_pages:
            apolice.paginas = load_pages(policy_id)
        return apolice


def load_pages(policy_id: int) -> list[str]:
    """Texto de cada página da apólice, em ordem."""
    with _session() as session:
        rows = session.execute(
            select(PolicyPage.text).where(PolicyPage.policy_id == policy_id).order_by(PolicyPage.page_number)
        ).scalars().all()
        return list(rows)


def list_policies() -> list[dict]:
    """Lista resumida das apólices salvas (mais recentes primeiro)."""
    with _session() as session:
        records = session.execute(select(PolicyRecord).order_by(PolicyRecord.created_at.desc())).scalars().all()
        return [
            {
                "id": r.id,
                "filename": r.filename,
                "tipo_documento": r.tipo_documento or "N/D",
                "seguradora": r.seguradora or "N/D",
                "numero_apolice": r.numero_apolice or "N/D",
                "segurado": r.segurado or "N/D",
                "vigencia": f"{r.vigencia_inicio or '?'} - {r.vigencia_fim or '?'}",
                "limite_global": r.limite_global or "N/D",
                "total_paginas": r.total_paginas or 0,
                "created_at": r.created_at.strftime("%d/%m/%Y %H:%M") if r.created_at else "",
            }
            for r in records
        ]


def delete_policy(policy_id: int) -> bool:
    """Remove uma apólice e suas páginas."""
    with _session() as session:
        record = session.get(PolicyRecord, policy_id)
        if not record:
            return False
        session.execute(delete(PolicyPage).where(PolicyPage.policy_id == policy_id))
        session.delete(record)
        session.commit()
        return True


# ─── Comparações ─────────────────────────────────────────────────────────────

def save_comparison(relatorio: RelatorioComparativo, policy_ids: Optional[Sequence[int]] = None) -> int:
    """Persiste um relatório comparativo."""
    with _session() as session:
        record = ComparisonRecord(
            policy_ids=json.dumps(list(policy_ids or [])),
            titulo=" × ".join(relatorio.apolices),
            json_data=relatorio.model_dump_json(),
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        logger.info("Comparação salva: ID=%s", record.id)
        return record.id


def load_comparison(comparison_id: int) -> Optional[RelatorioComparativo]:
    with _session() as session:
        record = session.get(ComparisonRecord, comparison_id)
        return RelatorioComparativo.model_validate_json(record.json_data) if record else None


def list_comparisons() -> list[dict]:
    with _session() as session:
        records = session.execute(select(ComparisonRecord).order_by(ComparisonRecord.created_at.desc())).scalars().all()
        return [
            {
                "id": r.id,
                "titulo": r.titulo,
                "created_at": r.created_at.strftime("%d/%m/%Y %H:%M") if r.created_at else "",
            }
            for r in records
        ]
