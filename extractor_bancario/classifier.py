"""
Clasificador de movimientos bancarios.
Categorias basadas en el criterio real del estudio contable.

Categorias:
  25413 Debitos     | impuesto debitos Ley 25413 y reversiones
  25413 Creditos    | impuesto creditos Ley 25413
  IVA               | IVA
  Percep IVA        | percepciones de IVA
  Retencion IIBB    | retencion Ingresos Brutos sobre creditos (SIRCREB)
  IIBB Percepcion   | percepcion Ingresos Brutos sobre debitos
  Impuesto Sellos   | impuesto de sellos
  Comision          | comisiones bancarias e intereses descubierto
  Pago TC           | pagos tarjeta de credito (Visa, etc.)
  Prestamo          | cuotas/acreditaciones de prestamos
  Cheques           | cheques propios y de camara (ECHEQ, pago cheque)
  Transferencia     | transferencias propias, a/de terceros, AFIP, BIP
  Creditos          | acreditaciones de terceros (CR.TRAN, IPLC, DNET)
  Pago              | pagos a proveedores y servicios varios
  Debitos           | extracciones de efectivo, compras tarjeta debito
  Otros             | sin categoria
"""
import re

REGLAS = [
    ("25413 Creditos", [
        r"\bIMP\.?\s*CRE\.?\s*LEY\s*25413\b",
        r"\bIMPUESTO\s+CREDITO\s*[-]?\s*LEY\s*25413\b",
        r"DEV\.?\s*IMP\.?\s*(CRE|CRED)",
    ]),
    ("25413 Debitos", [
        r"\bIMP\.?\s*DEB\.?\s*LEY\s*25413\b",
        r"\bIMPUESTO\s+DEBITO\s*[-]?\s*LEY\s*25413\b",
        r"\bIMPUESTO\s+DEB\.?\s*LEY\s*25413\b",
        r"\bIMP\.?\s*LEY\s*25413\b",
        r"REV\.?\s*IMP\.?\s*DEBITO",
        r"DEV\.?\s*IMP\.?\s*DEB",
    ]),
    ("IVA", [
        r"^IVA\b",
        r"\bIVA\s+R\.?I\.?\b",
        r"\bIVA\s+TASA\s+GENERAL\b",
        r"\bIVA\s+(MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE|ENERO|FEBRERO)\b",
    ]),
    ("Percep IVA", [
        r"\bPERCEP\.?\s*IVA\b",
        r"\bPERCEPCION\s+IVA\b",
    ]),
    ("Retencion IIBB", [
        r"\bSIRCREB\b",
        r"\bINGRESOS\s+BRUTOS\s+SIRCREB\b",
        r"\bING\.?\s*BRUTOS\s+S/\s*CRED\b",
        r"\bIMP\.?\s*ING\.?\s*BRUTOS\b",
        r"\bCOBRO\s+IIBB\b",
        r"\bREVERSA\s+INGRESOS\s+BRUTO\b",
    ]),
    ("IIBB Percepcion", [
        r"\bIMPUESTO\s+I\.?BRUTOS\s*[-]?\s*PERCEPCION\b",
        r"\bPERCEP\.?\s*INGRESOS\s+BRUTOS\b",
        r"\bPERCEP\.?\s*IIBB\b",
        r"\bIIBB\s+PERCEP\b",
    ]),
    ("Impuesto Sellos", [
        r"\bIMPUESTO\s+(DE\s+)?SELLOS\b",
    ]),
    ("Comision", [
        r"\bCOMISION\b",
        r"\bCOM\.?\s*MANT\b",
        r"\bCOM\s+MANT\b",
        r"\bMANTENIM\b",
        r"\bCOM\.?\s*GESTION\b",
        r"\bINTERES(ES)?\s+SALDO\s+DEUDOR\b",
        r"\bINTERESES?\s+SOBRE\s+SALDOS\b",
        r"\bINTERESES?\s+COBRADOS\b",
        r"\bCOMISION\s+POR\s+CUSTODIA\b",
        r"\bLIQUIDACION\s+PRESTAMOS\s*[-]?\s*IMPUESTOS\b",
    ]),
    ("Pago TC", [
        r"\bPAGO\s+(LIQUIDACION\s+)?VISA\b",
        r"\bPAGO\s+VISA\s+EMPRESA\b",
        r"\bCUENTA\s+VISA\b",
        r"\bPAGO\s+TARJ\b",
        r"\bTARJ\.?\s*PROCAMPO\b",
    ]),
    ("Prestamo", [
        r"\bCUOTA\s+DE\s+PRESTAMO\b",
        r"\bACREDITACION\s+DE\s+PRESTAMO\b",
        r"\bLIQUIDACION\s+DE\s+PRESTAMOS\b",
    ]),
    ("Cheques", [
        r"\bECHEQ\b",
        r"\bCHEQUE\s+DE\s+CAMARA\b",
        r"\bCHEQUE\s+PAGADOR\b",
        r"\bPAGO\s+CHEQUE\b",
        r"\bDEBITO\s+EN\s+CUENTA\b",
    ]),
    ("Transferencia", [
        r"\bTRANSFERENCIA(S)?\b",
        r"\bTRANSF\s+[ADEIOP]",
        r"\bTRANSF\.?\s+A\s+",
        r"\bTRANSF\.?\s+DE\s+",
        r"\bTRANSF\.?\s*INMED\b",
        r"\bTRF\s+INMED\b",
        r"\bTRANSF\.?\s*AFIP\b",
        r"\bTRANSF\.?\s*CTAS\s+PROPIAS\b",
        r"\bBIP\s+DB\.?TR\b",
        r"\bTRANSFERENCIAS\s+CASH\b",
        r"DEB\.?\s+AUTOM",
        r"\bRECHAZO\s+DE\s+DEBITO\s+AUTOMATICO\b",
        r"\bTRANSF\.?\s+A\s+TERCEROS\b",
        r"\bTRANSF\s+INMED\s+CP\b",
    ]),
    ("Creditos", [
        r"\bVENTA\s+(BURSATIL|DE\s+TITULOS|DE\s+VALORES)\b",
        r"\bCR\.?\s*TRAN\b",
        r"\bCRED\.?\s*TRF\b",
        r"\bI\.P\.L\.C\b",
        r"\bIPLC\b",
        r"\bDNET\s+CREDITO\b",
        r"\bTR\.?\s*NE\d+\b",
        r"\bCREDITO\s+TRANSFERENCIA\b",
    ]),
    ("Pago", [
        r"\bTRF\s+INMED\s+PROVEED\b",
        r"\bPAGO\s+(DE\s+)?SERVICIOS\b",
        r"\bSERVICIO\s+ACREDITAMIENTO\s+DE\s+HABERES\b",
        r"\bSERVICIO\s+PAGO\s+A\s+PROVEEDORES\b",
        r"\bP\.?\s*SERV\b",
        r"\bPAGO\s+SERVICIOS\s+VARIOS\b",
    ]),
    ("Debitos", [
        r"\bEXTRACCION\s+CAJERO\b",
        r"\bEXTRACCION\s+EFECTIVO\b",
        r"\bDEP\.?\s*EFVO\b",
        r"\bCOMPRA\s+TARJETA\b",
    ]),
]

REGLAS_COMPILADAS = [
    (cat, [re.compile(p, re.IGNORECASE) for p in patrones])
    for cat, patrones in REGLAS
]

CATEGORIA_DEFAULT = "Otros (a revisar)"


def clasificar(descripcion: str) -> str:
    if not descripcion:
        return CATEGORIA_DEFAULT
    for categoria, patrones in REGLAS_COMPILADAS:
        for patron in patrones:
            if patron.search(descripcion):
                return categoria
    return CATEGORIA_DEFAULT


def clasificar_dataframe(df, columna_descripcion="Descripción"):
    df = df.copy()
    df["Categoria"] = df[columna_descripcion].apply(clasificar)
    df["Tipo"] = df["Importe"].apply(
        lambda x: "Credito" if (x is not None and x >= 0) else "Debito"
    )
    return df
