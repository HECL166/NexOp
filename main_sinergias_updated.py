import pandas as pd
import os
import re
import traceback
import random

# =====================================================================
# 1. FUNCIONES DE APOYO Y LIMPIEZA
# =====================================================================
def limpiar_cruce(valor):
    if pd.isna(valor): return ""
    texto = str(valor).replace('\xa0', ' ').replace('\n', '').replace('\r', '').replace('_x000D_', '').strip().upper()
    if texto in ['NAN', 'NONE', '', '-']: return ""
    if texto.endswith('.0'): texto = texto[:-2]
    return texto

def limpiar_rev(valor):
    texto = limpiar_cruce(valor)
    if texto == "": return ""
    texto_limpio = texto.lstrip('0')
    if texto_limpio == "": return "00"
    return texto_limpio.zfill(2)

def limpiar_ruta(valor):
    texto = limpiar_cruce(valor)
    if texto == "": return ""
    return texto.zfill(9)

def juntar_unicos(x):
    valores = [str(v).strip().upper() for v in x if pd.notna(v)]
    valores = [v for v in valores if v not in ['', 'NAN', 'NONE', '-']]
    return ", ".join(list(dict.fromkeys(valores)))

def obtener_evidencias_vacias(): 
    return {
        "Evidencia_Docs": "-", "Evidencia_C1_HTI": "-", "Evidencia_C2_PNSN": "-", 
        "Evidencia_C3_OCCAR": "-", "Evidencia_C4_PEP": "-", "Evidencia_C5_Tiempo": "-"
    }

def chequear_materiales_incluidos(dict_padre, dict_hijo):
    if not dict_hijo:
        return True 
    for pieza, cant_hijo in dict_hijo.items():
        if pieza not in dict_padre: return False
        if dict_padre[pieza] < cant_hijo: return False
    return True

# --- NUEVO: FUNCIÓN CHIVATA PARA EXTRAER EL MOTIVO EXACTO DEL FALLO ---
def obtener_motivo_fallo_materiales(dict_padre, dict_hijo):
    motivos = []
    for pieza, cant_hijo in dict_hijo.items():
        if pieza not in dict_padre: 
            motivos.append(f"El padre no tiene el PN {pieza} (el hijo requiere {cant_hijo})")
        elif dict_padre[pieza] < cant_hijo: 
            motivos.append(f"Cantidad insuficiente del PN {pieza} (Padre tiene {dict_padre[pieza]}, pero el hijo requiere {cant_hijo})")
    
    # Usamos " | " para separar los motivos si fallan varios Part Numbers a la vez
    return " | ".join(motivos)
# ----------------------------------------------------------------------

def limpiar_6_digitos(valor):
    val_limpio = str(valor).replace('-', '').strip().upper()
    if val_limpio in ['NAN', 'NONE', '']: return ""
    return val_limpio[:6]

