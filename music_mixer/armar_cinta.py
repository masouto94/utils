#!/usr/bin/env python3
"""
armar_cinta.py - Une varias pistas de audio en un unico archivo continuo,
con silencio entre ellas, pensado para grabar a cassette de una sola pasada.

Requiere: pip install soundfile numpy

Uso basico:
    python3 armar_cinta.py /ruta/a/la/carpeta

Ejemplos:
    # 3 segundos entre temas (por defecto), salida WAV
    python3 armar_cinta.py ./Grassland_Rock

    # 10 segundos de silencio al principio, para no contar el leader a mano
    python3 armar_cinta.py ./Grassland_Rock --lead-in 10

    # Mezclado a mono, que es como lo va a grabar el equipo igual
    python3 armar_cinta.py ./Grassland_Rock --mono

    # Ver el orden y las duraciones sin escribir nada
    python3 armar_cinta.py ./Grassland_Rock --dry-run
"""

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

EXTENSIONES = {".flac", ".wav", ".aif", ".aiff", ".ogg"}


def clave_natural(path: Path):
    """Ordena '2' antes que '10', a diferencia del orden alfabetico."""
    partes = re.split(r"(\d+)", path.name.lower())
    return [int(p) if p.isdigit() else p for p in partes]


def mmss(segundos: float) -> str:
    m, s = divmod(int(round(segundos)), 60)
    return f"{m}:{s:02d}"


def buscar_pistas(
    carpeta: Path, archivo_orden: Path | None, excluir: Path | None = None
):
    if archivo_orden:
        nombres = [
            linea.strip()
            for linea in archivo_orden.read_text(encoding="utf-8").splitlines()
            if linea.strip() and not linea.lstrip().startswith("#")
        ]
        pistas = []
        for nombre in nombres:
            p = carpeta / nombre
            if not p.exists():
                sys.exit(f"ERROR: no encuentro '{nombre}' en {carpeta}")
            pistas.append(p)
        return pistas

    excluidos = set()
    if excluir is not None:
        try:
            excluidos.add(excluir.resolve())
        except OSError:
            pass

    pistas = [
        p
        for p in carpeta.iterdir()
        if p.is_file()
        and p.suffix.lower() in EXTENSIONES
        and p.resolve() not in excluidos
    ]
    if not pistas:
        sys.exit(f"ERROR: no hay archivos de audio en {carpeta}")
    return sorted(pistas, key=clave_natural)


