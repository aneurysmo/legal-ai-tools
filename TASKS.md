# Tareas — Lex Workspace (legal-ai-tools)

Tablero simple en markdown, versionado con el código. Formato: `- [ ]` pendiente, `- [x]` hecho.
Al mover una tarea de sección, hazlo en el mismo commit que el cambio que la resuelve cuando sea posible — así el historial de este archivo cuenta la historia del proyecto.

## En progreso

_(vacio — ver Hecho para lo recien cerrado)_

## Hecho — modelo de usuarios (2026-08-21)

21082601 - [x] Los usuarios deberan agregar como usuario ahora su email.
  - Email es un campo adicional al username (no lo reemplaza como login). Obligatorio y unico (`@unique` en el schema).
  - Agregados tambien `firstName`/`lastName`, ambos **opcionales** (no mandatorios).
  - Implementado: `schema.prisma.template` (campos nuevos en `User`), `auth.py` (`create_user` acepta email/nombres/apellidos, valida formato basico de email, `EmailTakenError` nuevo), `app.py` (formulario de registro con los campos nuevos).
  - Migracion local: `prisma/app.db` ya tenia 2 usuarios de prueba (`demo`, `demo1`) sin email — se conservaron con email placeholder (`usuario@local.pendiente`) via ALTER TABLE manual + indice unico, en vez de resetear la base (decision del usuario). `prisma db push` confirmado en sync sin perdida de datos.
21082602 - [x] Los usuarios deberan poder agregar a su usuario una imagen de perfil, tendra que existir una imagen por default. Por lo que se requerira realizar una UI donde puedan hacer esto.
  - Decision final de storage (ajustada, mas eficiente que el plan original): el set de 31 avatares es **curado y estatico**, viaja empaquetado con la app (mismo repo/Docker image en demo y prod) — en vez de guardar el SVG completo por usuario, la base solo guarda el **ID del avatar elegido** (`avatar String @default("default-generic")`, ej. `"lawyer-01-Santiago"`). Evita duplicar texto SVG en cada fila y es aun mas liviano que la idea original de "SVG como texto en Postgres".
  - Confirmado: los PDFs subidos NO se guardan como binario hoy (solo texto extraido en `Chunk.text` + `embedding`), asi que no requieren optimizacion adicional de storage por ahora.
  - Implementado en `auth.py`: `list_avatar_ids()`, `get_avatar_svg()`, `update_avatar()`, `get_user_avatar()`. UI en el sidebar de `app.py`: muestra el avatar actual junto al nombre del usuario conectado, expander "Cambiar avatar" con selector + vista previa + boton guardar.
21082603 - [x] Agregar 25 imagenes tipo avatar moderno como perfil de usuario (ampliado de 10 a 25 por el usuario), ten en cuenta que son abogados. — Avataaars (CC0). Se generaron 3 tandas para que el usuario eligiera/filtrara manualmente (tanda 1: 25, tanda 2: 25 mas, tanda 3: 5 mas) — el usuario elimino los que no encajaban y dejo 31 finales. Archivos renombrados/normalizados a formato unico `lawyer-NN-Nombre.svg` (numeracion secuencial 01-31, dos digitos) + `default-generic.svg`. Durante el renombrado 2 archivos (Paulina, Ricardo) se perdieron por un fallo silencioso de `mv` — repuestos manualmente. Total final: 31 avatares + 1 default en `assets/avatars/`, todos escaneados por seguridad (sin `<script>`/handlers). Ver [[21082610]] para el reemplazo futuro por Humaaans.
  - Ajustes pedidos por el usuario: **boca cerrada** (sin expresion de boca abierta). Tono de piel: se descarto forzar `skinColor` (el parametro de DiceBear requiere hex, no nombres, dio error 400) — se opta por **variedad natural** dejando que varie por seed.
  - Estilos evaluados: "personas", "open-peeps" (descartado — el usuario detecto un bug visual, genera personas con 3 ojos en algunas semillas) y **"avataaars" (elegido/confirmado por el usuario)**.
  - Licencia verificada por el usuario en dicebear.com/licenses: "avataaars" es **CC0 1.0** — libre de atribucion obligatoria, sin anuncios ni creditos requeridos.
  - Plan: descargar 25 SVG reales (seeds variadas, `mouth` en {default, serious, smile, twinkle, concerned} para evitar boca abierta) + 1 avatar default de silueta generica (dibujado a mano, sin dependencia externa, para evitar cualquier duda de licencia en el default). Se guardan como archivos + luego se insertan como texto en Postgres.
  - Se evaluaron alternativas mas "serias" (menos caricatura): imagen de referencia del usuario resulto no ser DiceBear real (era ilustracion con sombreado, probablemente IA de imagenes, sin licencia clara ni formato liviano). Se investigaron Craftwork Userpics y Humaaans como bancos con licencia clara:
    - **Craftwork Userpics — DESCARTADO.** Su licencia gratuita prohibe explicitamente usarse "en productos que vendes" (cita: "you cannot use the free assets... in products you sell") — inviable para PRD, que es un producto vendido a un cliente.
    - **Humaaans (Pablo Stanley, mismo autor de Avataaars) — CC0 confirmado en la fuente oficial, estilo mas sobrio/serio que Avataaars.** No se pudo automatizar la descarga (solo se distribuye como archivo de Figma/Sketch/Gumroad, sin SVG sueltos publicos) — requiere que el usuario exporte manualmente desde Figma. **Pendiente para el futuro** (ver tarea nueva abajo), no bloquea el trabajo actual.
  - **Decision final (por tiempo): se usan los 25 Avataaars ya descargados como set definitivo por ahora.**
