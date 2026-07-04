#!/usr/bin/env python3
"""Indexa el corpus en Supabase DESDE TU ORDENADOR (evita el OOM de Railway).

El indexado (cargar el modelo + embeber cientos de documentos) consume mucha RAM;
hacerlo en tu Mac y escribir los vectores directamente en Supabase deja a Railway
solo con la tarea ligera de responder preguntas. No hay que "subir" nada: los
vectores van a la tabla `kb_chunks` que Railway ya lee.

Uso:
    cp .env.example .env         # y rellena SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY
    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    python3 index_local.py        # incremental (solo lo nuevo)
    python3 index_local.py --all  # completo (reconstruye todo el índice)
"""
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).parent


def load_env(name: str = ".env") -> None:
    p = HERE / name
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        # las variables de entorno reales tienen prioridad sobre el .env
        os.environ.setdefault(k.strip(), v.strip())


def main() -> None:
    load_env()
    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        sys.exit("Faltan SUPABASE_URL y/o SUPABASE_SERVICE_ROLE_KEY (ponlos en .env o como variables de entorno).")

    sys.path.insert(0, str(HERE))
    from app import indexer  # importar DESPUÉS de cargar el entorno (config lo lee al importar)

    full = "--all" in sys.argv or "--todo" in sys.argv
    only = None
    for a in sys.argv:
        if a.startswith("--only="):
            only = [s.strip() for s in a.split("=", 1)[1].split(",") if s.strip()]
    scope = f"solo {', '.join(only)}" if only else ("COMPLETO" if full else "incremental")
    print(f"→ Indexando ({scope}). La 1ª vez descarga el modelo (~400 MB), paciencia.\n")
    report = indexer.run_index(full=full, only=only)
    print("\n✓ Indexado terminado.")
    print("  Documentos por fuente:", report.get("processed"))
    print("  Chunks nuevos/actualizados:", report.get("chunks"))
    print("  Sin cambios:", report.get("skipped_unchanged"))
    print("\nYa puedes preguntarle a Curro en la web: Railway lee estos vectores directamente.")


if __name__ == "__main__":
    main()
