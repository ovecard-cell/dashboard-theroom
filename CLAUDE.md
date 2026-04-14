# The Room Argentina — Dashboard

## Cómo trabajamos

Gustavo o Tiki me pasan archivos o info. Yo proceso y actualizo el dashboard.
No hay pasos manuales. Solo pasame las cosas y listo.

---

## Lo que me pueden pasar y qué hago

| Qué me pasan | Qué hago |
|---|---|
| Archivo `.xls` de Dux en `data/ventas/` | Lo leo con `load_dux_files()`, muestro resumen de ventas |
| Screenshot o foto del homebanking | Leo los saldos, escribo en `data/bancos.json` |
| Me dicen saldos ("BBVA -9M, Corrientes -10.7M") | Escribo en `data/bancos.json` |
| Screenshot de Meta Ads | Leo inversión/ROAS, escribo en `data/meta_ads.json` |
| Me dicen un gasto ("pagué alquiler $925K") | Lo agrego a `data/gastos.json` |
| Me dicen que Tiki subió los archivos | Leo todo, doy resumen del día |

---

## Estructura de archivos

```
Dash board the room/
├── app.py                  ← Dashboard principal Streamlit (NO crear otros app_*.py)
├── data_processor.py       ← Toda la lógica de procesamiento Dux
├── requirements.txt
├── run.bat                 ← Doble clic para arrancar
├── CLAUDE.md               ← Este archivo (en la raíz, no en data/)
└── data/
    ├── ventas/             ← .xls de Dux van acá (NUNCA modificar)
    ├── cheques.json        ← Cheques emitidos y por negociar
    ├── stock_inicial.json  ← Stock inicial de proveedores
    ├── deuda_personal.json ← Plata que Gustavo puso en el negocio
    ├── bancos.json         ← Saldos bancarios (yo lo escribo)
    ├── gastos.json         ← Gastos del mes (yo lo escribo)
    └── meta_ads.json       ← Datos de Meta Ads (yo lo escribo)
```

---

## Para correr el servidor

```
py -3 -m streamlit run app.py --server.port 8501
```

Comando Python en este sistema: `py -3` (no `python` ni `python3`)

---

## Datos del negocio

- **Tienda:** The Room Argentina — ropa masculina
- **Local:** La Rioja 943, Corrientes
- **Online:** theroomarg.com (Tienda Nube)
- **POS:** Dux Software (exporta .xls)
- **Publicidad:** Meta Ads
- **Equipo:** Gustavo (dueño), Gabriela, Sofía, Facu (diseñador externo)
- **Objetivo diario:** $300.000
- **Gastos fijos:** ~$7.000.000/mes
- **Deuda bancaria activa:** ~$19.75M en descubierto

---

## Formato archivos Dux (.xls)

- Headers en **fila 3** (`header=2` en pandas)
- Engine: `xlrd` para .xls, `openpyxl` para .xlsx
- Filtros obligatorios:
  - Quitar filas donde `Producto` contiene "ENVIO" o "COSTO_ENVIO"
  - Quitar filas donde `Cantidad` <= 0 (devoluciones)
- Canal Online: si "THEROOM1" en `Personal Registra`

### Columnas clave
| Columna | Uso |
|---------|-----|
| `Fecha Comp` | Fecha de venta (DD/MM/YYYY HH:MM) |
| `Producto` | Nombre del producto |
| `Cantidad` | Unidades |
| `Total Sin IVA` | Ingreso neto |
| `% Desc.` | Descuento aplicado |
| `Precio Uni` | Precio de lista |
| `Costo Unitario Producto` | Costo |
| `Forma Pago` | Efectivo / transferencia / tarjeta / cuotas |
| `Personal Registra` | "THEROOM1" = online, resto = físico |
| `Marca` | Marca del producto |
| `Rubro` | Categoría (REMERAS, CAMISAS, JEANS, etc.) |

---

## Clasificación stock nuevo

| Proveedor | Fecha ingreso | Prefijos de producto |
|-----------|--------------|----------------------|
| KAZUMA    | 26/03/2026   | REMERA BASICA LYCRA TOM, REMERA OVER POPPIES/LOS ANGELES/CORAL/EVERY, REMERA REGULAR TACOS/GRAVE/JUICY, CAMISA ROTHE, JEAN RIG MOM MIROX/JARO |
| LISBON    | 28/03/2026   | PANTALON RINGO, JEAN SEVEN STRAIGHT, JEAN FALCON REGULAR, CHOMBA TEJIDA, REMERA OVER LISA LB, REMERA OVER TRIEND |
| DISTRICT  | 30/03/2026   | REMERA GIRONA, REMERA NAPOLES, JEAN CENTINELA, CHOMBA EMINEM II, BILLETERA |

---

## Cheques (al 12/04/2026)

### Emitidos — hay que pagarlos sí o sí
| ID | Proveedor | Vencimiento | Monto |
|----|-----------|-------------|-------|
| #214 | Lisbon | 15/04/2026 | $1.279.705 |
| #215 | Dacob/Kazuma | 21/04/2026 | $573.127 |
| #216 | Dacob/Kazuma | 21/05/2026 | $573.127 |
| #217 | Dacob/Kazuma | 21/06/2026 | $573.127 |

