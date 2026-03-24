import pandas as pd
import os
import re

def cargar_datos():
    print("Cargando datos de la fase 1")
    try:
        df_op = pd.read_excel("outputs/Operaciones_Finales_COMPLETO.xlsx", dtype=str)
        df_doc = pd.read_excel("outputs/Documentos_COMPLETO.xlsx", dtype=str)
        df_mat = pd.read_excel("outputs/Materiales_COMPLETO.xlsx", dtype=str)
        df_ac = pd.read_excel("outputs/AC_Mini_Filtrado_COMPLETO.xlsx", dtype=str)
        df_tasar = pd.read_excel("outputs/Tasar_Filtrado_Y_COMPLETO.xlsx", dtype=str)
        df_cat = pd.read_excel("outputs/Catalogo_Nombres_COMPLETO.xlsx", dtype=str) 
        #se leen todos como texto (str) para evitar perder formato        
        lista_catalogo = set(df_cat['Nombre Operación'].dropna().str.strip().str.upper())
        print("Datos cargados con exito. \n")
        return  df_op, df_doc, df_mat, df_ac, df_tasar, lista_catalogo
    except FileNotFoundError as e:
        print(f"Error: No se encuentra {e.filename}. Ejecuta fase 1")
        exit()
        
def limpiar_cruce(valor):
    texto = str(valor).replace('\xa0', ' ').replace('\n', '').replace('\r', '').replace('_x000D_', '').strip().upper()
    if texto in ['NAN', 'NONE', '', '-']: return ""
    if texto.endswith('.0'): texto = texto[:-2] 
    texto = texto.lstrip('0')
    if texto == "": texto = "0" 
    return texto

#Esta función es para hacer las descripciones más flexibles y poder agruparlas
def flexibilizar_descripcion(desc):
    desc_flexible = re.sub(r'\d+', '#', desc) #Sustituimos cualquier número por # (Engine 1 = Engine #)
    desc_flexible = re.sub(r'\b(LH|RH|FWD|AFT|L|R)\b', '*', desc_flexible) #Las de posición sustituimos por *
    desc_flexible = re.sub(r'\s+', ' ', desc_flexible).strip() #Espacios
    return desc_flexible

def obtener_evidencias_vacias(): #Diccionario de evidencias
    return {
        "Evidencia_Docs": "-", "Evidencia_C1": "-", "Evidencia_C2": "-", "Evidencia_C3": "-",
        "Evidencia_C5": "-", "Evidencia_C6": "-", "Evidencia_C7": "-", "Evidencia_C8": "-", "Evidencia_C9": "-"
    }