# =====================================================================
# 2. MOTOR PRINCIPAL UNIFICADO
# =====================================================================
def ejecutar_pipeline_completo(rutas, carpeta_outputs):
    try:
        print("-" * 70)
        print("**[ INICIANDO FASE 1 ] EXTRACCIÓN, LIMPIEZA Y AGRUPACIÓN**")
        print("-" * 70)

        # -------------------------------------------------------------
        # 1. CARGA DE ARCHIVOS A PRUEBA DE BALAS
        # -------------------------------------------------------------
        print("  - Cargando Excels originales a memoria...")
        
        df_operaciones_raw = pd.read_excel(rutas["Operaciones"], sheet_name='Operaciones', dtype=str)
        df_documentos_raw = pd.read_excel(rutas["Operaciones"], sheet_name='Documentos', dtype=str)
        df_materiales_raw = pd.read_excel(rutas["Operaciones"], sheet_name='Materiales', dtype=str)
        
        if 'T. Producción' not in df_operaciones_raw.columns: df_operaciones_raw['T. Producción'] = '0.0'
        if 'Est. Trab.' not in df_operaciones_raw.columns: df_operaciones_raw['Est. Trab.'] = '-'

        file_analisis = rutas.get("Lanzamiento", rutas.get("Analisis_PD"))
        df_analisis_raw = pd.read_excel(file_analisis, sheet_name=0, dtype=str)
        
        df_lanz_bruto = df_analisis_raw.copy()
        df_lanz_bruto.columns = df_lanz_bruto.columns.str.strip()
        df_lanz_bruto = df_lanz_bruto.rename(columns={'ITEM REF': 'ITEM', 'PN': 'P/N', 'SN': 'S/N'})
        
        # --- EXTRACCIÓN DE APLICABILIDAD ESTRICTA (COLUMNA M = Índice 12) En función del nombre de la columna de aplicabilidad---
        try:
            columna_n_nombre = df_lanz_bruto.columns[5]
            df_lanz_bruto['FLAG_APLICABILIDAD'] = df_lanz_bruto.iloc[:, 5]
            print(f"    * Columna de aplicabilidad detectada en Lanzamiento (Columna N): '{columna_n_nombre}'")
        except IndexError:
            # --- EXTRACCIÓN DE APLICABILIDAD ESTRICTA (ÚLTIMA COLUMNA REAL DE LA PLANTILLA) ---
            # Filtramos columnas vacías o innominadas de Pandas para asegurar que cogemos la última columna con texto
            cols_reales = [c for c in df_lanz_bruto.columns if not str(c).strip().startswith('Unnamed')]
            ultima_columna_original = cols_reales[-1]
            df_lanz_bruto['FLAG_APLICABILIDAD'] = df_lanz_bruto[ultima_columna_original]
            print(f"    * Columna de aplicabilidad detectada en Lanzamiento (Última columna): '{ultima_columna_original}'")
        # --------------------------------------------------------------------# --------------------------------------------------------------------

        # =====================================================================
        # INTEGRACIÓN DE TASAR PARA MSN123 (SOURCE HOURS Y DOCUMENT TYPE)- Esto puede ser que se meta en 'Análisis de la PD'
        # =====================================================================
        file_tasar = rutas.get("TASAR")
        if file_tasar and os.path.exists(file_tasar):
            print("  - Cargando archivo TASAR para cruzar Source Hours y Document Type...")
            df_tasar_raw = pd.read_excel(file_tasar, dtype=str)
            df_tasar_raw.columns = df_tasar_raw.columns.astype(str).str.strip().str.upper()
            
            col_task_lanz_cand = [c for c in df_lanz_bruto.columns if 'TASK' in str(c).upper() and 'REF' in str(c).upper()]
            nombre_task_lanz = col_task_lanz_cand[0] if col_task_lanz_cand else 'TASK REFERENCE'
            if nombre_task_lanz not in df_lanz_bruto.columns: df_lanz_bruto[nombre_task_lanz] = ""
            
            col_task_tasar_cand = [c for c in df_tasar_raw.columns if 'TASK' in c and 'REF' in c]
            col_sh_tasar_cand = [c for c in df_tasar_raw.columns if 'SOURCE' in c and 'HOUR' in c]
            col_dt_tasar_cand = [c for c in df_tasar_raw.columns if 'DOCUMENT' in c and 'TYPE' in c]
            
            if col_task_tasar_cand:
                col_task_tasar = col_task_tasar_cand[0]
                cols_to_extract = [col_task_tasar]
                if col_sh_tasar_cand: cols_to_extract.append(col_sh_tasar_cand[0])
                if col_dt_tasar_cand: cols_to_extract.append(col_dt_tasar_cand[0])
                
                df_tasar_subset = df_tasar_raw[cols_to_extract].drop_duplicates(subset=[col_task_tasar])
                df_lanz_bruto['TMP_KEY'] = df_lanz_bruto[nombre_task_lanz].apply(limpiar_cruce)
                df_tasar_subset['TMP_KEY'] = df_tasar_subset[col_task_tasar].apply(limpiar_cruce)
                
                df_lanz_bruto = pd.merge(df_lanz_bruto, df_tasar_subset.drop(columns=[col_task_tasar]), on='TMP_KEY', how='left')
                df_lanz_bruto.drop(columns=['TMP_KEY'], inplace=True)
                
                if col_sh_tasar_cand: df_lanz_bruto.rename(columns={col_sh_tasar_cand[0]: 'SOURCE HOURS'}, inplace=True)
                if col_dt_tasar_cand: df_lanz_bruto.rename(columns={col_dt_tasar_cand[0]: 'DOCUMENT TYPE'}, inplace=True)
        # =====================================================================

        col_doc_type_cand = [c for c in df_lanz_bruto.columns if 'DOCUMENT' in str(c).upper() and 'TYPE' in str(c).upper()]
        nombre_doc_type = col_doc_type_cand[0] if col_doc_type_cand else 'DOCUMENT TYPE'
        if nombre_doc_type not in df_lanz_bruto.columns: df_lanz_bruto[nombre_doc_type] = ""
        
        ops_routes = df_operaciones_raw.copy()
        ops_routes.columns = ops_routes.columns.str.strip().str.upper()
        col_r_op_init = [c for c in ops_routes.columns if 'RUTA' in c and 'LOCAL' in c][0]
        pos_r_op_init = list(ops_routes.columns).index(col_r_op_init)
        col_v_op_init = ops_routes.columns[pos_r_op_init + 1]
        unique_ops_keys = ops_routes[[col_r_op_init, col_v_op_init]].drop_duplicates()
        
        col_r_lanz_init = [c for c in df_lanz_bruto.columns if 'RUTA' in str(c).upper() and 'LOCAL' in str(c).upper()][0]
        
        col_v_lanz_cand = [c for c in df_lanz_bruto.columns if 'REV' in str(c).upper() and 'RUTA' in str(c).upper()]
        col_v_lanz_init = col_v_lanz_cand[0] if col_v_lanz_cand else df_lanz_bruto.columns[list(df_lanz_bruto.columns).index(col_r_lanz_init) + 1]
        
        existing_keys = set(df_lanz_bruto[col_r_lanz_init].apply(limpiar_ruta) + "-" + df_lanz_bruto[col_v_lanz_init].apply(limpiar_rev))
        
        col_sh_orig = [c for c in df_lanz_bruto.columns if 'SOURCE' in str(c).upper() and 'HOUR' in str(c).upper()]
        nombre_sh_real = col_sh_orig[0] if col_sh_orig else 'Source Hours'
        
        rows_to_add = []
        for _, row_op in unique_ops_keys.iterrows():
            r_c = limpiar_ruta(row_op[col_r_op_init])
            v_c = limpiar_rev(row_op[col_v_op_init])
            if f"{r_c}-{v_c}" not in existing_keys:
                rows_to_add.append({
                    col_r_lanz_init: row_op[col_r_op_init], col_v_lanz_init: row_op[col_v_op_init],
                    'ITEM': f"AUTO_{r_c}_{v_c}", 'P/N': '', 'S/N': '', nombre_sh_real: '', 'FLAG_APLICABILIDAD': 'N'
                })
        if rows_to_add:
            df_lanz_bruto = pd.concat([df_lanz_bruto, pd.DataFrame(rows_to_add)], ignore_index=True)
            
        df_quotation = df_lanz_bruto.copy()
        df_quotation = df_quotation.rename(columns={'Source Hour': 'SOURCE HOURS', 'ITEM': 'ITEM REF'})

        # -------------------------------------------------------------
        # 2. PRIORIDADES, SMART KITS Y ADD WORKS
        # -------------------------------------------------------------
        print("  - Cargando archivo WP y SOURCES A400...")
        file_prioridades = rutas.get("Prioridades")
        if not file_prioridades: raise KeyError("No se ha definido la ruta 'Prioridades' en el diccionario.")
        
        df_prioridades_raw = pd.read_excel(file_prioridades, sheet_name=0, header=1).iloc[:, 1:]
        df_prioridades_raw.columns = df_prioridades_raw.columns.astype(str).str.strip().str.upper()
        
        col_source_cand = [c for c in df_prioridades_raw.columns if 'SOURCE' in c and 'PRIORIDAD SOURCE' not in c]
        col_prio_cand = [c for c in df_prioridades_raw.columns if 'PRIORIDAD SOURCE' in c]
        if not col_source_cand or not col_prio_cand: raise ValueError("Error en las columnas del archivo Prioridades.")
            
        col_source = col_source_cand[0]
        col_prio = col_prio_cand[0]
        df_prioridades_raw['SOURCE_CLN'] = df_prioridades_raw[col_source].apply(limpiar_cruce)
        df_prioridades_raw[col_prio] = pd.to_numeric(df_prioridades_raw[col_prio], errors='coerce').fillna(999)
        mapa_prioridad = dict(zip(df_prioridades_raw['SOURCE_CLN'], df_prioridades_raw[col_prio]))

        print("  - Cargando archivo SMART KITS y ADD-WORKS...")
        file_sk = rutas.get("Smart_Kits")
        if not file_sk: raise KeyError("No se ha definido la ruta 'Smart_Kits'.")
        df_sk_raw = pd.read_excel(file_sk, sheet_name=0, dtype=str, header=1)
        df_sk_raw.columns = df_sk_raw.columns.astype(str).str.strip().str.upper()
        col_ref_sk_cand = [c for c in df_sk_raw.columns if 'REFERENCE' in c]
        col_pn_sk_cand = [c for c in df_sk_raw.columns if 'PN' in c or 'P/N' in c]
        if not col_ref_sk_cand or not col_pn_sk_cand: raise ValueError("Faltan columnas en Smart Kits.")
        df_sk_raw['REF_6_DIGITOS'] = df_sk_raw[col_ref_sk_cand[0]].apply(limpiar_6_digitos)
        df_sk_raw['PN_LIMPIO'] = df_sk_raw[col_pn_sk_cand[0]].apply(limpiar_cruce)
        mapa_sk = df_sk_raw.groupby('REF_6_DIGITOS')['PN_LIMPIO'].apply(set).to_dict()

        file_addworks = rutas.get("Add_Works")
        cat_addworks = {} 
        if file_addworks and os.path.exists(file_addworks):
            xls_addworks = pd.ExcelFile(file_addworks)
            hojas_validas = [h for h in xls_addworks.sheet_names if 'ENGINE' in h.upper() or 'PROPELLER' in h.upper()]
            for hoja in hojas_validas:
                df_aw_raw = pd.read_excel(file_addworks, sheet_name=hoja, dtype=str)
                df_aw_raw.columns = df_aw_raw.columns.astype(str).str.strip().str.upper()
                col_aw_ruta = next((c for c in df_aw_raw.columns if 'RUTA' in c and 'LOCAL' in c), None)
                col_aw_op = next((c for c in df_aw_raw.columns if 'OPERACI' in c and 'JC' in c), None)
                col_aw_pelicano = next((c for c in df_aw_raw.columns if 'PEL' in c and 'CANO' in c), None)
                if col_aw_ruta and col_aw_op and col_aw_pelicano:
                    for _, row_aw in df_aw_raw.iterrows():
                        r_aw = limpiar_ruta(row_aw[col_aw_ruta])
                        o_aw = limpiar_cruce(row_aw[col_aw_op])
                        desc_pelicano = limpiar_cruce(row_aw[col_aw_pelicano])
                        if r_aw and o_aw and desc_pelicano:
                            cat_addworks[f"{r_aw}-{o_aw}"] = desc_pelicano

        # -------------------------------------------------------------
        # CATÁLOGO OCCAR (ARCHIVO INDEPENDIENTE). Existe la posibilidad de que haya una columna 'OCCAR == YES/NO' en el 'Análisis de la PD'
        # -------------------------------------------------------------
        print("  - Cargando Catálogo OCCAR independiente...")
        file_occar = rutas.get("Catalogo_OCCAR")
        rutas_rev_occar = set()
        
        if file_occar and os.path.exists(file_occar):
            df_occar_raw = pd.read_excel(file_occar, dtype=str)
            df_occar_raw.columns = df_occar_raw.columns.astype(str).str.strip().str.upper()
            
            col_ruta_occ_cand = [c for c in df_occar_raw.columns if 'RUTA' in c]
            col_rev_occ_cand = [c for c in df_occar_raw.columns if 'REV' in c]
            
            if col_ruta_occ_cand:
                col_r_occ = col_ruta_occ_cand[0]
                col_v_occ = col_rev_occ_cand[0] if col_rev_occ_cand else df_occar_raw.columns[list(df_occar_raw.columns).index(col_r_occ) + 1]
                rutas_rev_occar = set(df_occar_raw[col_r_occ].dropna().apply(limpiar_ruta) + "-" + df_occar_raw[col_v_occ].dropna().apply(limpiar_rev))
        else:
            print("    [!] Archivo Catalogo_OCCAR no proporcionado. Se asume que no hay operaciones OCCAR.")

        # -------------------------------------------------------------
        # 3. LANZAMIENTO Y CREACIÓN DE LANZ_DICT
        # -------------------------------------------------------------
        df_lanz_bruto.columns = df_lanz_bruto.columns.str.strip().str.upper()
        df_quotation.columns = df_quotation.columns.str.strip().str.upper()

        df_lanz_bruto['LLAVE_CRUCE'] = df_lanz_bruto['ITEM'].apply(limpiar_cruce)
        df_quotation['LLAVE_CRUCE'] = df_quotation['ITEM REF'].apply(limpiar_cruce)
        
        col_sh_cand = [c for c in df_lanz_bruto.columns if 'SOURCE' in str(c).upper() and 'HOUR' in str(c).upper()]
        if col_sh_cand: df_lanz_bruto.rename(columns={col_sh_cand[0]: 'SOURCE HOURS'}, inplace=True)
            
        col_task_cand = [c for c in df_lanz_bruto.columns if 'TASK' in c and 'REF' in c]
        nombre_task = col_task_cand[0] if col_task_cand else 'TASK REFERENCE'
        if nombre_task not in df_lanz_bruto.columns: df_lanz_bruto[nombre_task] = "" 
            
        df_lanz_cruzado = df_lanz_bruto.copy()
        df_lanz_cruzado = df_lanz_cruzado.loc[:, ~df_lanz_cruzado.columns.duplicated()]
        df_lanz_cruzado.rename(columns=lambda x: 'RUTA LOCAL' if 'RUTA' in x and 'LOCAL' in x else x, inplace=True)
        
        df_lanz_ok = df_lanz_cruzado[df_lanz_cruzado['FLAG_APLICABILIDAD'].astype(str).str.strip().str.upper() == 'Y'].copy()
        print(f"    * Rutas válidas identificadas como 'Y' en Lanzamiento: {len(df_lanz_ok)}")

        if df_lanz_ok.empty:
            print("[!] No hay rutas aplicables para procesar (todas son out). Abortando fase.")
            return

        pos_ruta = [i for i, col in enumerate(df_lanz_ok.columns) if col == 'RUTA LOCAL'][0]
        col_ruta_lanz = df_lanz_ok.columns[pos_ruta]
        col_rev_lanz = df_lanz_ok.columns[pos_ruta + 1]

        df_lanz_ok[col_rev_lanz] = df_lanz_ok[col_rev_lanz].apply(limpiar_rev)
        df_lanz_ok['LLAVE_RutaRev'] = df_lanz_ok[col_ruta_lanz].apply(limpiar_ruta) + "-" + df_lanz_ok[col_rev_lanz].apply(limpiar_rev)
        claves_lanzamiento = set(df_lanz_ok['LLAVE_RutaRev'].unique())

        def agrupar_atributos(x):
            return {
                'P/N': juntar_unicos(x['P/N']),
                'S/N': juntar_unicos(x['S/N']),
                'SOURCE HOURS': juntar_unicos(x.get('SOURCE HOURS', x.get('Source Hour', ''))),
                'TASK_REF': juntar_unicos(x[nombre_task]),
                'DOC_TYPE': juntar_unicos(x.get(nombre_doc_type, ''))
            }
        df_lanz_ok['KEY_LANZ'] = df_lanz_ok[col_ruta_lanz].apply(limpiar_ruta) + "-" + df_lanz_ok[col_rev_lanz].apply(limpiar_rev)
        try:
            lanz_dict = df_lanz_ok.groupby('KEY_LANZ').apply(agrupar_atributos, include_groups=False).to_dict()
        except TypeError:
            lanz_dict = df_lanz_ok.groupby('KEY_LANZ').apply(agrupar_atributos).to_dict()

        # -------------------------------------------------------------
        # 4. OPERACIONES (FASE 0 Y 1)
        # -------------------------------------------------------------
        cols_op_upper = df_operaciones_raw.columns.str.strip().str.upper()
        pos_ruta_op = [i for i, col in enumerate(cols_op_upper) if col == 'RUTA LOCAL'][0]
        col_ruta_op = df_operaciones_raw.columns[pos_ruta_op]
        col_rev_op = df_operaciones_raw.columns[pos_ruta_op + 1]

        df_operaciones_raw[col_rev_op] = df_operaciones_raw[col_rev_op].apply(limpiar_rev)
        df_operaciones_raw['LLAVE_RutaRev'] = df_operaciones_raw[col_ruta_op].apply(limpiar_ruta) + "-" + df_operaciones_raw[col_rev_op].apply(limpiar_rev)
        
        df_operaciones = df_operaciones_raw[df_operaciones_raw['LLAVE_RutaRev'].isin(claves_lanzamiento)].copy()
        
        col_lanzar_cand = [c for c in df_operaciones.columns if str(c).strip().upper() == 'LANZAR']
        if col_lanzar_cand:
            print(f"    * Columna '{col_lanzar_cand[0]}' detectada en Operaciones. Filtrando por YES/SI...")
            filtro_yes = df_operaciones[col_lanzar_cand[0]].astype(str).str.strip().str.upper().isin(['YES', 'SI'])
            df_operaciones = df_operaciones[filtro_yes].copy()
            print(f"    * Operaciones restantes tras el filtro LANZAR: {len(df_operaciones)}")

        patrones_validos = ['OT', 'BT', 'RMV', 'INS', 'ITL', 'SVC', 'RPL', 'APURUN', 'EGR', 'HPGC', 'LPGC', 'ACC', 'CLOSE-UP', 'CLOSE UP', 'CLOSEUP','SET-UP', 'SET UP', 'SETUP']
        patrones_ejecutables = ['ITL ALU', 'ADM', 'LKC VCS', 'LKC PP VCS', 'LKC TCS', 'LKC TCS HPGC/APU', 'REPORT', 'LKC AGS', 'LKC ALU APU', 'LKC ALU EGR', 'LKC ALU HPGC', 'SW', 'SOFTWARE']
        
        ops_validas = []
        ops_ignoradas = [] 
        
        for idx, row in df_operaciones.iterrows():
            nombre_op = re.sub(r'\s+', ' ', str(row['Nombre Operación'])).strip().upper()
            desc_op_original = str(row['Descripción Operación']).strip().upper()

            # --- LIMPIEZA TOTAL DE SUBTASK (NOMBRE Y DESCRIPCIÓN) ---
            nombre_op = re.sub(r'SUBTASK\s*[\d\-]+\s*(?:-\s*)?', '', nombre_op).strip()
            desc_op_original = re.sub(r'SUBTASK\s*[\d\-]+\s*(?:-\s*)?', '', desc_op_original).strip()
            # --------------------------------------------------------
            
            if any(p_ex in nombre_op for p_ex in patrones_ejecutables):
                row_dict = row.to_dict()
                row_dict['MOTIVO_RECHAZO'] = "Patron ejecutable directo, sin sinergia, (ej. ITL ALU, ADM, SW)"
                ops_ignoradas.append(row_dict)
                continue
            
            patron_encontrado = None
            for patron in patrones_validos:
                if re.search(r'\b' + re.escape(patron), nombre_op):
                    patron_encontrado = patron; break 
            
            if patron_encontrado:
                row_dict = row.to_dict()
                row_dict['PATRON_DETECTADO'] = patron_encontrado 
                # Guardamos las versiones limpias de subtask para no volver a hacerlo luego
                row_dict['Nombre Operación'] = nombre_op
                row_dict['Descripción Operación'] = desc_op_original
                ops_validas.append(row_dict)
            else:
                row_dict = row.to_dict()
                row_dict['MOTIVO_RECHAZO'] = "Sin patron valido (No es OT, BT, RMV, etc.)"
                ops_ignoradas.append(row_dict)
                
        df_ops_validas = pd.DataFrame(ops_validas)
        df_ops_ignoradas = pd.DataFrame(ops_ignoradas)

        if not df_ops_ignoradas.empty:
            ruta_ign = os.path.join(carpeta_outputs, "Operaciones_Ignoradas_Fase0.xlsx")
            df_ops_ignoradas.drop(columns=['LLAVE_RutaRev'], errors='ignore').to_excel(ruta_ign, index=False)
            print(f"  - Guardadas **{len(df_ops_ignoradas)}** operaciones ignoradas por filtro.")
            
        if df_ops_validas.empty:
            print("[!] No hay operaciones válidas para procesar.")
            return

        df_ops_validas['DESC_LIMPIA'] = df_ops_validas['Descripción Operación'].astype(str).str.upper()
        df_ops_validas['ESTACION_LIMPIA'] = df_ops_validas['Est. Trab.'].apply(limpiar_cruce)
        df_ops_validas['DESC_LIMPIA'] = df_ops_validas['DESC_LIMPIA'].replace(r'[^A-Z0-9]', '', regex=True)

        # -------------------------------------------------------------
        # 5. DOCUMENTOS, PURGA Y MATERIALES
        # -------------------------------------------------------------
        col_rev_doc = [c for c in df_documentos_raw.columns if 'REV' in c.upper()][0]
        df_documentos_raw[col_rev_doc] = df_documentos_raw[col_rev_doc].apply(limpiar_rev)
        
        df_ops_validas['LLAVE_RutaRevOp'] = (
            df_ops_validas[col_ruta_op].apply(limpiar_ruta) + "-" + 
            df_ops_validas[col_rev_op].apply(limpiar_rev) + "-" + 
            df_ops_validas['Operación'].apply(limpiar_cruce)
        )
        claves_op_final = set(df_ops_validas['LLAVE_RutaRevOp'].unique())

        col_ruta_doc = [c for c in df_documentos_raw.columns if 'RUTA' in c.upper()][0]
        df_documentos_raw['LLAVE_RutaRevOp'] = df_documentos_raw[col_ruta_doc].apply(limpiar_ruta) + "-" + df_documentos_raw[col_rev_doc].apply(limpiar_rev) + "-" + df_documentos_raw['Operación'].apply(limpiar_cruce)
        df_documentos = df_documentos_raw[df_documentos_raw['LLAVE_RutaRevOp'].isin(claves_op_final)].copy()

        # =========================================================================
        # LÓGICA DE ELIMINACIÓN DE DOCUMENTOS PRINCIPALES
        # =========================================================================
        print("  - Identificando y purgando documentos principales (SB/AOT/VSB)...")
        col_num_doc = 'Nº Documento' if 'Nº Documento' in df_documentos.columns else [c for c in df_documentos.columns if 'Nº DOC' in c.upper()][0]
        col_tit_doc = 'Título Documento' if 'Título Documento' in df_documentos.columns else [c for c in df_documentos.columns if 'TÍTULO' in c.upper()][0]

        indices_a_eliminar = []
        deleted_docs_info = {}

        def limpiar_alfanum(texto):
            return re.sub(r'[^A-Z0-9]', '', str(texto).upper())

        for idx, row in df_documentos.iterrows():
            r = limpiar_ruta(row[col_ruta_doc])
            rev = limpiar_rev(row[col_rev_doc])
            llave_busqueda = f"{r}-{rev}"
            llave_op = row['LLAVE_RutaRevOp']
            
            num_doc_crudo = str(row[col_num_doc])
            num_doc_cln = limpiar_alfanum(num_doc_crudo)
            
            attr = lanz_dict.get(llave_busqueda, {})
            task_ref_crudo = str(attr.get('TASK_REF', ''))
            task_ref_cln = limpiar_alfanum(task_ref_crudo)
            
            doc_types_str = str(attr.get('DOC_TYPE', ''))
            doc_types = [dt.strip().upper() for dt in doc_types_str.split(',')] if doc_types_str else []
            
            eliminar = False
            doc_type_matched = ""
            
            for dtype in doc_types:
                if dtype in ['AOT', 'SB']:
                    if len(task_ref_cln) >= 6 and len(num_doc_cln) >= 6:
                        if task_ref_cln[-6:] == num_doc_cln[-6:]:
                            eliminar = True
                            doc_type_matched = dtype
                            break
                elif dtype == 'VSB':
                    if len(task_ref_cln) >= 9 and len(num_doc_cln) >= 9:
                        if task_ref_cln[-9:] == num_doc_cln[-9:]:
                            eliminar = True
                            doc_type_matched = dtype
                            break
            
            if eliminar:
                indices_a_eliminar.append(idx)
                if llave_op not in deleted_docs_info:
                    deleted_docs_info[llave_op] = {
                        'DOC_TYPE_ELIMINADO': doc_type_matched,
                        'NUM_DOC_ELIMINADO': num_doc_crudo,
                        'TITULO_DOC_ELIMINADO': str(row[col_tit_doc])
                    }

        df_documentos = df_documentos.drop(indices_a_eliminar)
        print(f"    * Eliminados {len(indices_a_eliminar)} registros de documentos principales.")
        # =========================================================================

        col_rev_mat = [c for c in df_materiales_raw.columns if 'REV' in c.upper()][0]
        col_ruta_mat = [c for c in df_materiales_raw.columns if 'RUTA' in c.upper()][0]
        col_tipo_mat = [c for c in df_materiales_raw.columns if 'TIPO' in c.upper()][0]
        col_pieza_mat = [c for c in df_materiales_raw.columns if 'PIEZA' in c.upper()][0]
        col_cant_mat = [c for c in df_materiales_raw.columns if 'CANTIDAD' in c.upper()][0]
        
        col_obs_mat_cand = [c for c in df_materiales_raw.columns if 'OBSERVACION' in c.upper()]
        col_obs_mat = col_obs_mat_cand[0] if col_obs_mat_cand else None

        df_materiales_raw[col_rev_mat] = df_materiales_raw[col_rev_mat].apply(limpiar_rev)
        df_materiales_raw['LLAVE_RutaRevOp'] = df_materiales_raw[col_ruta_mat].apply(limpiar_ruta) + "-" + df_materiales_raw[col_rev_mat].apply(limpiar_rev) + "-" + df_materiales_raw['Operación'].apply(limpiar_cruce)
        
        tipos_validos = ['MATERIAL', 'LIST. MAT.']
        filtro_tipo = df_materiales_raw[col_tipo_mat].astype(str).str.strip().str.upper().isin(tipos_validos)
        claves_con_material_valido = set(df_materiales_raw[filtro_tipo]['LLAVE_RutaRevOp'])
        
        if col_obs_mat:
            filtro_kit = df_materiales_raw[col_obs_mat].astype(str).str.upper().str.contains('KIT', na=False)
            claves_con_kit = set(df_materiales_raw[filtro_kit]['LLAVE_RutaRevOp'])
        else:
            claves_con_kit = set()
        
        df_materiales_raw['CANTIDAD_NUM'] = pd.to_numeric(df_materiales_raw[col_cant_mat].astype(str).str.replace(',', '.').str.extract(r'([\d\.]+)')[0], errors='coerce').fillna(0)
        df_materiales_raw['PIEZA_LIMPIA'] = df_materiales_raw[col_pieza_mat].apply(limpiar_cruce)
        
        mats_agrupados = df_materiales_raw[df_materiales_raw['PIEZA_LIMPIA'] != ""].groupby(['LLAVE_RutaRevOp', 'PIEZA_LIMPIA'])['CANTIDAD_NUM'].sum().reset_index()

        dict_cantidades_mat = {}
        for _, row in mats_agrupados.iterrows():
            llave = row['LLAVE_RutaRevOp']
            pieza = row['PIEZA_LIMPIA']
            cant = row['CANTIDAD_NUM']
            if llave not in dict_cantidades_mat: dict_cantidades_mat[llave] = {}
            dict_cantidades_mat[llave][pieza] = cant

        df_documentos['KEY'] = df_documentos[col_ruta_doc].apply(limpiar_ruta) + "-" + df_documentos[col_rev_doc].apply(limpiar_rev) + "-" + df_documentos['Operación'].apply(limpiar_cruce)
        
        # --- NUEVA LÓGICA: AGRUPACIÓN DE CONJUNTOS POR Nº DE DOCUMENTO ---
        docs_map = df_documentos.groupby('KEY')[col_num_doc].apply(lambda x: set(x.str.upper().str.strip())).to_dict()
        # -----------------------------------------------------------------

        # Creamos el diccionario de info para TODAS las operaciones
        todas_las_operaciones_global = {}
        for _, row in df_ops_validas.iterrows():
            r = limpiar_ruta(row[col_ruta_op])
            rv = limpiar_rev(row[col_rev_op])
            o = limpiar_cruce(row['Operación'])
            key_op = f"{r}-{rv}-{o}"
            llave_busqueda = f"{r}-{rv}"
            
            attr = lanz_dict.get(llave_busqueda, {})
            pn = str(attr.get('P/N', '')).strip().upper()
            sn = str(attr.get('S/N', '')).strip().upper()
            sh = str(attr.get('SOURCE HOURS', '')).strip().upper()
            task_ref_crudo = str(attr.get('TASK_REF', '')).strip().upper()
            doc_type_crudo = str(attr.get('DOC_TYPE', '')).strip().upper()
            
            prioridad_detectada = 999
            for s in sh.split(','):
                s_limpio = limpiar_cruce(s)
                if s_limpio in mapa_prioridad:
                    prioridad_detectada = mapa_prioridad[s_limpio]
                    break
            
            # Recordar que ya lo limpiamos de subtasks arriba
            nombre_op = str(row['Nombre Operación']).strip().upper()
            desc_op_original = str(row['Descripción Operación']).strip().upper()
            desc_limpia_cruce = str(row['DESC_LIMPIA']).strip().upper()

            es_core = "CORE" in nombre_op

            tiene_pn_m = any(p.strip().startswith('M') for p in pn.split(',') if p.strip())
            tiene_tipo_valido = key_op in claves_con_material_valido
            
            cambia_config_sk = False
            task_ref_6 = limpiar_6_digitos(task_ref_crudo)
            if task_ref_6 in mapa_sk:
                pns_validos_sk = mapa_sk[task_ref_6]
                materiales_op = set(dict_cantidades_mat.get(key_op, {}).keys())
                if materiales_op.intersection(pns_validos_sk):
                    cambia_config_sk = True

            llave_aw_check = f"{r}-{o}"
            doc_eliminado = deleted_docs_info.get(key_op, {})

            es_op_occar = f"{r}-{rv}" in rutas_rev_occar

            info = {
                "id": key_op, "ruta": r, "rev": rv, "op": o, "nombre": nombre_op, "desc": desc_op_original,
                "desc_limpia": desc_limpia_cruce,
                "estacion": limpiar_cruce(row['Est. Trab.']), "pn": pn, "sn": sn, "sh": sh,
                "prioridad": prioridad_detectada, "es_occar": es_op_occar,
                
                "doc_type": doc_type_crudo, 
                "cambia_config_sk": cambia_config_sk,
                "tiene_kit": key_op in claves_con_kit, 
                "es_addworks": llave_aw_check in cat_addworks,
                "desc_pelicano": cat_addworks.get(llave_aw_check, ""),
                
                "doc_type_eliminado": doc_eliminado.get('DOC_TYPE_ELIMINADO', ''),
                "num_doc_eliminado": doc_eliminado.get('NUM_DOC_ELIMINADO', ''),
                "titulo_doc_eliminado": doc_eliminado.get('TITULO_DOC_ELIMINADO', ''),
                
                "pn_m": tiene_pn_m and tiene_tipo_valido, 
                "tiene_pn_sn": pn != "" and sn != "",
                "tiempo": float(str(row['T. Producción']).replace(',','.')) if pd.notna(row['T. Producción']) else 0.0,
                "es_core": es_core,
                "cambia_config": "PARTIAL" in nombre_op or "PARTIAL" in desc_op_original,
                "docs": docs_map.get(key_op, set()),
                "docs_str": f"({len(docs_map.get(key_op, set()))}) " + ", ".join(str(doc) for doc in docs_map.get(key_op, set())) if key_op in docs_map else "(0) Sin docs",
                
                "materiales_dict": dict_cantidades_mat.get(key_op, {})
            }
            todas_las_operaciones_global[key_op] = info

        def obtener_motivo_c1(op):
            if "HTI" in op["nombre"] or "HARD TIME" in op["nombre"]: return "Cambio de configuración: HTI"
            if op["pn_m"]: return "Cambio de configuración: Material M"
            if op["cambia_config_sk"]: return "Cambio de configuración: pertenece a smart kit"
            if op["tiene_kit"]: return "Cambio de configuración: contiene kit en observaciones"
            return "Cambio de configuración"

        def formato_res_aw(p, h, mot, ev_dict, grp_name):
            dict_p = p.get("materiales_dict", {})
            dict_h = h.get("materiales_dict", {})
            
            # --- NUEVA LÓGICA: Formatear string de materiales y cantidades ---
            mat_p_str = ", ".join([f"{k} (Cant: {v})" for k, v in dict_p.items()]) if dict_p else "Sin materiales"
            mat_h_str = ", ".join([f"{k} (Cant: {v})" for k, v in dict_h.items()]) if dict_h else "Sin materiales"
            # -----------------------------------------------------------------
            
            if not dict_p and not dict_h: warning_mat = 'Ni padre ni hijo requieren material'
            elif not dict_p and dict_h: warning_mat = 'El padre no requiere materiales pero el hijo si'
            else:
                materiales_incluidos = chequear_materiales_incluidos(dict_p, dict_h)
                if materiales_incluidos:
                    warning_mat = "Los materiales del hijo están incluidos en los del padre"
                else:
                    motivo = obtener_motivo_fallo_materiales(dict_p, dict_h)
                    warning_mat = f"Los materiales del hijo NO están incluidos en los del padre ({motivo})"

            res = {
                "Operacion_Pelicano_Grupo": grp_name, "Resultado_Final": f"PADRE: {p['id']} -> HIJA: {h['id']}", "Motivo": mot,
                "Warning_Materiales": warning_mat,
                "Op_A_Materiales_Cant": mat_p_str, # <--- AÑADIDO
                "Op_B_Materiales_Cant": mat_h_str, # <--- AÑADIDO
                "id_padre_temp": p['id'], "id_hija_temp": h['id'],
                "Op_A_Ruta": p["ruta"], "Op_A_Rev": p["rev"], "Op_A_Op": p["op"], 
                "Op_A_Nombre": p["nombre"], "Op_A_Desc": p["desc"],
                "Docs_A": p['docs_str'],
                "Op_B_Ruta": h["ruta"], "Op_B_Rev": h["rev"], "Op_B_Op": h["op"], 
                "Op_B_Nombre": h["nombre"], "Op_B_Desc": h["desc"],
                "Docs_B": h['docs_str']
            }
            res.update(ev_dict)
            return res

        print("\n" + "-" * 70)
        print("**[ INICIANDO FASE 1.5 ] RED ADD-WORKS (ENGINE/PROPELLER)**")
        print("-" * 70)
        
        operaciones_excluidas_addworks = set()
        resultados_addworks = []
        grupos_aw = {}

        for key, info in todas_las_operaciones_global.items():
            if info["es_addworks"]:
                clave_aw = info["desc_pelicano"]
                if clave_aw not in grupos_aw: grupos_aw[clave_aw] = []
                grupos_aw[clave_aw].append(info)
            else:
                for desc_pel in cat_addworks.values():
                    if info["desc"] == desc_pel:
                        if desc_pel not in grupos_aw: grupos_aw[desc_pel] = []
                        grupos_aw[desc_pel].append(info)
                        break 

        print(f"  - Resolviendo {len(grupos_aw)} grupos de combates Add-Works...")
        ops_aw_que_combatieron = set()

        for clave_pelicano, ops_aw in grupos_aw.items():
            if len(ops_aw) < 2: continue
            
            ids_g = [o['id'] for o in ops_aw]
            for i in range(len(ids_g)):
                for j in range(i+1, len(ids_g)):
                    a, b = todas_las_operaciones_global[ids_g[i]], todas_las_operaciones_global[ids_g[j]]
                    if a['ruta'] == b['ruta']: continue
                    if not a["es_addworks"] and not b["es_addworks"]: continue
                        
                    ops_aw_que_combatieron.update([a['id'], b['id']])
                    ev = obtener_evidencias_vacias()
                    match = None
                    
                    a_c1 = "HTI" in a["nombre"] or "HARD TIME" in a["nombre"] or a["pn_m"] or a["cambia_config_sk"] or a["tiene_kit"]
                    b_c1 = "HTI" in b["nombre"] or "HARD TIME" in b["nombre"] or b["pn_m"] or b["cambia_config_sk"] or b["tiene_kit"]
                    
                    if a_c1 and b_c1: continue 
                    if a_c1 and not a["es_addworks"] and b["es_addworks"]: continue
                    if b_c1 and not b["es_addworks"] and a["es_addworks"]: continue
                    
                    if a_c1 and not b_c1: 
                        motivo = obtener_motivo_c1(a)
                        ev["Evidencia_C1_HTI"] = motivo
                        match = formato_res_aw(a, b, "C1: Padre cambia Configuración", ev, clave_pelicano)
                    elif b_c1 and not a_c1: 
                        motivo = obtener_motivo_c1(b)
                        ev["Evidencia_C1_HTI"] = motivo
                        match = formato_res_aw(b, a, "C1: Padre cambia Configuración", ev, clave_pelicano)
                    else:
                        if a["es_addworks"] and not b["es_addworks"]:
                            match = formato_res_aw(a, b, "C2: Padre es Operación Add-Works", ev, clave_pelicano)
                        elif b["es_addworks"] and not a["es_addworks"]:
                            match = formato_res_aw(b, a, "C2: Padre es Operación Add-Works", ev, clave_pelicano)
                        else:
                            match = formato_res_aw(a, b, "fallo de industrialización: dos operaciones de la JC no pueden cumplimentarse", ev, clave_pelicano)
                            match["Resultado_Final"] = "NO CUMPLIMENTADAS"

                    if match: resultados_addworks.append(match)
        
        for key, info in todas_las_operaciones_global.items():
            if info["es_addworks"] and key not in ops_aw_que_combatieron:
                ev = obtener_evidencias_vacias()
                res_indep_aw = {
                    "Operacion_Pelicano_Grupo": info["desc_pelicano"], "Resultado_Final": "SIN SINERGIA - ADD-WORKS", 
                    "Motivo": "Independiente en Fase Add-Works", "Warning_Materiales": "-",
                    "Op_A_Materiales_Cant": mat_p_str,
                    "Op_B_Materiales_Cant": "-",
                    "id_padre_temp": info['id'], "id_hija_temp": None,
                    "Op_A_Ruta": info["ruta"], "Op_A_Rev": info["rev"], "Op_A_Op": info["op"], 
                    "Op_A_Nombre": info["nombre"], "Op_A_Desc": info["desc"], "Docs_A": info['docs_str'],
                    "Op_B_Ruta": "-", "Op_B_Rev": "-", "Op_B_Op": "-", "Op_B_Nombre": "-", "Op_B_Desc": "-", "Docs_B": "-"
                }
                res_indep_aw.update(ev)
                resultados_addworks.append(res_indep_aw)
        
        if resultados_addworks:
            pd.DataFrame(resultados_addworks).drop(columns=['id_padre_temp', 'id_hija_temp'], errors='ignore').to_excel(os.path.join(carpeta_outputs, "Resultados_AddWorks_Trazabilidad.xlsx"), index=False)
            print(f"  - Guardado Resultados_AddWorks_Trazabilidad.xlsx con toda la trazabilidad.")
            
            for r in resultados_addworks:
                if r.get('id_hija_temp'): operaciones_excluidas_addworks.add(r['id_hija_temp'])

        for key, info in todas_las_operaciones_global.items():
            if info["es_addworks"]: operaciones_excluidas_addworks.add(key)


        print("\n" + "-" * 70)
        print("**[ INICIANDO FASE 1.8 ] RED SB SET-UP (JOB SETUP / CLOSE UP)**")
        print("-" * 70)

        grupos_sb_closeup = {}
        grupos_sb_jobsetup = {}
        operaciones_excluidas_sb = set()

        for key, info in todas_las_operaciones_global.items():
            if key in operaciones_excluidas_addworks: continue
            
            nombre_op = info['nombre']
            texto_completo = nombre_op + " " + info['desc']
            doc_type_val = info.get('doc_type', '')
            
            if re.search(r'\bSB\b', doc_type_val):
                if "CLOSE UP" in texto_completo or "CLOSE-UP" in texto_completo or "CLOSEUP" in texto_completo:
                    clave_g = ("SB CLOSE-UP", info["desc_limpia"])
                    if clave_g not in grupos_sb_closeup: grupos_sb_closeup[clave_g] = []
                    grupos_sb_closeup[clave_g].append(info)
                    operaciones_excluidas_sb.add(key)
                    info["tipo_especial"] = "SB CLOSE-UP"
                    
                elif "SET UP" in texto_completo or "SET-UP" in texto_completo or "SETUP" in texto_completo:
                    clave_g = ("SB JOB SET-UP", info["desc_limpia"])
                    if clave_g not in grupos_sb_jobsetup: grupos_sb_jobsetup[clave_g] = []
                    grupos_sb_jobsetup[clave_g].append(info)
                    operaciones_excluidas_sb.add(key)
                    info["tipo_especial"] = "SB JOB SET-UP"

        print(f"  - Grupos de Close-up encontrados: {len(grupos_sb_closeup)}")
        print(f"  - Grupos de Job Setup encontrados: {len(grupos_sb_jobsetup)}")

        def evaluar_cascada_normal(a, b, ev):
            a_c1 = "HTI" in a["nombre"] or "HARD TIME" in a["nombre"] or a["pn_m"] or a["cambia_config_sk"] or a["tiene_kit"]
            b_c1 = "HTI" in b["nombre"] or "HARD TIME" in b["nombre"] or b["pn_m"] or b["cambia_config_sk"] or b["tiene_kit"]
            
            if a_c1 and b_c1: return None, None, None
            if a_c1 and not b_c1: 
                motivo = obtener_motivo_c1(a)
                ev["Evidencia_C1_HTI"] = motivo
                return a, b, motivo
            if b_c1 and not a_c1: 
                motivo = obtener_motivo_c1(b)
                ev["Evidencia_C1_HTI"] = motivo
                return b, a, motivo

            if not a["tiene_pn_sn"] and b["tiene_pn_sn"]: ev["Evidencia_C2_PNSN"] = "PADRE no específico"; return a, b, "C2: Padre es tarea genérica"
            if not b["tiene_pn_sn"] and a["tiene_pn_sn"]: ev["Evidencia_C2_PNSN"] = "PADRE no específico"; return b, a, "C2: Padre es tarea genérica"

            if a["es_occar"] and not b["es_occar"]: ev["Evidencia_C3_OCCAR"] = "PADRE es OCCAR"; return a, b, "C3: Padre está en Catálogo OCCAR"
            if b["es_occar"] and not a["es_occar"]: ev["Evidencia_C3_OCCAR"] = "PADRE es OCCAR"; return b, a, "C3: Padre está en Catálogo OCCAR"

            if a["prioridad"] < b["prioridad"]: ev["Evidencia_C4_PEP"] = "PADRE mejor Prioridad Source"; return a, b, "C4: Padre gana por Prioridad Source"
            if b["prioridad"] < a["prioridad"]: ev["Evidencia_C4_PEP"] = "PADRE mejor Prioridad Source"; return b, a, "C4: Padre gana por Prioridad Source"

            if a["tiempo"] > b["tiempo"]: ev["Evidencia_C5_Tiempo"] = "PADRE mayor tiempo"; return a, b, "C5: Padre tiene mayor tiempo"
            if b["tiempo"] > a["tiempo"]: ev["Evidencia_C5_Tiempo"] = "PADRE mayor tiempo"; return b, a, "C5: Padre tiene mayor tiempo"
            
            a_incluye_b = chequear_materiales_incluidos(a.get("materiales_dict", {}), b.get("materiales_dict", {}))
            b_incluye_a = chequear_materiales_incluidos(b.get("materiales_dict", {}), a.get("materiales_dict", {}))
            
            if a_incluye_b and not b_incluye_a: return a, b, "C6: Padre incluye materiales del hijo"
            if b_incluye_a and not a_incluye_b: return b, a, "C6: Padre incluye materiales del hijo"

            if a["id"] < b["id"]: return a, b, "C7: Alfabético"
            return b, a, "C7: Alfabético"

        def formato_res_normal(p, h, mot, ev_dict, grp_name):
            dict_p = p.get("materiales_dict", {})
            dict_h = h.get("materiales_dict", {})
            
            # --- NUEVA LÓGICA: Formatear string de materiales y cantidades ---
            mat_p_str = ", ".join([f"{k} (Cant: {v})" for k, v in dict_p.items()]) if dict_p else "Sin materiales"
            mat_h_str = ", ".join([f"{k} (Cant: {v})" for k, v in dict_h.items()]) if dict_h else "Sin materiales"
            # -----------------------------------------------------------------

            if not dict_p and not dict_h: warning_mat = 'Ni padre ni hijo requieren material'
            elif not dict_p and dict_h: warning_mat = 'El padre no requiere materiales pero el hijo si'
            else:
                materiales_incluidos = chequear_materiales_incluidos(dict_p, dict_h)
                if materiales_incluidos:
                    warning_mat = "Los materiales del hijo están incluidos en los del padre"
                else:
                    motivo = obtener_motivo_fallo_materiales(dict_p, dict_h)
                    warning_mat = f"Los materiales del hijo NO están incluidos en los del padre ({motivo})"

            res = {
                "Grupo": grp_name, "Resultado_Final": f"PADRE: {p['id']} -> HIJA: {h['id']}", "Motivo": mot,
                "Warning_Materiales": warning_mat,
                "Op_A_Materiales_Cant": mat_p_str, # <--- AÑADIDO
                "Op_B_Materiales_Cant": mat_h_str, # <--- AÑADIDO
                "id_padre_temp": p['id'], "id_hija_temp": h['id'],
                "Op_A_Ruta": p["ruta"], "Op_A_Rev": p["rev"], "Op_A_Op": p["op"], 
                "Op_A_Nombre": p["nombre"], "Op_A_Desc": p["desc"], "Op_A_Estacion": p["estacion"],
                "Op_A_Doc_Eliminado_Tipo": p.get("doc_type_eliminado", ""),
                "Op_A_Doc_Eliminado_Num": p.get("num_doc_eliminado", ""),
                "Op_A_Doc_Eliminado_Titulo": p.get("titulo_doc_eliminado", ""),
                "conjunto PN ruta A": p["pn"], "conjunto SN ruta A": p["sn"], "Op_A_SH": p["sh"], "Op_A_Prioridad_Source": p["prioridad"], "Op_A_Tiempo": p["tiempo"],
                "Docs_A": p['docs_str'],
                "Op_B_Ruta": h["ruta"], "Op_B_Rev": h["rev"], "Op_B_Op": h["op"], 
                "Op_B_Nombre": h["nombre"], "Op_B_Desc": h["desc"], "Op_B_Estacion": h["estacion"],
                "Op_B_Doc_Eliminado_Tipo": h.get("doc_type_eliminado", ""),
                "Op_B_Doc_Eliminado_Num": h.get("num_doc_eliminado", ""),
                "Op_B_Doc_Eliminado_Titulo": h.get("titulo_doc_eliminado", ""),
                "conjunto PN ruta B": h["pn"], "conjunto SN ruta B": h["sn"], "Op_B_SH": h["sh"], "Op_B_Prioridad_Source": h["prioridad"], "Op_B_Tiempo": h["tiempo"],
                "Docs_B": h['docs_str']
            }
            res.update(ev_dict)
            return res

        resultados_sb = []
        operaciones_emparejadas_sb = set()
        for grupos_dict in [grupos_sb_closeup, grupos_sb_jobsetup]:
            for clave, ops in grupos_dict.items():
                if len(ops) < 2: continue
                res_grupo = []
                ids_g = [o['id'] for o in ops]
                # Rescatamos la descripción original legible de la primera operación del grupo
                desc_legible = ops[0]['desc']
                grp_name = f"{clave[0]} | {desc_legible}"
                
                for i in range(len(ids_g)):
                    for j in range(i+1, len(ids_g)):
                        a, b = todas_las_operaciones_global[ids_g[i]], todas_las_operaciones_global[ids_g[j]]
                        if a['ruta'] == b['ruta']: continue
                        
                        ev = obtener_evidencias_vacias()
                        match = None
                        
                        if a['docs'] == b['docs']:
                            if a['cambia_config'] and b['cambia_config']: match = None
                            elif a['cambia_config'] and not b['cambia_config']: match = formato_res_normal(b, a, "Forzado: A tiene prohibición (PARTIAL)", ev, grp_name)
                            elif b['cambia_config'] and not a['cambia_config']: match = formato_res_normal(a, b, "Forzado: B tiene prohibición (PARTIAL)", ev, grp_name)
                            else:
                                p, h, mot = evaluar_cascada_normal(a, b, ev)
                                if p is not None:
                                    ev["Evidencia_Docs"] = "Empate Documental"
                                    match = formato_res_normal(p, h, mot, ev, grp_name)
                        
                        elif a['docs'].issubset(b['docs']) and not b['cambia_config']:
                            ev["Evidencia_Docs"] = "Padre engloba a Hija"
                            match = formato_res_normal(b, a, "Padre engloba a Hija", ev, grp_name)
                        elif b['docs'].issubset(a['docs']) and not a['cambia_config']:
                            ev["Evidencia_Docs"] = "Padre engloba a Hija"
                            match = formato_res_normal(a, b, "Padre engloba a Hija", ev, grp_name)
                            
                        if match: 
                            match["Motivo"] = f"SB: {match['Motivo']}" 
                            res_grupo.append(match)
                        
                if res_grupo:
                    marcador = {idx: {"v": 0, "d": 0} for idx in ids_g}
                    for r in res_grupo: 
                        marcador[r['id_padre_temp']]["v"] += 1
                        marcador[r['id_hija_temp']]["d"] += 1
                    vencedores = [idx for idx, st in marcador.items() if st["d"] == 0 and st["v"] > 0]
                    
                    if vencedores:
                        hijas_asignadas = set() 
                        for p_top in vencedores:
                            hijas_del_padre = [r for r in res_grupo if r['id_padre_temp'] == p_top and r['id_hija_temp'] not in hijas_asignadas]
                            if not hijas_del_padre: continue
                            
                            tiempo_padre = todas_las_operaciones_global[p_top]["tiempo"]
                            tiempo_hijas = sum(todas_las_operaciones_global[r['id_hija_temp']]["tiempo"] for r in hijas_del_padre)
                            t_sin_sinergia = tiempo_padre + tiempo_hijas
                            t_sinergiado = tiempo_padre
                            ahorro = tiempo_hijas
                            
                            for r in hijas_del_padre:
                                r["Tiempo_Grupo_Sin_Sinergiar"] = t_sin_sinergia
                                r["Tiempo_Grupo_Sinergiado"] = t_sinergiado
                                r["Horas_Ahorradas_Grupo"] = ahorro
                                resultados_sb.append(r)
                                hijas_asignadas.add(r['id_hija_temp'])
                                operaciones_emparejadas_sb.update([r['id_padre_temp'], r['id_hija_temp']])

        print("\n" + "-" * 70)
        print("**[ INICIANDO FASE 2 ] RESOLUCIÓN DE CASCADA NORMAL**")
        print("-" * 70)
        
        grupos_normales = {}
        todas_las_operaciones_vivas = {}

        for key, info in todas_las_operaciones_global.items():
            if key in operaciones_excluidas_addworks or key in operaciones_excluidas_sb: continue
            todas_las_operaciones_vivas[key] = info
            
            patron = re.search(r'\b(OT|BT|RMV|INS|ACC|ITL|SVC|RPL|APURUN|EGR|HPGC|LPGC)', info["nombre"])
            if patron:
                clave_g = (patron.group(), info["desc_limpia"])
                if clave_g not in grupos_normales: grupos_normales[clave_g] = []
                grupos_normales[clave_g].append(info)

        print("  - Resolviendo combates normales en tribunal de sinergias...")
        resultados_normales = []
        operaciones_emparejadas_normales = set()
        
        for clave, ops in grupos_normales.items():
            if len(ops) < 2: continue
            res_grupo = []
            ids_g = [o['id'] for o in ops]
            # Rescatamos la descripción original legible
            desc_legible = ops[0]['desc']
            grp_name = f"{clave[0]} | {desc_legible}"
            for i in range(len(ids_g)):
                for j in range(i+1, len(ids_g)):
                    a, b = todas_las_operaciones_vivas[ids_g[i]], todas_las_operaciones_vivas[ids_g[j]]
                    if a['ruta'] == b['ruta']: continue
                    ev = obtener_evidencias_vacias()
                    match = None

                    if a['docs'] == b['docs']:
                        if a['cambia_config'] and b['cambia_config']: match = None
                        elif a['cambia_config'] and not b['cambia_config']: match = formato_res_normal(b, a, "Forzado: A tiene prohibición (PARTIAL)", ev, grp_name)
                        elif b['cambia_config'] and not a['cambia_config']: match = formato_res_normal(a, b, "Forzado: B tiene prohibición (PARTIAL)", ev, grp_name)
                        else:
                            p, h, mot = evaluar_cascada_normal(a, b, ev)
                            if p is not None:
                                ev["Evidencia_Docs"] = "Empate Documental"
                                match = formato_res_normal(p, h, mot, ev, grp_name)
                            else:
                                match = None

                    elif a['docs'].issubset(b['docs']) and not b['cambia_config']:
                        ev["Evidencia_Docs"] = "Padre engloba a Hija"
                        match = formato_res_normal(b, a, "Padre engloba a Hija", ev, grp_name)
                    elif b['docs'].issubset(a['docs']) and not a['cambia_config']:
                        ev["Evidencia_Docs"] = "Padre engloba a Hija"
                        match = formato_res_normal(a, b, "Padre engloba a Hija", ev, grp_name)

                    if match: res_grupo.append(match)

            if res_grupo:
                marcador = {idx: {"v": 0, "d": 0} for idx in ids_g}
                for r in res_grupo: marcador[r['id_padre_temp']]["v"] += 1; marcador[r['id_hija_temp']]["d"] += 1
                vencedores = [idx for idx, st in marcador.items() if st["d"] == 0 and st["v"] > 0]
                if vencedores:
                    p_top = sorted(vencedores, key=lambda x: (marcador[x]["v"], x), reverse=True)[0]
                    
                    tiempo_padre = todas_las_operaciones_vivas[p_top]["tiempo"]
                    tiempo_hijas = sum(todas_las_operaciones_vivas[r['id_hija_temp']]["tiempo"] for r in res_grupo if r['id_padre_temp'] == p_top)
                    t_sin_sinergia = tiempo_padre + tiempo_hijas
                    t_sinergiado = tiempo_padre
                    ahorro = tiempo_hijas

                    for r in res_grupo:
                        if r['id_padre_temp'] == p_top:
                            r["Tiempo_Grupo_Sin_Sinergiar"] = t_sin_sinergia
                            r["Tiempo_Grupo_Sinergiado"] = t_sinergiado
                            r["Horas_Ahorradas_Grupo"] = ahorro
                            resultados_normales.append(r); operaciones_emparejadas_normales.update([r['id_padre_temp'], r['id_hija_temp']])

        resultados_fase2 = resultados_normales + resultados_sb
        operaciones_emparejadas_fase2 = operaciones_emparejadas_normales | operaciones_emparejadas_sb

        # --- FASE: RESTRICCIÓN DE RUTA COMPLETA (Se saca una ruta aleatoria y se lanza warning de descumplimentación) ---
        ops_por_ruta_original = {}
        for key_orig, info_orig in todas_las_operaciones_global.items():
            if key_orig in operaciones_excluidas_addworks: continue
            r_orig = info_orig['ruta']
            if r_orig not in ops_por_ruta_original: ops_por_ruta_original[r_orig] = set()
            ops_por_ruta_original[r_orig].add(key_orig)

        hijas_totales = {r['id_hija_temp'] for r in resultados_fase2 if 'id_hija_temp' in r}
        
        for ruta, ops_orig in ops_por_ruta_original.items():
            if len(ops_orig) > 0 and ops_orig.issubset(hijas_totales):
                op_rescatada = random.choice(list(ops_orig))
                match_a_borrar = next((r for r in resultados_fase2 if r.get('id_hija_temp') == op_rescatada), None)
                if match_a_borrar:
                    padre_id = match_a_borrar['id_padre_temp']
                    t_hija = todas_las_operaciones_global[op_rescatada]['tiempo']
                    resultados_fase2.remove(match_a_borrar)
                    operaciones_emparejadas_fase2.discard(op_rescatada)
                    
                    padre_tiene_mas_hijos = False
                    for r in resultados_fase2:
                        if r.get('id_padre_temp') == padre_id:
                            padre_tiene_mas_hijos = True
                            r['Tiempo_Grupo_Sin_Sinergiar'] -= t_hija
                            r['Horas_Ahorradas_Grupo'] -= t_hija
                    if not padre_tiene_mas_hijos: operaciones_emparejadas_fase2.discard(padre_id)
                        
                relacion_rota = f"PADRE: {padre_id} -> HIJA: {op_rescatada}"
                texto_motivo = f"Relación descumplimentada ({relacion_rota}). Esta ruta se ha cumplimentado de forma completa por lo que esta operación ha sido descumplimentada debido a la restricción de que una ruta no puede cumplimentarse completa. ¿desea cumplimentarla?"
                todas_las_operaciones_global[op_rescatada]['motivo_rescate'] = texto_motivo
                todas_las_operaciones_global[op_rescatada]['resultado_final_rescate'] = "Cumplimentar en el libro"
        
        # Independientes Globales
        for kid, info in todas_las_operaciones_global.items():
            if kid in operaciones_excluidas_addworks: continue
            if kid not in operaciones_emparejadas_fase2:
                ev = obtener_evidencias_vacias()
                patron = re.search(r'\b(OT|BT|RMV|INS|ACC|ITL|SVC|RPL|APURUN|EGR|HPGC|LPGC)', info["nombre"])
                if "tipo_especial" in info:
                    nombre_grupo = f"{info['tipo_especial']} | {info['desc']}"
                    motivo_base = "Independiente (SB No Sinergiada)"
                else:
                    nombre_grupo = f"{patron.group()} | {info['desc']}" if patron else "SIN PATRÓN"
                    motivo_base = "Independiente"
                
                if "motivo_rescate" in info:
                    motivo_indep = info["motivo_rescate"]
                    resultado_final_str = info.get("resultado_final_rescate", "SIN SINERGIA")
                else:
                    motivo_indep = motivo_base; resultado_final_str = "SIN SINERGIA"
                    
                dict_p = info.get("materiales_dict", {})
                mat_p_str = ", ".join([f"{k} (Cant: {v})" for k, v in dict_p.items()]) if dict_p else "Sin materiales"

                ind = {
                    "Grupo": nombre_grupo, "Resultado_Final": resultado_final_str, "Motivo": motivo_indep,
                    "Warning_Materiales": "-", 
                    "Op_A_Materiales_Cant": mat_p_str, # <--- AÑADIDO
                    "Op_B_Materiales_Cant": "-",       # <--- AÑADIDO
                    "Op_A_Ruta": info['ruta'], "Op_A_Rev": info['rev'], "Op_A_Op": info['op'], 
                    "Op_A_Nombre": info['nombre'], "Op_A_Desc": info['desc'], "Op_A_Estacion": info['estacion'],
                    "Op_A_Doc_Eliminado_Tipo": info.get("doc_type_eliminado", ""),
                    "Op_A_Doc_Eliminado_Num": info.get("num_doc_eliminado", ""),
                    "Op_A_Doc_Eliminado_Titulo": info.get("titulo_doc_eliminado", ""),
                    "conjunto PN ruta A": info['pn'], "conjunto SN ruta A": info['sn'], "Op_A_SH": info['sh'], "Op_A_Prioridad_Source": info['prioridad'], "Op_A_Tiempo": info['tiempo'],
                    "Docs_A": info['docs_str'], "Op_B_Ruta": "-", "Op_B_Rev": "-", "Op_B_Op": "-", "Op_B_Nombre": "-", "Op_B_Desc": "-", "Op_B_Estacion": "-",
                    "Op_B_Doc_Eliminado_Tipo": "-", "Op_B_Doc_Eliminado_Num": "-", "Op_B_Doc_Eliminado_Titulo": "-",
                    "conjunto PN ruta B": "-", "conjunto SN ruta B": "-", "Op_B_SH": "-", "Op_B_Prioridad_Source": "-", "Op_B_Tiempo": "-", "Docs_B": "-",
                    "Tiempo_Grupo_Sin_Sinergiar": info['tiempo'], "Tiempo_Grupo_Sinergiado": info['tiempo'], "Horas_Ahorradas_Grupo": 0.0
                }
                ind.update(ev)
                resultados_fase2.append(ind)

        for r_aw in resultados_addworks:
            ev = {k: r_aw.get(k, "-") for k in obtener_evidencias_vacias().keys()}
            ind = {
                "Grupo": r_aw.get("Operacion_Pelicano_Grupo", "-"), "Resultado_Final": r_aw.get("Resultado_Final", ""), "Motivo": r_aw.get("Motivo", ""), "Warning_Materiales": r_aw.get("Warning_Materiales", "-"),
                "Op_A_Ruta": r_aw.get("Op_A_Ruta", ""), "Op_A_Rev": r_aw.get("Op_A_Rev", ""), "Op_A_Op": r_aw.get("Op_A_Op", ""), "Op_A_Nombre": r_aw.get("Op_A_Nombre", ""), "Op_A_Desc": r_aw.get("Op_A_Desc", ""),
                "Op_A_Materiales_Cant": r_aw.get("Op_A_Materiales_Cant", "-"), # <--- AÑADIDO
                "Op_B_Materiales_Cant": r_aw.get("Op_B_Materiales_Cant", "-"),
                "Op_A_Estacion": todas_las_operaciones_global.get(r_aw.get("id_padre_temp", ""), {}).get("estacion", "-"),
                "Op_A_Doc_Eliminado_Tipo": todas_las_operaciones_global.get(r_aw.get("id_padre_temp", ""), {}).get("doc_type_eliminado", "-"),
                "Op_A_Doc_Eliminado_Num": todas_las_operaciones_global.get(r_aw.get("id_padre_temp", ""), {}).get("num_doc_eliminado", "-"),
                "Op_A_Doc_Eliminado_Titulo": todas_las_operaciones_global.get(r_aw.get("id_padre_temp", ""), {}).get("titulo_doc_eliminado", "-"),
                "conjunto PN ruta A": todas_las_operaciones_global.get(r_aw.get("id_padre_temp", ""), {}).get("pn", "-"), "conjunto SN ruta A": todas_las_operaciones_global.get(r_aw.get("id_padre_temp", ""), {}).get("sn", "-"),
                "Op_A_SH": todas_las_operaciones_global.get(r_aw.get("id_padre_temp", ""), {}).get("sh", "-"), "Op_A_Prioridad_Source": todas_las_operaciones_global.get(r_aw.get("id_padre_temp", ""), {}).get("prioridad", "-"), "Op_A_Tiempo": todas_las_operaciones_global.get(r_aw.get("id_padre_temp", ""), {}).get("tiempo", 0.0), "Docs_A": r_aw.get("Docs_A", "-"),
                "Op_B_Ruta": r_aw.get("Op_B_Ruta", "-"), "Op_B_Rev": r_aw.get("Op_B_Rev", "-"), "Op_B_Op": r_aw.get("Op_B_Op", "-"), "Op_B_Nombre": r_aw.get("Op_B_Nombre", "-"), "Op_B_Desc": r_aw.get("Op_B_Desc", "-"),
                "Op_B_Estacion": todas_las_operaciones_global.get(r_aw.get("id_hija_temp", ""), {}).get("estacion", "-") if r_aw.get("id_hija_temp") else "-",
                "Op_B_Doc_Eliminado_Tipo": todas_las_operaciones_global.get(r_aw.get("id_hija_temp", ""), {}).get("doc_type_eliminado", "-") if r_aw.get("id_hija_temp") else "-",
                "Op_B_Doc_Eliminado_Num": todas_las_operaciones_global.get(r_aw.get("id_hija_temp", ""), {}).get("num_doc_eliminado", "-") if r_aw.get("id_hija_temp") else "-",
                "Op_B_Doc_Eliminado_Titulo": todas_las_operaciones_global.get(r_aw.get("id_hija_temp", ""), {}).get("titulo_doc_eliminado", "-") if r_aw.get("id_hija_temp") else "-",
                "conjunto PN ruta B": todas_las_operaciones_global.get(r_aw.get("id_hija_temp", ""), {}).get("pn", "-") if r_aw.get("id_hija_temp") else "-", "conjunto SN ruta B": todas_las_operaciones_global.get(r_aw.get("id_hija_temp", ""), {}).get("sn", "-") if r_aw.get("id_hija_temp") else "-",
                "Op_B_SH": todas_las_operaciones_global.get(r_aw.get("id_hija_temp", ""), {}).get("sh", "-") if r_aw.get("id_hija_temp") else "-", "Op_B_Prioridad_Source": todas_las_operaciones_global.get(r_aw.get("id_hija_temp", ""), {}).get("prioridad", "-") if r_aw.get("id_hija_temp") else "-", "Op_B_Tiempo": todas_las_operaciones_global.get(r_aw.get("id_hija_temp", ""), {}).get("tiempo", "-") if r_aw.get("id_hija_temp") else "-", "Docs_B": r_aw.get("Docs_B", "-"),
                "Tiempo_Grupo_Sin_Sinergiar": todas_las_operaciones_global.get(r_aw.get("id_padre_temp", ""), {}).get("tiempo", 0.0) + (todas_las_operaciones_global.get(r_aw.get("id_hija_temp", ""), {}).get("tiempo", 0.0) if r_aw.get("id_hija_temp") else 0.0),
                "Tiempo_Grupo_Sinergiado": todas_las_operaciones_global.get(r_aw.get("id_padre_temp", ""), {}).get("tiempo", 0.0), "Horas_Ahorradas_Grupo": todas_las_operaciones_global.get(r_aw.get("id_hija_temp", ""), {}).get("tiempo", 0.0) if r_aw.get("id_hija_temp") else 0.0
            }
            ind.update(ev)
            resultados_fase2.append(ind)

        # --- NUEVA LÓGICA: INYECCIÓN DE OPERACIONES IGNORADAS EN EL EXCEL FINAL ---
        # Rescatamos las operaciones filtradas en Fase 0 para que TODO el evento quede reflejado
        for op_ign in ops_ignoradas:
            r_ign = limpiar_ruta(op_ign.get(col_ruta_op, ''))
            rv_ign = limpiar_rev(op_ign.get(col_rev_op, ''))
            o_ign = limpiar_cruce(op_ign.get('Operación', ''))
            llave_busqueda = f"{r_ign}-{rv_ign}"
            
            # Intentamos recuperar datos del diccionario de Lanzamiento si existen
            attr = lanz_dict.get(llave_busqueda, {})
            pn_ign = str(attr.get('P/N', '')).strip().upper()
            sn_ign = str(attr.get('S/N', '')).strip().upper()
            sh_ign = str(attr.get('SOURCE HOURS', '')).strip().upper()
            
            t_prod = float(str(op_ign.get('T. Producción', 0)).replace(',', '.')) if pd.notna(op_ign.get('T. Producción')) else 0.0
            
            ev = obtener_evidencias_vacias()
            ind_ign = {
                "Grupo": "EXCLUIDA FASE 0 | " + str(op_ign.get('MOTIVO_RECHAZO', 'Sin patrón válido')), 
                "Resultado_Final": "SIN SINERGIA (FILTRADA)", 
                "Motivo": str(op_ign.get('MOTIVO_RECHAZO', '')),
                "Warning_Materiales": "-", 
                "Op_A_Materiales_Cant": "-", # <--- AÑADIDO
                "Op_B_Materiales_Cant": "-",
                "Op_A_Ruta": r_ign, "Op_A_Rev": rv_ign, "Op_A_Op": o_ign, 
                "Op_A_Nombre": str(op_ign.get('Nombre Operación', '')), "Op_A_Desc": str(op_ign.get('Descripción Operación', '')), 
                "Op_A_Estacion": limpiar_cruce(op_ign.get('Est. Trab.', '')),
                "Op_A_Doc_Eliminado_Tipo": "-", "Op_A_Doc_Eliminado_Num": "-", "Op_A_Doc_Eliminado_Titulo": "-",
                "conjunto PN ruta A": pn_ign, "conjunto SN ruta A": sn_ign, "Op_A_SH": sh_ign, "Op_A_Prioridad_Source": "-", "Op_A_Tiempo": t_prod,
                "Docs_A": "-", "Op_B_Ruta": "-", "Op_B_Rev": "-", "Op_B_Op": "-", "Op_B_Nombre": "-", "Op_B_Desc": "-", "Op_B_Estacion": "-",
                "Op_B_Doc_Eliminado_Tipo": "-", "Op_B_Doc_Eliminado_Num": "-", "Op_B_Doc_Eliminado_Titulo": "-",
                "conjunto PN ruta B": "-", "conjunto SN ruta B": "-", "Op_B_SH": "-", "Op_B_Prioridad_Source": "-", "Op_B_Tiempo": "-", "Docs_B": "-",
                "Tiempo_Grupo_Sin_Sinergiar": t_prod, "Tiempo_Grupo_Sinergiado": t_prod, "Horas_Ahorradas_Grupo": 0.0
            }
            ind_ign.update(ev)
            resultados_fase2.append(ind_ign)
        # --------------------------------------------------------------------------

        ruta_guardado = os.path.join(carpeta_outputs, "Resultados_Sinergias_Final.xlsx")
        pd.DataFrame(resultados_fase2).to_excel(ruta_guardado, index=False)
        print(f"  - Excel de resultados finales generado con éxito. (Se incluyeron {len(ops_ignoradas)} operaciones filtradas en Fase 0)")

    except Exception as e:
        print(f"\n**[!] ERROR EN EL PROCESAMIENTO:** {e}")
        traceback.print_exc()
        raise e