### No emitidos — dilatar, negociar desde mayo
| Proveedor | Monto |
|-----------|-------|
| Lisbon (Dandy) compra marzo | $1.975.000 |
| District (Tarkus) compra marzo | $956.512 |

---

## Deuda personal de Gustavo (lo que el negocio le debe)

- Solo en 2026: **$15.798.100**
- Histórico 2022-2025: pendiente cargar
- El negocio le debe esa plata a Gustavo, no es deuda bancaria

---

## Gastos fijos mensuales (~$7M/mes)

| Rubro | Monto |
|-------|-------|
| Sueldos (Gabriela + Sofía) | ~$2.1M |
| Gastos bancarios | ~$1.26M |
| Alquiler | ~$925K |
| Luz/gas/tel | ~$488K |
| Transporte | ~$691K |
| AFIP/impuestos | ~$463K |
| Tienda Nube | ~$92K |
| Otros | ~$1M |

---

## Pricing

- Markup: 2.5x remeras, 2.3x todo lo demás
- Descuentos: 15% efectivo, 10% transferencia
- Cuotas sin interés: hasta $150K → 6 cuotas / más de $150K → 9 cuotas
- Pantalón Ringo: precio fijo $82.080
- Stock viejo verano: 70% OFF (solo efectivo/transferencia)
- Stock viejo invierno/todo año: precio completo, NO liquidar

---

## Rotación stock nuevo (al 11/04/2026 — 17 días)

### Kazuma (ingresó 26/03)
- Remera Básica Lycra Tom: 43 ini → 9 vendidas → **ESTRELLA, reponer L y XL**
- Remera Over: 31 ini → 2 vendidas → lento
- Remera Regular: 24 ini → 3 vendidas → lento
- Camisa Rothe: 4 ini → 1 vendida → ok
- Jean Rig Mom: 13 ini → **0 vendidas → NO ROTA**

### Lisbon (ingresó 28/03)
- 80 unidades → solo 3 vendidas → muy lento
- Pantalón Ringo: **0 vendidos** (era top histórico online)

### District (ingresó 30/03)
- 47 unidades → solo 3 vendidas → lento

---

## Ventas históricas de referencia

| Mes | Neto | Promedio/día |
|-----|------|-------------|
| Abril 2025 | $9.4M | $314K/día |
| Mayo 2025 (Hot Sale) | $12.9M | $415K/día |
| Junio 2025 (Día del Padre) | $14M | $466K/día |
| Abril 2026 sin pauta | ~$68K/día | — |
| Abril 2026 con pauta (3 días) | ~$274K/día | — |

---

## Meta Ads

- ROAS global histórico: **3.2x**
- Campaña de CAMISAS: **ROAS 5.96x** (la que más convierte)
- Campaña "GANGAS": **ROAS 4.6x**
- Mejor campaña individual: ROAS 9.36x
- Campaña activa desde 09/04: catálogo dinámico, $20K/día, toda Argentina 25-55
- Las camisas manga larga son el **60% de ventas online históricas**
- El catálogo necesita 800-1000 productos para que Meta optimice bien (hoy ~400)

### Top productos históricos online
1. Camisa Daytona Azul — 55 ventas
2. Remera Lisa Blanca — 51 ventas
3. Camisa USA Argentina — 43 ventas
4. Camisa Daytona Bordo — 40 ventas
5. Remera Lisa Negra — 36 ventas

---

## Plan estratégico

- **Abril 2026:** sobrevivir, cubrir cheques 15/04 y 21/04, comprar camisas manga larga a plazo
- **Mayo 2026:** Hot Sale (~19/05), campañas con descuento agresivo, objetivo $12M+
- **Junio 2026:** colección invierno completa, Día del Padre (~22/06), objetivo $14M+
- **Enero 2027:** dar vuelta la bicicleta, empezar a saldar deuda bancaria

---

## Pendientes urgentes (al 12/04/2026)

1. Cubrir cheque Lisbon #214 por $1.279.705 el **15/04**
2. Comprar mercadería a plazo esta semana: camisas manga larga + remeras + abrigo liviano
3. Consultar a Kazuma y District si tienen camisas para invierno
4. Verificar pixel Meta con Tienda Nube (Facu)
5. Subir catálogo Tienda Nube de 400 a 800-1000 productos
6. Negociar cheques Lisbon y District nuevos desde mayo

---

## Diseño del dashboard

- Tema oscuro: `#0d0d14` fondo, `#1a1a2e` cards
- Fuente: Inter (Google Fonts)
- Colores: rojo `#e94560`, verde `#00c96b`, azul `#3a86ff`, amarillo `#f7b731`, morado `#8b5cf6`
- NO usar componentes nativos de Streamlit para métricas o tablas — usar HTML/CSS propio
- Siempre ocultar: menú Streamlit, footer, toolbar, deploy button