def aplicar_fase_2(df_op, df_doc, df_mat, df_ac, df_tasar, lista_catalogo, jerarquia_pep):
    print("="*50)
    print("INICIANDO AGRUPACION Y CONDICIONES (C1 a C9)")
    print("="*50)

    patrones_validos = ['OT', 'BT', 'RMV', 'INS', 'ACC', 'ITL', 'SVC', 'RPL', 'APURUN', 'EGR', 'HPGC', 'LPGC']

    #Columnas nuevas limpias en documentos y materiales
    print("Limpiando formatos de cruce (String vs Int, decimales ocultos)...")
    df_doc['Ruta_str'] = df_doc['Ruta'].apply(limpiar_cruce)
    df_doc['Rev_str'] = df_doc['Rev.'].apply(limpiar_cruce)
    df_doc['Op_str'] = df_doc['Operación'].apply(limpiar_cruce)
    
    df_mat['Ruta_str'] = df_mat['Ruta'].apply(limpiar_cruce)
    df_mat['Rev_str'] = df_mat['Rev.'].apply(limpiar_cruce)
    df_mat['Op_str'] = df_mat['Operación'].apply(limpiar_cruce)

    #Creamos los grupos. Recorremos Operaciones y extraemos Nombre. Descripción y Estación
    grupos = {}

    print("\nAnalizando operaciones (Agrupando con Descripción Flexible...)")
    for idx, row in df_op.iterrows():
        nombre_op = str(row['Nombre Operación']).strip().upper()
        desc_op = str(row['Descripción Operación']).strip().upper()
        estacion = str(row['Estación Oper.']).strip().upper()
        
        desc_flex = flexibilizar_descripcion(desc_op)

        # Busca si el nombre de la operación tiene el patrón válido
        for patron in patrones_validos:
            if re.search(r'\b' + re.escape(patron), nombre_op):
                clave = (patron, desc_flex, estacion)
                if clave not in grupos: grupos[clave] = [] 
                grupos[clave].append(row)
                break
        
    print(f"\n-> Se han creado {len(grupos)} grupos de operaciones para analizar. \n")

    resultados = []
    ejemplos_mostrados = 0 
    
    # --- NUEVAS VARIABLES GLOBALES PARA RASTREAR A TODOS ---
    todas_las_operaciones = {}
    operaciones_emparejadas = set()

    for clave, operaciones in grupos.items():
        mostrar_debug = (ejemplos_mostrados < 5)
        str_clave_grupo = f"{clave[0]} | {clave[1]} | {clave[2]}"
        
        docs_op = {}
        datos_op = {}

        # 1. EXTRAEMOS DATOS DE TODAS LAS OPERACIONES (Incluso si están solas en el grupo)
        for op in operaciones:
            ruta_val = limpiar_cruce(op['Ruta Local'])
            rev_val = limpiar_cruce(op['Rev.'])
            op_val = limpiar_cruce(op['Operación'])
            id_str = f"{ruta_val}-{rev_val}-{op_val}"
            
            nombre_str = str(op['Nombre Operación']).strip().upper()
            desc_str = str(op['Descripción Operación']).strip().upper()

            # Cruce de Documentos
            filtro_docs = (df_doc['Ruta_str'] == ruta_val) & (df_doc['Rev_str'] == rev_val) & (df_doc['Op_str'] == op_val) 
            docs_crudos = df_doc[filtro_docs]['Título Documento'].dropna().astype(str)
            docs_limpios = docs_crudos.str.upper().replace(r'\s+', ' ', regex=True).str.strip()
            docs = set(docs_limpios.unique())
            docs_op[id_str] = docs
            
            str_docs_a = f"({len(docs)}) " + ", ".join(list(docs)) if docs else "(0) Sin documentos"

            # Cruce A/C Mini, TASAR y Materiales
            filtro_ac_mini = (df_ac['RUTA SAN PABLO'].apply(limpiar_cruce) == ruta_val) & \
                             (df_ac['REV SN PABLO COPIADA'].apply(limpiar_cruce) == rev_val)
            filas_ac_mini = df_ac[filtro_ac_mini]
            
            tipo_material = "ninguno"; pn_empieza_por_m = False; tiene_pn_sn = False
            pep_source = ""; maint_type = ""; pn_valor = ""; sn_valor = ""

            if not filas_ac_mini.empty:
                fila_ac = filas_ac_mini.iloc[0]
                
                filtro_mat = (df_mat['Ruta_str'] == ruta_val) & (df_mat['Rev_str'] == rev_val) & (df_mat['Op_str'] == op_val)
                tipos_mat = df_mat[filtro_mat]['Tipo'].str.lower().dropna().unique()
                tipo_material = tipos_mat[0] if len(tipos_mat) > 0 else "ninguno"

                ref_ac_mini = fila_ac['Reference']
                fila_tasar = df_tasar[df_tasar['TASK REFERENCE'] == ref_ac_mini]
                
                if not fila_tasar.empty:
                    pn_valor = str(fila_tasar.iloc[0].get('PN', '')).strip().upper()
                    sn_valor = str(fila_tasar.iloc[0].get('SN', '')).strip().upper()
                    if pn_valor not in ["NAN", "NONE", ""] and pn_valor.startswith('M'): pn_empieza_por_m = True
                    if pn_valor not in ["NAN", "NONE", ""] and sn_valor not in ["NAN", "NONE", ""]: tiene_pn_sn = True
                    pep_source = str(fila_tasar.iloc[0].get('SOURCE HOURS', '')).strip().upper()
                    maint_type = str(fila_tasar.iloc[0].get('MAINTENANCE TYPE', '')).strip().upper()

            es_partial = "PARTIAL" in nombre_str
            es_subtask = "SUBTASK" in desc_str or "SUBTASK" in nombre_str
            palabras_sw = ["SIR PRE", "UPLOAD SOFTWARE", "SIR POST", "SIR CHECK"]
            es_sw = any(sw_word in nombre_str or sw_word in desc_str for sw_word in palabras_sw)
            cambia_config = es_subtask or es_sw
            es_core = ("CORE" in nombre_str) or es_sw 
            
            try:
                t_val = str(op.get('Tiempo Oper.', '0')).strip().replace(',', '.')
                tiempo_op = float(t_val) if t_val.upper() not in ['NAN', 'NONE', ''] else 0.0
            except ValueError:
                tiempo_op = 0.0

            en_catalogo = nombre_str in lista_catalogo

            # Guardamos la info local y en la libreta global
            datos_op[id_str] = {
                "id": id_str, "ruta": ruta_val, "rev": rev_val, "op": op_val, "nombre": nombre_str,
                "tipo_material": tipo_material, "pn_empieza_por_m": pn_empieza_por_m,
                "en_catalogo": en_catalogo, "es_core": es_core, "es_partial": es_partial,
                "tiene_pn_sn": tiene_pn_sn, "pn": pn_valor, "sn": sn_valor,
                "pep_source": pep_source, "maint_type": maint_type, "tiempo": tiempo_op,
                "cambia_config": cambia_config, "es_sw": es_sw,
                "grupo_str": str_clave_grupo, "docs_str": str_docs_a 
            }
            todas_las_operaciones[id_str] = datos_op[id_str]


        # 2. SI HAY MENOS DE 2 OPERACIONES, SALTAMOS EL COMBATE (Pero ya están guardadas)
        if len(operaciones) < 2: 
            continue 
            
        if mostrar_debug: print(f"\n" + "="*40)
        if mostrar_debug: print(f"[TRAZA] ENTRANDO A GRUPO: {str_clave_grupo} (Tamaño: {len(operaciones)})")

        ids = list(datos_op.keys())
        for i in range(len(ids)):
            for j in range(i+1, len(ids)):
                id_a, id_b = ids[i], ids[j]
                dato_a, dato_b = datos_op[id_a], datos_op[id_b]
                
                if mostrar_debug: print(f"\n   [TRAZA] Enfrentando: {id_a} vs {id_b}")

                # Regla 5
                if dato_a["ruta"] == dato_b["ruta"]:
                    if mostrar_debug: print(f"      -> DESCARTADAS: Pertenecen a la misma ruta.")
                    continue
                
                set_a, set_b = docs_op[id_a], docs_op[id_b]
                str_docs_a = dato_a["docs_str"]
                str_docs_b = dato_b["docs_str"]

                info_base = { "Grupo": str_clave_grupo, "Docs_A": str_docs_a, "Docs_B": str_docs_b }
                ev = obtener_evidencias_vacias()

                # --- 1. EVALUACIÓN DE DOCUMENTOS ---
                estado_docs = ""; candidato_padre = None; candidato_hijo = None; motivo_englobe = ""

                if (len(set_a) == 0 and len(set_b) == 0) or (len(set_a) > 0 and len(set_b) == 0) or (len(set_b) > 0 and len(set_a) == 0):
                    estado_docs = "EMPATE_DOCS"; ev["Evidencia_Docs"] = "Empate Documental (Vacíos o Desequilibrio)"
                elif set_a == set_b:
                    estado_docs = "EMPATE_DOCS"; ev["Evidencia_Docs"] = "Empate Documental (Idénticos)"
                elif set_a.issubset(set_b):
                    estado_docs = "ENGLOBE"; candidato_padre = dato_b; candidato_hijo = dato_a
                    motivo_englobe = "Sinergia Parcial (B engloba a A en Docs)"; ev["Evidencia_Docs"] = motivo_englobe
                elif set_b.issubset(set_a):
                    estado_docs = "ENGLOBE"; candidato_padre = dato_a; candidato_hijo = dato_b
                    motivo_englobe = "Sinergia Parcial (A engloba a B en Docs)"; ev["Evidencia_Docs"] = motivo_englobe
                else:
                    if mostrar_debug: print(f"      -> DESCARTADAS: Docs no coinciden ni se engloban.")
                    continue 

                # --- 2. PRE-FILTROS DE K.O. Y CASCADA ---
                ko_tecnico = False
                resultado_reglas = None
                
                # REGLA SUPREMA: PARTIAL JAMÁS ES PADRE
                if dato_a["es_partial"] and dato_b["es_partial"]:
                    if mostrar_debug: print(f"      -> ANULADA: Ambas son PARTIAL, ninguna puede ser padre.")
                    continue # Se aborta el combate
                elif dato_a["es_partial"]:
                    resultado_reglas = generar_resultado(dato_b, dato_a, "Forzado PRE-Docs: A es PARTIAL (Hija obligatoria)", ev)
                    ko_tecnico = True
                elif dato_b["es_partial"]:
                    resultado_reglas = generar_resultado(dato_a, dato_b, "Forzado PRE-Docs: B es PARTIAL (Hija obligatoria)", ev)
                    ko_tecnico = True
                    
                # REGLA SECUNDARIA: PN/SN
                if not ko_tecnico:
                    if not dato_a["tiene_pn_sn"] and dato_b["tiene_pn_sn"]:
                        resultado_reglas = generar_resultado(dato_a, dato_b, "Forzado PRE-Docs: A no tiene PN/SN (Padre)", ev)
                        ko_tecnico = True
                    elif not dato_b["tiene_pn_sn"] and dato_a["tiene_pn_sn"]:
                        resultado_reglas = generar_resultado(dato_b, dato_a, "Forzado PRE-Docs: B no tiene PN/SN (Padre)", ev)
                        ko_tecnico = True

                if not ko_tecnico:
                    resultado_reglas = evaluar_desempate_cascada(dato_a, dato_b, jerarquia_pep, ev)
                
                # --- 3. CONTRASTE: DOCUMENTOS vs REGLAS ---
                padre_elegido_id = f"{resultado_reglas['Op_A_Ruta']}-{resultado_reglas['Op_A_Rev']}-{resultado_reglas['Op_A_Op']}"
                
                if estado_docs == "EMPATE_DOCS":
                    resultado_reglas.update(info_base)
                    resultados.append(resultado_reglas)
                    operaciones_emparejadas.add(id_a); operaciones_emparejadas.add(id_b)
                    
                elif estado_docs == "ENGLOBE":
                    id_candidato_padre = candidato_padre["id"]
                    
                    if resultado_reglas["Resultado_Final"].startswith("EMPATE"):
                        resultado_reglas = generar_resultado(candidato_padre, candidato_hijo, f"{motivo_englobe} (Desempata reglas)", ev)
                        resultado_reglas.update(info_base)
                        resultados.append(resultado_reglas)
                        operaciones_emparejadas.add(id_a); operaciones_emparejadas.add(id_b)
                        
                    elif padre_elegido_id == id_candidato_padre:
                        resultado_reglas["Motivo"] = f"{motivo_englobe} + CONFIRMADO POR: {resultado_reglas['Motivo']}"
                        resultado_reglas.update(info_base)
                        resultados.append(resultado_reglas)
                        operaciones_emparejadas.add(id_a); operaciones_emparejadas.add(id_b)
                        
                    else:
                        if mostrar_debug: print(f"      -> ANULADA: Contradicción con las reglas.")
                        continue
        ejemplos_mostrados += 1


    # --- 4. RECOGER A LOS HUÉRFANOS (EJECUTABLES INDEPENDIENTES) ---
    for op_id, op_data in todas_las_operaciones.items():
        if op_id not in operaciones_emparejadas:
            ev = obtener_evidencias_vacias()
            res_indep = {
                "Grupo": op_data["grupo_str"],
                "Resultado_Final": "EJECUTABLE (Independiente)",
                "Motivo": "Sin sinergia válida (Única en grupo, docs incompatibles o anulada por reglas)",
                # Datos rellenados en el lado del 'Padre' para visibilidad
                "Op_A_Ruta": op_data["ruta"], "Op_A_Rev": op_data["rev"], "Op_A_Op": op_data["op"], 
                "Op_A_Nombre": op_data["nombre"], "Op_A_PN": op_data["pn"], "Op_A_SN": op_data["sn"],
                "Op_A_PEP": op_data["pep_source"], "Op_A_MaintType": op_data["maint_type"],
                "Op_A_Material": op_data["tipo_material"], "Op_A_Tiempo": op_data["tiempo"],
                "Op_A_Catalogo": op_data["en_catalogo"], "Op_A_Core": op_data["es_core"],
                "Docs_A": op_data["docs_str"],
                # Lado del 'Hijo' vacío
                "Op_B_Ruta": "-", "Op_B_Rev": "-", "Op_B_Op": "-", "Op_B_Nombre": "-", 
                "Op_B_PN": "-", "Op_B_SN": "-", "Op_B_PEP": "-", "Op_B_MaintType": "-",
                "Op_B_Material": "-", "Op_B_Tiempo": "-", "Op_B_Catalogo": "-", "Op_B_Core": "-", "Docs_B": "-"
            }
            res_indep.update(ev)
            resultados.append(res_indep)


    # --- GUARDADO EN EXCEL ---
    if resultados:
        df_resultados = pd.DataFrame(resultados)
        columnas_ordenadas = [
            "Grupo", "Resultado_Final", "Motivo",
            "Op_A_Ruta", "Op_A_Rev", "Op_A_Op", "Op_A_Nombre", "Op_A_PN", "Op_A_SN", "Op_A_PEP", "Op_A_MaintType", "Op_A_Material", "Op_A_Tiempo", "Op_A_Catalogo", "Op_A_Core",
            "Op_B_Ruta", "Op_B_Rev", "Op_B_Op", "Op_B_Nombre", "Op_B_PN", "Op_B_SN", "Op_B_PEP", "Op_B_MaintType", "Op_B_Material", "Op_B_Tiempo", "Op_B_Catalogo", "Op_B_Core",
            "Evidencia_Docs", "Evidencia_C1", "Evidencia_C2", "Evidencia_C3", "Evidencia_C5", 
            "Evidencia_C6", "Evidencia_C7", "Evidencia_C8", "Evidencia_C9", "Docs_A", "Docs_B"
        ]
        
        for col in columnas_ordenadas:
            if col not in df_resultados.columns: df_resultados[col] = "-"
                
        df_resultados = df_resultados[columnas_ordenadas]
        
        print("\nRESULTADOS FINALES:")
        print(f"Se han evaluado y guardado {len(df_resultados)} filas (Pares + Ejecutables independientes).")
        df_resultados.to_excel("outputs/Resultados_C1_C2.xlsx", index = False)
        print("\nGuardado en: outputs/Resultados_C1_C2.xlsx")
    else:
        print("\n[RESULTADO] Error masivo, no hay datos.")