# =====================================================================
# LLAVE DE CONTACTO (Para pruebas directas), la idea es que se suban los documentos directamente a la interfaz.
# =====================================================================
if __name__ == "__main__":
    rutas_prueba = {
        "Operaciones": r"C:\Users\HECL166\Desktop\Cumplimentadas\nexOp_v2.0\data\data\plantilla_extracto_operaciones.xlsx",
        "Lanzamiento": r"C:\Users\HECL166\Desktop\Cumplimentadas\nexOp_v2.0\data\data\plantilla_analisis_PD.xlsx",
        "Prioridades": r"C:\Users\HECL166\Desktop\Cumplimentadas\nexOp_v2.0\data\data\WP y SOURCES A400.xlsx",
        "Smart_Kits": r"C:\Users\HECL166\Desktop\Cumplimentadas\nexOp_v2.0\data\data\SMART_KITS_A400M_20260622.xlsx",
        "Add_Works": r"C:\Users\HECL166\Desktop\Cumplimentadas\nexOp_v2.0\data\data\Add-Works Catalogue Data.xlsx",
        "Catalogo_OCCAR": r"C:\Users\HECL166\Desktop\Cumplimentadas\nexOp_v2.0\data\data\Referencias de Catálogo OCCAR MSN123.xlsx",
        "TASAR": r"C:\Users\HECL166\Desktop\Cumplimentadas\nexOp_v2.0\data\data\plantilla_PD.xlsx"
    }
    
    if not os.path.exists("outputs"):
        os.makedirs("outputs")
        
    ejecutar_pipeline_completo(rutas_prueba, "outputs")