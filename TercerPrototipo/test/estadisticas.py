"""Estadísticas y tablas compartidas por las herramientas de medición."""

import statistics


def percentil(valores, p):
    """Percentil con interpolación lineal (p entre 0 y 100)."""

    datos = sorted(valores)
    if not datos:
        return None
    if len(datos) == 1:
        return datos[0]
    posicion = (len(datos) - 1) * p / 100
    abajo = int(posicion)
    arriba = min(abajo + 1, len(datos) - 1)
    fraccion = posicion - abajo
    return datos[abajo] + (datos[arriba] - datos[abajo]) * fraccion


def resumir(valores):
    """Devuelve n, media, mediana, p95, mínimo y máximo de una lista."""

    valores = [float(v) for v in valores]
    if not valores:
        return None
    return {
        "n": len(valores),
        "media": statistics.fmean(valores),
        "mediana": statistics.median(valores),
        "p95": percentil(valores, 95),
        "min": min(valores),
        "max": max(valores),
        "desvio": statistics.stdev(valores) if len(valores) > 1 else 0.0,
    }


ENCABEZADO = ("Etapa", "n", "Media", "Mediana", "P95", "Mín", "Máx")


def filas_tabla(resumenes):
    """resumenes: lista de (nombre, resumen). Devuelve filas de texto en ms."""

    filas = []
    for nombre, r in resumenes:
        if r is None:
            continue
        filas.append(
            (
                nombre,
                str(r["n"]),
                f"{r['media']:.1f}",
                f"{r['mediana']:.1f}",
                f"{r['p95']:.1f}",
                f"{r['min']:.1f}",
                f"{r['max']:.1f}",
            )
        )
    return filas


def tabla_texto(resumenes, titulo=None):
    """Tabla alineada para la terminal (valores en milisegundos)."""

    filas = filas_tabla(resumenes)
    anchos = [
        max(len(str(f[i])) for f in [ENCABEZADO] + filas)
        for i in range(len(ENCABEZADO))
    ]
    lineas = []
    if titulo:
        lineas.append(titulo)
    lineas.append(
        "  ".join(
            str(c).ljust(anchos[i]) if i == 0 else str(c).rjust(anchos[i])
            for i, c in enumerate(ENCABEZADO)
        )
    )
    lineas.append("  ".join("-" * a for a in anchos))
    for f in filas:
        lineas.append(
            "  ".join(
                c.ljust(anchos[i]) if i == 0 else c.rjust(anchos[i])
                for i, c in enumerate(f)
            )
        )
    return "\n".join(lineas)


def tabla_markdown(resumenes):
    """Misma tabla en Markdown, para pegar en el informe."""

    filas = filas_tabla(resumenes)
    encabezado = ("Etapa", "n", "Media (ms)", "Mediana (ms)", "P95 (ms)", "Mín (ms)", "Máx (ms)")
    lineas = [
        "| " + " | ".join(encabezado) + " |",
        "|" + "|".join(["---"] + ["---:"] * (len(encabezado) - 1)) + "|",
    ]
    for f in filas:
        lineas.append("| " + " | ".join(f) + " |")
    return "\n".join(lineas)