# --- FUNCIONES DE EVALUACION Y EMPAQUETADO ---
def evaluar_desempate_cascada(a, b, jerarquia_pep, ev):
    if (a["es_core"] or a["es_sw"]) and (b["es_core"] or b["es_sw"]):
        ev["Evidencia_C1"] = f"EMPATE: Ambas son CORE o están relacionadas con SW."
        return generar_resultado_empate(a, b, "C1: Ambas CORE/SW", ev)

    if a["cambia_config"] and not b["cambia_config"]:
        ev["Evidencia_C1"] = f"GANA A: '{a['nombre']}' cambia la configuración."
        return generar_resultado(a, b, "C1: A cambia configuración", ev)
    if b["cambia_config"] and not a["cambia_config"]:
        ev["Evidencia_C1"] = f"GANA B: '{b['nombre']}' cambia la configuración."
        return generar_resultado(b, a, "C1: B cambia configuración", ev)

    a_es_material = a["tipo_material"] in ['material', 'materiales']
    b_es_material = b["tipo_material"] in ['material', 'materiales']
    
    a_es_hti = "HTI" in a["nombre"] or "HARD TIME ITEM" in a["nombre"] or "HTI" in a["maint_type"]
    b_es_hti = "HTI" in b["nombre"] or "HARD TIME ITEM" in b["nombre"] or "HTI" in b["maint_type"]
    
    a_c1 = a_es_hti or (a_es_material and a["pn_empieza_por_m"])
    b_c1 = b_es_hti or (b_es_material and b["pn_empieza_por_m"])
    
    if a_c1 and not b_c1:
        ev["Evidencia_C1"] = f"GANA A: '{a['nombre']}' cumple HTI/Mat+M. B no cumple."
        return generar_resultado(a, b, "C1: A es HTI o (Material y PN_M)", ev)
    if b_c1 and not a_c1:
        ev["Evidencia_C1"] = f"GANA B: '{b['nombre']}' cumple HTI/Mat+M. A no cumple."
        return generar_resultado(b, a, "C1: B es HTI o (Material y PN_M)", ev)
        
    ev["Evidencia_C1"] = f"EMPATE: A(Cumple: {a_c1}), B(Cumple: {b_c1})"

    a_cat_core = a["en_catalogo"] and a["es_core"]
    a_cat_no_core = a["en_catalogo"] and not a["es_core"]
    b_cat_core = b["en_catalogo"] and b["es_core"]
    b_cat_no_core = b["en_catalogo"] and not b["es_core"]

    if a_cat_core and b_cat_core:
        ev["Evidencia_C2"] = f"AMBAS EJECUTABLES: '{a['nombre']}' y '{b['nombre']}' son CORE"
        return generar_resultado_empate(a, b, "C2: Ambas CORE en catalogo (Ejecutables)", ev)
    if a_cat_core:
        ev["Evidencia_C2"] = f"GANA A: '{a['nombre']}' es CORE"
        return generar_resultado(a, b, "C2: A es CORE en Catalogo", ev)
    if b_cat_core:
        ev["Evidencia_C2"] = f"GANA B: '{b['nombre']}' es CORE"
        return generar_resultado(b, a, "C2: B es CORE en Catalogo", ev)
    if a_cat_no_core and not b_cat_no_core:
        ev["Evidencia_C2"] = f"GANA B: A ('{a['nombre']}') esta en catalogo pero NO es CORE (Solo puede ser hija)"
        return generar_resultado(b, a, "C2: A en Catalogo sin CORE", ev)
    if b_cat_no_core and not a_cat_no_core:
        ev["Evidencia_C2"] = f"GANA A: B ('{b['nombre']}') esta en catalogo pero NO es CORE (Solo puede ser hija)"
        return generar_resultado(a, b, "C2: B en Catalogo sin CORE", ev)
        
    if a_cat_no_core and b_cat_no_core:
        ev["Evidencia_C2"] = f"EMPATE: Ambas en catalogo pero sin CORE -> A: '{a['nombre']}', B: '{b['nombre']}'"
    else:
        ev["Evidencia_C2"] = "EMPATE: Ninguna de las dos esta en el catalogo o es CORE"

    ev["Evidencia_C3"] = "Ignorada (Evaluada en pre-filtro K.O.)"
    ev["Evidencia_C5"] = "Ignorada (Evaluada en pre-filtro K.O.)"

    idx_a = jerarquia_pep.index(a["pep_source"]) if a["pep_source"] in jerarquia_pep else 999
    idx_b = jerarquia_pep.index(b["pep_source"]) if b["pep_source"] in jerarquia_pep else 999
    
    if idx_a < idx_b:
        ev["Evidencia_C6"] = f"GANA A: PEP '{a['pep_source']}' es mejor que '{b['pep_source']}'"
        return generar_resultado(a, b, "C6: A tiene mayor jerarquia PEP", ev)
    if idx_b < idx_a:
        ev["Evidencia_C6"] = f"GANA B: PEP '{b['pep_source']}' es mejor que '{a['pep_source']}'"
        return generar_resultado(b, a, "C6: B tiene mayor jerarquia PEP", ev)
        
    ev["Evidencia_C6"] = f"EMPATE: Tienen la misma jerarquia PEP ('{a['pep_source']}')"

    palabras_a = set(a["nombre"].split())
    palabras_b = set(b["nombre"].split())
    
    if palabras_b.issubset(palabras_a) and len(palabras_a) > len(palabras_b):
        ev["Evidencia_C8"] = f"GANA A: '{a['nombre']}' contiene todas las palabras de B"
        return generar_resultado(a, b, "C8: Nombre de A engloba a B", ev)
    if palabras_a.issubset(palabras_b) and len(palabras_b) > len(palabras_a):
        ev["Evidencia_C8"] = f"GANA B: '{b['nombre']}' contiene todas las palabras de A"
        return generar_resultado(b, a, "C8: Nombre de B engloba a A", ev)
        
    ev["Evidencia_C8"] = "EMPATE: Los nombres no se engloban entre si"

    # --- C7: SIMETRÍA Y CONSISTENCIA (COMENTADA TEMPORALMENTE) ---
    # if a["nombre"] != b["nombre"]:
    #     if a["nombre"] < b["nombre"]:
    #         ev["Evidencia_C7"] = f"GANA A: Por Simetría/Orden ({a['nombre']} prevalece sobre {b['nombre']})"
    #         return generar_resultado(a, b, "C7: Simetría y Consistencia", ev)
    #     else:
    #         ev["Evidencia_C7"] = f"GANA B: Por Simetría/Orden ({b['nombre']} prevalece sobre {a['nombre']})"
    #         return generar_resultado(b, a, "C7: Simetría y Consistencia", ev)
            
    ev["Evidencia_C7"] = "IGNORADA (Simetría en Modo Avión)"

    # --- C9: Tiempo ---
    if a["tiempo"] > b["tiempo"]:
        ev["Evidencia_C9"] = f"GANA A: Tiempo {a['tiempo']}h vs {b['tiempo']}h de B"
        return generar_resultado(a, b, "C9: A tiene mayor Tiempo", ev)
    if b["tiempo"] > a["tiempo"]:
        ev["Evidencia_C9"] = f"GANA B: Tiempo {b['tiempo']}h vs {a['tiempo']}h de A"
        return generar_resultado(b, a, "C9: B tiene mayor Tiempo", ev)
        
    ev["Evidencia_C9"] = f"EMPATE: Tienen exactamente el mismo tiempo ({a['tiempo']}h)"

    return generar_resultado_empate(a, b, "C10: Empate Absoluto", ev)


