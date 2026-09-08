# Clasificador de Extractos Bancarios (AR)

Procesa extractos bancarios en PDF (Banco Provincia, BBVA, Banco Galicia y
Santander) y genera un Excel con todos los movimientos clasificados por
categoría (impuestos, comisiones, transferencias, sueldos, AFIP, cheques,
etc.).

## Instalación

```bash
python3 -m venv venv
source venv/bin/activate   # En Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Uso

```bash
streamlit run app.py
```

Se abre en el navegador. Ahí podés:
1. Subir uno o varios PDF.
2. Indicar de qué banco es cada uno.
3. Procesar.
4. Revisar la vista previa (movimientos y resumen por categoría).
5. Descargar el Excel final.

## Estado de los parsers por banco

| Banco            | Estado                                                                 |
|-------------------|-------------------------------------------------------------------------|
| Banco Provincia   | ✅ Validado: cuadre matemático exacto contra extracto real.            |
| BBVA              | ✅ Validado: cuadre matemático exacto contra extracto real.            |
| Banco Galicia     | ✅ Validado: cuadre matemático exacto contra extracto real.            |
| Santander         | ⚠️ Estimado sobre el patrón típico de extractos AR. No se pudo probar contra un PDF real de Santander. Si los resultados no cuadran, compartí un extracto de ejemplo (los montos pueden estar editados/ficticios) para ajustar `parsers/santander.py`. |

"Cuadre matemático" significa: se verificó, movimiento por movimiento, que
`saldo_anterior + importe == saldo_informado_por_el_banco` en absolutamente
todas las filas extraídas, lo cual confirma que no se perdió ni se inventó
ningún movimiento.

## Estructura del proyecto

```
app.py                  # Interfaz Streamlit
procesador.py            # Orquesta: parsear -> clasificar -> exportar a Excel
classifier.py             # Reglas de clasificación por palabras clave
parsers/
  utils.py                # Helpers de parsing de montos y fechas en formato AR
  provincia.py             # Parser Banco Provincia
  bbva.py                  # Parser BBVA
  galicia.py               # Parser Banco Galicia
  santander.py             # Parser Santander (estimado, ver advertencia arriba)
```

## Cómo agregar o ajustar categorías

Editar `classifier.py`, lista `REGLAS`: cada tupla es
`(nombre_categoria, [lista_de_patrones_regex])`. El orden importa: la primera
regla que matchee gana. Los movimientos que no matcheen ninguna regla quedan
en "Otros (a revisar)" para que los puedas revisar y, si hace falta, agregar
una regla nueva.

## Cómo agregar un banco nuevo

1. Crear `parsers/nuevo_banco.py` con una función `to_dataframe(pdf_path)` que
   devuelva un DataFrame con columnas `Fecha, Fecha Valor, Descripción,
   Importe, Saldo, Banco` (ver `parsers/galicia.py` como referencia, ya que
   maneja descripciones multilínea).
2. Registrarlo en `parsers/__init__.py` dentro del diccionario `PARSERS`.
3. Validar el parser contra un extracto real verificando el cuadre matemático
   movimiento a movimiento (ver ejemplo de validación usado durante el
   desarrollo, comparando `saldo_anterior + importe` contra el saldo
   informado en cada línea).