21082604 - [x] Cambios en la app respecto al modelo de usuarios — completado: schema, `auth.py` y UI actualizados, `prisma db push` verificado localmente sin perdida de datos. **Ya no bloquea Neon.**

## Pendiente

21082111 - [x] Reubicar el avatar/perfil del usuario: hoy vive en el sidebar y se ve mal (imagen sin recortar/redimensionar bien). Debe moverse a la esquina superior derecha del area de trabajo, alineado con el texto "Deploy" nativo de Streamlit (aclarar al usuario que "Deploy" es un control propio de Streamlit, no de la app).
  - Bug de tamano de imagen: el SVG de DiceBear trae sus propios atributos `width`/`height` que ignoraban el `div` contenedor. Corregido con CSS (`.avatar-thumb svg { width:100%; height:100%; }`) en vez de solo el estilo inline del div.
  - Implementado: nueva funcion `render_profile_bar()` en `app.py`, renderizada en el area principal (no sidebar) justo antes del router de herramientas, alineada a la derecha via `st.columns([6, 1.3])`. Aclarado al usuario que "Deploy" es control nativo de Streamlit, no editable desde el codigo de la app.
21082112 - [x] Agregar opcion para que el usuario edite sus datos de perfil (email, nombres, apellidos) y su avatar desde esa misma zona superior derecha (no solo elegir avatar, tambien editar datos).
  - Implementado: `auth.get_user_profile()` / `auth.update_profile()` (nuevas), formulario dentro del popover de perfil con validacion de email y manejo de `EmailTakenError`.
21082113 - [x] Mover "Cerrar sesion", el selector de Tema y el toggle de Modo oscuro desde el sidebar al mismo menu de perfil en la esquina superior derecha (junto con avatar y edicion de datos).
  - Todo el bloque que antes vivia repartido en el sidebar (avatar, expander "Cambiar avatar", boton "Cerrar sesion", selectbox Tema, toggle Modo oscuro) se removio del sidebar y ahora vive dentro del `st.popover` de `render_profile_bar()`. El sidebar solo conserva la marca, el radio de herramientas y el estado del proveedor LLM.
  - Verificado: sintaxis (`py_compile` + `ast.parse`) y arranque del servidor sin errores de importacion/ejecucion a nivel modulo. La logica del popover en si depende de sesion autenticada (WebSocket) y no se pudo probar por HTTP simple — **pendiente de confirmacion visual del usuario al probar la app**.
21082610 - [ ] (Futuro) Reemplazar los avatares Avataaars por **Humaaans** (Pablo Stanley, mismo autor de Avataaars) — estilo mas sobrio/serio, CC0 confirmado, pero requiere exportar manualmente desde Figma (no se pudo automatizar la descarga). El usuario debe abrir el archivo en figma.com (link en humaaans.com), armar ~25 combinaciones con ropa formal, y exportar como SVG; luego se integran igual que el set actual.
21082601 - [ ] Crear cuenta Neon (proyecto separado para demo) y obtener `DATABASE_URL` real.
21082602 - [ ] Probar `prisma db push` localmente contra Neon (sin Docker) para validar el `DATABASE_URL` antes de usarlo en Streamlit Cloud.
21082603 - [ ] Configurar el panel de Secrets de Streamlit Community Cloud (TOML) con las variables de `.env.demo`.
21082604 - [ ] Desplegar la app en Streamlit Community Cloud (conectar repo, primer deploy real).
21082605 - [ ] Crear un segundo proyecto Neon (o proveedor equivalente) **separado**, exclusivo para PRD — nunca compartir instancia con demo.
21082606 - [ ] Desplegar en Google Cloud Run (producción) usando el Dockerfile ya verificado.
21082607 - [ ] Configurar un secret manager (ej. Google Secret Manager) para credenciales de producción, en vez de `.env` plano.
21082608 - [x] Decidir si/cuándo comitear `.dockerignore` — comiteado en `d9d033c` ("Add .dockerignore to exclude venv/ and secrets from build context").
21082609 - [ ] Compactar el disco virtual de WSL2 (`wsl --shutdown` + `diskpart compact vdisk`) para recuperar espacio en disco — requiere PowerShell como administrador (el usuario lo hará manualmente).

## Hecho

01082601 - [x] Definir plan de proveedores LLM: Gemini principal, Groq fallback.
01082602 - [x] Optimizar `requirements.txt` para PyTorch CPU-only (reduce tamaño de imagen).
01082603 - [x] Resolver la limitación de Prisma para `provider` dinámico vía `DB_PROVIDER` (template + script generador).
01082604 - [x] Crear `Dockerfile` base compartido por demo y PRD.
01082605 - [x] Crear `.env.demo.example` / `.env.prod.example`.
01082606 - [x] Verificar que `docker build` funciona de extremo a extremo (imagen final 1.73 GB).
01082607 - [x] Crear `.dockerignore` (excluye `venv/`, secretos, etc. del contexto de build) — verificado, pendiente de commit.
01082608 - [x] Cerrar los 3 gaps de despliegue en Streamlit Community Cloud: `packages.txt`, wheel de spaCy pip-instalable, `_ensure_prisma_client()` en `app.py`.
01082609 - [x] Documentar todo lo anterior en `README.md`.