def generar_resultado(padre, hijo, motivo, diccionario_evidencias):
    res = {
        "Resultado_Final": f"PADRE: {padre['id']} -> HIJA: {hijo['id']}",  
        "Motivo": motivo,
        "Op_A_Ruta": padre["ruta"], "Op_A_Rev": padre["rev"], "Op_A_Op": padre["op"], 
        "Op_A_Nombre": padre["nombre"], "Op_A_PN": padre["pn"], "Op_A_SN": padre["sn"],
        "Op_A_PEP": padre["pep_source"], "Op_A_MaintType": padre["maint_type"],
        "Op_A_Material": padre["tipo_material"], "Op_A_Tiempo": padre["tiempo"],
        "Op_A_Catalogo": padre["en_catalogo"], "Op_A_Core": padre["es_core"],
        "Op_B_Ruta": hijo["ruta"], "Op_B_Rev": hijo["rev"], "Op_B_Op": hijo["op"], 
        "Op_B_Nombre": hijo["nombre"], "Op_B_PN": hijo["pn"], "Op_B_SN": hijo["sn"],
        "Op_B_PEP": hijo["pep_source"], "Op_B_MaintType": hijo["maint_type"],
        "Op_B_Material": hijo["tipo_material"], "Op_B_Tiempo": hijo["tiempo"],
        "Op_B_Catalogo": hijo["en_catalogo"], "Op_B_Core": hijo["es_core"]
    }
    res.update(diccionario_evidencias)
    return res