def main():
    ap = argparse.ArgumentParser(
        description="Une pistas de audio con silencio entre medio, para grabar a cassette.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("carpeta", type=Path, help="Carpeta con las pistas")
    ap.add_argument(
        "-o",
        "--salida",
        type=Path,
        default=None,
        help="Archivo de salida (por defecto: cinta.wav en la carpeta)",
    )
    ap.add_argument(
        "-g",
        "--gap",
        type=float,
        default=3.0,
        help="Segundos de silencio entre pistas (default: 3)",
    )
    ap.add_argument(
        "--lead-in",
        type=float,
        default=0.0,
        help="Segundos de silencio al principio, para cubrir el leader (default: 0)",
    )
    ap.add_argument(
        "--tail",
        type=float,
        default=2.0,
        help="Segundos de silencio al final (default: 2)",
    )
    ap.add_argument(
        "--mono", action="store_true", help="Mezclar a mono (promedio de canales)"
    )
    ap.add_argument(
        "--orden",
        type=Path,
        default=None,
        help="Archivo de texto con los nombres en el orden deseado, uno por linea",
    )
    ap.add_argument(
        "--minutos-lado",
        type=float,
        default=45.0,
        help="Minutos disponibles en el lado del cassette, para avisar (default: 45)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo mostrar el plan, sin escribir el archivo",
    )
    args = ap.parse_args()

    if not args.carpeta.is_dir():
        sys.exit(f"ERROR: '{args.carpeta}' no es una carpeta")

    salida = args.salida or (args.carpeta / "cinta.wav")
    pistas = buscar_pistas(args.carpeta, args.orden, excluir=salida)

    # --- Primera pasada: leer cabeceras y validar ---
    infos = []
    for p in pistas:
        try:
            info = sf.info(p)
        except Exception as e:
            sys.exit(f"ERROR al leer '{p.name}': {e}")
        infos.append(info)

    sr = infos[0].samplerate
    distintos = {i.samplerate for i in infos}
    if len(distintos) > 1:
        print(
            "ERROR: las pistas no comparten sample rate. Encontrados:",
            sorted(distintos),
        )
        for p, i in zip(pistas, infos):
            print(f"  {i.samplerate:>6} Hz  {p.name}")
        sys.exit("Convertilas todas al mismo sample rate antes de continuar.")

    canales = 1 if args.mono else infos[0].channels
    if not args.mono and len({i.channels for i in infos}) > 1:
        sys.exit(
            "ERROR: las pistas tienen distinta cantidad de canales. Usa --mono para unificarlas."
        )

    # --- Mostrar el plan ---
    print(f"\nCarpeta : {args.carpeta}")
    print(f"Formato : {sr} Hz, {canales} canal{'es' if canales > 1 else ''}\n")

    total = args.lead_in
    for n, (p, info) in enumerate(zip(pistas, infos), start=1):
        dur = info.frames / info.samplerate
        if n > 1:
            total += args.gap
        total += dur
        print(f"  {n:2d}. [{mmss(dur)}]  {p.name}")
    total += args.tail

    n_gaps = max(len(pistas) - 1, 0)
    print(f"\n  Pistas          : {len(pistas)}")
    print(
        f"  Audio           : {mmss(total - args.lead_in - args.tail - n_gaps * args.gap)}"
    )
    print(
        f"  Silencios       : {mmss(args.lead_in + args.tail + n_gaps * args.gap)}"
        f"  ({args.lead_in:g}s inicio + {n_gaps}x{args.gap:g}s + {args.tail:g}s final)"
    )
    print(f"  TOTAL           : {mmss(total)}")

    limite = args.minutos_lado * 60
    if total > limite:
        print(
            f"\n  *** NO ENTRA: excede por {mmss(total - limite)} "
            f"un lado de {args.minutos_lado:g} min ***"
        )
    else:
        print(
            f"  Margen en cinta : {mmss(limite - total)} sobre {args.minutos_lado:g} min"
        )

    if args.dry_run:
        print("\n(dry-run: no se escribio nada)\n")
        return

    # --- Segunda pasada: leer audio y concatenar ---
    print(f"\nEscribiendo {salida} ...")

    def silencio(seg):
        return np.zeros((int(round(seg * sr)), canales), dtype=np.float32)

    trozos = []
    if args.lead_in > 0:
        trozos.append(silencio(args.lead_in))

    pico = 0.0
    for n, p in enumerate(pistas):
        datos, _ = sf.read(p, dtype="float32", always_2d=True)
        if args.mono and datos.shape[1] > 1:
            datos = datos.mean(axis=1, keepdims=True)
        elif args.mono:
            pass  # ya es mono
        pico = max(pico, float(np.abs(datos).max()))
        if n > 0 and args.gap > 0:
            trozos.append(silencio(args.gap))
        trozos.append(datos)

    if args.tail > 0:
        trozos.append(silencio(args.tail))

    final = np.concatenate(trozos, axis=0)

    subtipo = (
        "PCM_16"
        if salida.suffix.lower() in {".wav", ".flac", ".aiff", ".aif"}
        else None
    )
    sf.write(salida, final, sr, subtype=subtipo)

    dur_real = len(final) / sr
    print(
        f"Listo: {mmss(dur_real)}  ({len(final)} muestras, {canales} canal"
        f"{'es' if canales > 1 else ''}, {sr} Hz)"
    )
    print(
        f"Pico maximo: {pico:.3f}"
        + ("  (hay clipping en el original)" if pico >= 0.999 else "")
    )
    print()


if __name__ == "__main__":
    main()