def generar_resultado_empate(a, b, motivo, diccionario_evidencias):
    res = {
        "Resultado_Final": "EMPATE: Ni padre ni hija", 
        "Motivo": motivo,
        "Op_A_Ruta": a["ruta"], "Op_A_Rev": a["rev"], "Op_A_Op": a["op"], 
        "Op_A_Nombre": a["nombre"], "Op_A_PN": a["pn"], "Op_A_SN": a["sn"],
        "Op_A_PEP": a["pep_source"], "Op_A_MaintType": a["maint_type"],
        "Op_A_Material": a["tipo_material"], "Op_A_Tiempo": a["tiempo"],
        "Op_A_Catalogo": a["en_catalogo"], "Op_A_Core": a["es_core"],
        "Op_B_Ruta": b["ruta"], "Op_B_Rev": b["rev"], "Op_B_Op": b["op"], 
        "Op_B_Nombre": b["nombre"], "Op_B_PN": b["pn"], "Op_B_SN": b["sn"],
        "Op_B_PEP": b["pep_source"], "Op_B_MaintType": b["maint_type"],
        "Op_B_Material": b["tipo_material"], "Op_B_Tiempo": b["tiempo"],
        "Op_B_Catalogo": b["en_catalogo"], "Op_B_Core": b["es_core"]
    }
    res.update(diccionario_evidencias)
    return res

if __name__=='__main__':
    jerarquia_usuario_mock = ['ESTRUCTURAS', 'SISTEMAS', 'CABINA'] 
    df_op, df_doc, df_mat, df_ac, df_tasar, lista_catalogo = cargar_datos()
    aplicar_fase_2(df_op, df_doc, df_mat, df_ac, df_tasar, lista_catalogo, jerarquia_usuario_mock)